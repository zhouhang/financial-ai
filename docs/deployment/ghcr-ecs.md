# GHCR + ECS Deployment

This is the first-version production deployment path for Tally. GitHub Actions builds images,
pushes them to GitHub Container Registry, then tells the ECS host to pull and restart services
with Docker Compose.

## Images

- `ghcr.io/<owner>/<repo>/tally-python:<tag>` runs:
  - `finance-mcp`
  - `data-agent`
  - `finance-cron`
  - `recon-worker-1`
  - `recon-worker-2`
- `ghcr.io/<owner>/<repo>/finance-web:<tag>` serves the React build with Nginx.

The browser-agent is intentionally not part of this compose file. It runs on the Windows
collection machine so Chrome profiles and Playwright browser state remain local to that host.
Point the Windows collection machine at `wss://api.example.com/browser-agent` with `DATA_AGENT_WS_URL`
after the host Nginx route is live.

## One-Time ECS Setup

Install Docker and the Compose plugin on ECS, then prepare `/opt/tally`:

```bash
sudo mkdir -p /opt/tally
sudo chown "$USER":"$USER" /opt/tally
```

Copy these files to `/opt/tally`:

```text
docker-compose.prod.yml
.env.prod
deploy.env
```

Use `deploy.env.example` as the starting point:

```bash
cp deploy.env.example /opt/tally/deploy.env
```

`deploy.env` controls image names and the first-version DB pool sizing:

```env
GHCR_OWNER=your-github-org-or-user
GHCR_REPOSITORY=financial-ai
IMAGE_TAG=main-0000000
DB_POOL=1
DB_POOL_MAXCONN=16
```

`.env.prod` contains runtime secrets and service settings. Do not commit it. At minimum it should
include the production database, JWT, LLM, public URL, and notification settings used by the app.
Use service-internal URLs for container-to-container traffic:

```env
DB_HOST=<rds-internal-host>
DB_PORT=5432
DB_NAME=tally
DB_USER=<db-user>
DB_PASSWORD=<db-password>
DATABASE_URL=postgresql://<db-user>:<db-password>@<rds-internal-host>:5432/tally
LANGGRAPH_CHECKPOINT_DATABASE_URL=postgresql://<db-user>:<db-password>@<rds-internal-host>:5432/tally
LANGGRAPH_CHECKPOINT_SCHEMA=langgraph_checkpoint
JWT_SECRET=<long-random-secret>
FINANCE_MCP_BASE_URL=http://finance-mcp:3335
DATA_AGENT_BASE_URL=http://data-agent:8100
TALLY_PUBLIC_BASE_URL=https://api.example.com
MCP_PUBLIC_BASE_URL=https://api.example.com
TALLY_PUBLIC_WEB_BASE_URL=https://www.example.com
```

Use `env.prod.example` as the non-secret checklist for this file.

Log in to GHCR once on ECS. For private packages, the token needs `read:packages`.

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <github-user> --password-stdin
```

## OSS Storage

Production should set `STORAGE_BACKEND=oss` in `/opt/tally/.env.prod` and use a private OSS
bucket. Do not make the bucket public; the application serves downloads through authenticated
backend routes.

Required variables:

```env
STORAGE_BACKEND=oss
OSS_BUCKET=<private-bucket-name>
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OSS_REGION=cn-hangzhou
OSS_ACCESS_KEY_ID=<oss-access-key-id>
OSS_ACCESS_KEY_SECRET=<oss-access-key-secret>
OSS_PREFIX=financial-ai/prod
OSS_PRESIGN_EXPIRE_SECONDS=900
OSS_UPLOAD_MAX_SIZE=104857600
```

The Windows browser-agent is not part of the ECS compose file. Configure the same OSS variables
on the collection machine so raw browser downloads are uploaded before
`browser_sync_job_complete` reports success. The browser-agent imports `oss2` lazily; install the
same Python dependency set that includes `oss2>=2.18.0`.

## GitHub Secrets

Add these repository secrets:

```text
PROD_HOST
PROD_SSH_USER
PROD_SSH_KEY
PROD_DEPLOY_DIR
```

`PROD_DEPLOY_DIR` is optional in the workflow and defaults to `/opt/tally`.

## First Deploy

Push to `main` or run the workflow manually:

```text
.github/workflows/deploy-ghcr.yml
```

The workflow writes a fresh `deploy.env`, pulls the new images, restarts compose, and checks:

```bash
curl -fsS http://127.0.0.1:3335/health
curl -fsS http://127.0.0.1:8100/health
curl -fsS http://127.0.0.1:5173/health
```

## Manual Rollback

On ECS, inspect the previous deploy tag:

```bash
cat /opt/tally/deploy.env.prev
```

Restore the previous tag and restart:

```bash
cd /opt/tally
cp deploy.env.prev deploy.env
docker compose --env-file deploy.env -f docker-compose.prod.yml pull
docker compose --env-file deploy.env -f docker-compose.prod.yml up -d --remove-orphans
```

## Logs

Logging follows the runtime form, not the service. There are three forms, and each
has one correct log destination. Do **not** add per-service `logs/` directories inside
the repo — that is a half-measure between file logging and container logging that
fits neither.

### 1. Cloud services in containers (canonical production path)

`finance-mcp`, `data-agent`, `finance-cron`, `recon-worker-*`, and `finance-web` run as
containers from `docker-compose.prod.yml`. They log to **stdout/stderr**, and Docker's
`json-file` driver captures them. Do not write log files inside these containers — the
container filesystem is ephemeral and would be lost on restart.

Read them with:

```bash
docker compose -f docker-compose.prod.yml logs -f data-agent
```

Rotation is set once for all services via the `x-common-env` anchor:

```yaml
logging:
  driver: json-file
  options:
    max-size: "50m"   # roll to a new file once the current one hits 50 MB
    max-file: "5"     # keep 5 files (1 active + 4 archived), delete the oldest
