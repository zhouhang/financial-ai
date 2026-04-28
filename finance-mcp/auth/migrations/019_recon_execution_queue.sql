CREATE TABLE IF NOT EXISTS recon_execution_queue (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    run_plan_code varchar(128) NOT NULL,
    biz_date varchar(32) NOT NULL DEFAULT '',
    trigger_mode varchar(32) NOT NULL DEFAULT 'schedule',
    run_context jsonb NOT NULL DEFAULT '{}',
    status varchar(20) NOT NULL DEFAULT 'queued',
    attempt int NOT NULL DEFAULT 0,
    error text NOT NULL DEFAULT '',
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    finished_at timestamptz,
    CONSTRAINT recon_execution_queue_status_check CHECK (
        status = ANY(ARRAY['queued', 'running', 'done', 'failed'])
    )
);

-- 仅对 queued 状态建索引，保证 SKIP LOCKED 扫描高效
CREATE INDEX IF NOT EXISTS idx_recon_execution_queue_queued
    ON recon_execution_queue (created_at ASC)
    WHERE status = 'queued';

-- 用于检测卡死的 running 任务
CREATE INDEX IF NOT EXISTS idx_recon_execution_queue_running
    ON recon_execution_queue (started_at ASC)
    WHERE status = 'running';
