CREATE INDEX IF NOT EXISTS idx_handoff_sessions_agent_status
    ON browser_handoff_sessions(agent_id, status);

CREATE INDEX IF NOT EXISTS idx_handoff_sessions_expires_at
    ON browser_handoff_sessions(expires_at);