```

So `50m x 5` means each container's logs are capped at a rolling **250 MB** window
(`50 MB x 5`); older lines are dropped automatically and never fill the disk. For
long-term retention beyond that window, forward stdout to an external sink
(Loki/ELK) — do not raise the cap to "keep everything".

### 2. Browser-agent on the collection machine (not containerized)

The browser-agent runs as a bare process on the Windows/collection machine with a real
Chrome, so file logging in its **own** directory is correct. `scripts/start-browser-agent.sh`
already defaults there:

```bash
LOG_DIR="${BROWSER_AGENT_LOG_DIR:-$BROWSER_AGENT_DIR/logs}"   # finance-agents/browser-agent/logs/
```

It is intentionally separate from the cloud services because it is deployed on a
different host. Leave its log under `finance-agents/browser-agent/logs/`.

### 3. Local all-in-one (`START_ALL_SERVICES.sh`, dev only)

When everything runs on one machine as `nohup` processes, there is no container runtime
to collect stdout, so the script redirects every service to a single `logs/` directory
at the repo root (`LOG_DIR="$PROJECT_ROOT/logs"`) for easy `tail`. In this mode it also
overrides `BROWSER_AGENT_LOG_DIR="$LOG_DIR"` so the agent log joins the others. This is a
dev convenience only and does not apply to production.

For this bare-metal/script form, install the provided logrotate config (the container
`json-file` rotation does **not** cover these host files):

```bash
sudo cp deploy/logrotate/financial-ai /etc/logrotate.d/financial-ai
sudo logrotate -d /etc/logrotate.d/financial-ai   # -d = dry run, prints what it would do
```

## Nginx/SSL Front Door

Expose only 80/443 publicly. Keep application ports bound to localhost as the compose file does:

```text
127.0.0.1:3335 finance-mcp
127.0.0.1:8100 data-agent
127.0.0.1:5173 finance-web
```

A host-level Nginx or ALB should route:

```text
https://www.example.com      -> http://127.0.0.1:5173
https://api.example.com      -> http://127.0.0.1:8100
https://api.example.com/api/* -> http://127.0.0.1:8100/*
https://api.example.com/output/* -> http://127.0.0.1:3335/output/*
```

The web image also proxies `/api/*` to `data-agent` internally, so routing `www` to `finance-web`
is enough for normal browser use. Route `api` separately for callbacks, browser-agent WebSocket
traffic, direct API integrations, and finance-mcp output downloads. The `/api/*` rule below strips
the `/api` prefix to match the existing Vite proxy behavior.

Minimal host Nginx shape:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 443 ssl http2;
    server_name www.example.com;

    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    location /output/ {
        proxy_pass http://127.0.0.1:3335/output/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8100/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 900s;
    }

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 900s;
    }
}
```

## Notes

- `DB_POOL_MAXCONN=16` matches the current application default and is appropriate for the first
  RDS 2c8g rollout.
- Logging policy (containers vs. browser-agent vs. local script) lives in the `## Logs`
  section above; do not add per-service `logs/` directories in the repo.
- Uploads, generated outputs, and browser capture files should use the private OSS bucket in
  production. Docker volumes remain mounted for local fallback, temporary files, and legacy
  compatibility.
