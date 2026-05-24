CREATE TABLE IF NOT EXISTS browser_handoff_sessions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_job_id        uuid NOT NULL,
    company_id         uuid NOT NULL,
    data_source_id     uuid,
    agent_id           varchar(128) NOT NULL DEFAULT '',
    profile_key        varchar(256) NOT NULL DEFAULT '',
    status             varchar(32)  NOT NULL DEFAULT 'pending',
    reason             varchar(64)  NOT NULL DEFAULT '',
    channel_config_id  uuid,
    claimed_by_user_id uuid,
    claimed_at         timestamptz,
    completed_at       timestamptz,
    expires_at         timestamptz NOT NULL,
    audit_events       jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_handoff_sessions_sync_job ON browser_handoff_sessions(sync_job_id);
CREATE INDEX IF NOT EXISTS idx_handoff_sessions_company_status ON browser_handoff_sessions(company_id, status);
