# OSS Storage and Production Log Control Design

Date: 2026-06-01

## Context

Financial AI currently stores operational files on the local filesystem:

- User uploads are accepted by `finance-agents/data-agent/server.py` and delegated to the
  `file_upload` MCP tool in `finance-mcp/tools/file_upload_tool.py`, which writes under
  `finance-mcp/uploads`.
- Reconciliation outputs are written under `finance-mcp/recon/output` and protected by sidecar
  `.meta.json` files. Downloads go through `finance-mcp/unified_mcp_server.py` at
  `/output/{module}/{path}`.
- Proc outputs are written under `finance-mcp/proc/output`.
- Browser collection downloads are saved on the browser-agent machine and persisted as
  `browser_capture_files.storage_path`.
- Local development services are started by `START_ALL_SERVICES.sh`, which redirects process logs to
  `logs/*.log`.
- Production deployment is moving to Docker Compose. The new production compose keeps application
  ports bound to `127.0.0.1`, persists current file paths as Docker volumes, and caps Docker JSON
  logs at `50m x 5`.

The production storage target is an Alibaba Cloud OSS private bucket. Only new files need to move to
OSS. Historical local files stay where they are and must remain readable.

## Goals

- Store new user uploads, reconciliation outputs, proc outputs, and browser raw download files in an
  OSS private bucket.
- Use browser direct upload for user-uploaded files in production.
- Keep downloads behind backend authorization, not public OSS URLs.
- Preserve local development flow through the existing script and local filesystem defaults.
- Keep historical local files compatible without running a migration.
- Add production Docker log limits and local host logrotate guidance so logs cannot grow without
  bound.

## Non-Goals

- No historical file migration to OSS.
- No public bucket or anonymous object access.
- No rewrite of reconciliation, proc, or browser collection business logic beyond the file storage
  boundary.
- No frontend redesign.

## Recommended Approach

Use a hybrid storage model:

- Frontend uploads new files directly to OSS after obtaining a short-lived upload policy from the
  backend.
- The backend confirms uploaded objects, records metadata, and returns the same attachment shape the
  current chat flow expects.
- Backend services access files through a storage abstraction that supports both OSS objects and
  legacy local paths.
- Generated files are created as local temporary files, uploaded to OSS, and then referenced by
  storage metadata.
- All user-facing downloads remain backend-proxied and authorization checked.

This is the safest path for production because large upload bandwidth avoids the application server,
while downloads still benefit from existing ownership checks and audit controls.

## Storage Abstraction

Add a small storage layer in `finance-mcp`, used by MCP tools and output download routes:

- `StorageObjectRef`: provider, bucket, key, original filename, content type, size, checksum, and
  optional legacy local path.
- `StorageClient`: `put_file`, `get_stream`, `download_to_temp`, `exists`, `stat`, and
  `create_presigned_upload`.
- `LocalStorageClient`: wraps existing local directories for development and legacy paths.
- `OssStorageClient`: wraps Alibaba Cloud OSS SDK calls.
- `storage_from_env()`: selects `local` or `oss` from environment.

The storage layer accepts old refs such as `/uploads/...` and absolute paths under known safe roots,
then resolves them through existing security checks. New OSS refs should be represented as structured
metadata and may also expose a compact internal URI such as `oss://bucket/key` for logs and DB rows.

## Object Key Layout

Use deterministic prefixes that separate tenant, purpose, and date:

```text
{OSS_PREFIX}/uploads/{company_id}/{yyyy}/{mm}/{dd}/{uuid}-{safe_filename}
{OSS_PREFIX}/proc-output/{company_id}/{yyyy}/{mm}/{dd}/{run_id}/{safe_filename}
{OSS_PREFIX}/recon-output/{company_id}/{yyyy}/{mm}/{dd}/{run_id}/{safe_filename}
{OSS_PREFIX}/browser-captures/{company_id}/{shop_id}/{biz_date}/{sync_job_id}/{safe_filename}
```

Keys must not rely on the user-provided filename for uniqueness. Filenames are sanitized for display
and content disposition only.

## Upload Flow

Production upload flow:

1. Frontend calls a new backend endpoint or MCP tool to create a presigned OSS upload policy.
2. Backend validates auth, extension, size limit, and ownership context, then returns upload fields
   and the intended storage key.
3. Frontend uploads the file directly to OSS.
4. Frontend calls a confirm endpoint with storage key, original filename, size, and checksum if
   available.
5. Backend verifies object existence and expected prefix, records metadata, and returns the current
   attachment shape: `file_path`, `original_filename`, and `size`.

For local development and fallback, keep the current `/upload` proxy path. When
`STORAGE_BACKEND=local`, it continues to write to `finance-mcp/uploads`. When production direct
upload is unavailable, the backend may accept the old proxy upload and immediately `put_file` to OSS,
but this is a fallback rather than the default production path.

## Reading Inputs

Existing reconciliation and proc code expects local file paths for pandas and openpyxl. To limit risk:

- Resolve each input file through the storage layer.
- If the input is OSS-backed, download it to a request-scoped temporary file.
- Pass the temporary path to existing parsers.
- Clean up temporary files after the run.

Legacy `/uploads/...` paths continue through `resolve_upload_file_path` and
`resolve_recon_input_file_path`.

## Generated Outputs

Reconciliation and proc outputs should keep their current generation strategy:

1. Write the result workbook or CSV to a temporary local output path.
2. Write or build metadata containing module, owner, company, original filename, generated time, and
   storage ref.
3. Upload both the generated file and any metadata needed for authorization to OSS.
4. Return a backend download URL, not a direct OSS URL.

The `/output/{module}/{path}` route must be extended to resolve both legacy local files and new OSS
objects. Authorization remains based on authenticated user, owner metadata, and admin override. The
response streams from OSS with a safe content disposition filename.

Docker volumes for `uploads`, `proc/output`, and `recon/output` can stay in compose as temporary
working space and as compatibility for old paths. They are no longer the durable production store for
new files.

## Browser Raw Download Files

The browser-agent runs outside the ECS compose on a Windows collection machine, so it must upload raw
download files to OSS itself.

Flow:

1. Browser-agent downloads the source CSV/XLSX locally as it does today.
2. Browser-agent uploads the raw file to OSS using the same object key rules under
   `browser-captures`.
3. Browser-agent reports capture metadata back to finance-mcp.
4. finance-mcp stores structured storage metadata for audit.

Add columns to `browser_capture_files` while preserving `storage_path`:

- `storage_provider`
- `storage_bucket`
- `storage_key`
- `storage_uri`
- `content_type`
- `size_bytes`

For legacy rows, `storage_provider='local'` can be inferred when the new fields are empty and
`storage_path` contains a local path.

## Configuration

Add production environment variables:

```env
STORAGE_BACKEND=oss
OSS_BUCKET=
OSS_ENDPOINT=
OSS_REGION=
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_PREFIX=financial-ai/prod
OSS_PRESIGN_EXPIRE_SECONDS=900
OSS_UPLOAD_MAX_SIZE=104857600
```

Local development defaults:

```env
STORAGE_BACKEND=local
```

Do not require OSS credentials for local script-based development.

## Logging and Rotation

Production Docker:

- Keep the compose `json-file` cap at `max-size=50m` and `max-file=5` for each service.
- Document an optional daemon-level default for ECS hosts, but do not depend on it because the compose
  file already sets service-level limits.

Local script deployment:

- Add a logrotate config for `logs/*.log`.
- Rotate at `50M`, keep 7 compressed files, and use `copytruncate` because the current launcher keeps
  log file descriptors open.
- Include `missingok` and `notifempty`.

The app should continue logging to stdout/stderr in Docker. Avoid adding file handlers inside
containers.

## Deployment Compatibility

Production:

- Docker Compose remains the production process manager.
- `.env.prod` sets `STORAGE_BACKEND=oss`.
- Volumes remain mounted for temp files and legacy compatibility.
- Host Nginx routes continue to send frontend traffic to `finance-web`, API traffic to `data-agent`,
  and output downloads to `finance-mcp`.

Local:

- `START_ALL_SERVICES.sh` remains the primary development entrypoint.
- Local mode defaults to filesystem storage.
- Existing local uploads and outputs continue to work.

## Error Handling

- Presign requests fail fast when OSS config is incomplete in `STORAGE_BACKEND=oss`.
- Confirm upload rejects keys outside the authenticated user's allowed prefix.
- Confirm upload verifies the object exists before recording metadata.
- File reads fail with user-facing messages that distinguish missing object, permission denied, and
  unsupported legacy path.
- Output upload failures mark the run failed rather than returning a local-only result in production.
- Browser-agent upload failures should fail the sync job or mark capture upload failure explicitly;
  do not silently store a local Windows path as production audit storage.

## Testing

Unit tests:

- Storage ref parsing for OSS URIs, structured refs, and legacy local paths.
- Local storage client compatibility with current `/uploads/...` behavior.
- OSS client behavior with mocked SDK.
- Upload presign and confirm authorization.
- Output route authorization for OSS-backed metadata.
- Browser capture file DB insert with new storage fields and old `storage_path` fallback.

Integration tests:

- Upload confirm returns attachment shape compatible with chat.
- Reconciliation can read OSS-backed inputs through temp files.
- Reconciliation output uploads to storage and downloads through `/output/recon/...`.
- Browser-agent reports OSS-backed capture files.

Deployment checks:

- Docker compose health checks still pass.
- Docker log options are present for all services.
- Logrotate config validates with `logrotate -d`.

## Rollout Plan

1. Add storage abstraction and local backend without changing behavior.
2. Add OSS backend and configuration.
3. Add upload presign and confirm flow, keeping old upload as local/fallback.
4. Update input readers to resolve OSS-backed files to temp files.
5. Update proc/recon output upload and `/output` streaming.
6. Update browser-agent capture upload and DB schema.
7. Add Docker/env documentation and local logrotate config.
8. Deploy with `STORAGE_BACKEND=local` first for smoke testing.
9. Switch production to `STORAGE_BACKEND=oss` after OSS credentials and bucket policy are ready.

