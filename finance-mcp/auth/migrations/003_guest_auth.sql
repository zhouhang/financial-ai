--
-- Migration: Add guest_auth_tokens table for temporary authentication
-- Change: guest-reconciliation-flow
-- Generated: 2026-02
--

-- =============================================================================
-- 1. Create guest_auth_tokens table
-- =============================================================================

CREATE TABLE public.guest_auth_tokens (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    token character varying(64) NOT NULL,
    session_id character varying(64),
    usage_count integer DEFAULT 0,
    max_usage integer DEFAULT 3,
    ip_address inet,
    user_agent text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT guest_auth_tokens_pkey PRIMARY KEY (id)
);

COMMENT ON TABLE public.guest_auth_tokens IS '游客临时认证token表';
COMMENT ON COLUMN public.guest_auth_tokens.token IS '唯一token值';
COMMENT ON COLUMN public.guest_auth_tokens.session_id IS '关联的会话ID';
COMMENT ON COLUMN public.guest_auth_tokens.usage_count IS '已使用次数';
COMMENT ON COLUMN public.guest_auth_tokens.max_usage IS '最大使用次数';
COMMENT ON COLUMN public.guest_auth_tokens.ip_address IS '用户IP地址';
COMMENT ON COLUMN public.guest_auth_tokens.expires_at IS '过期时间';

-- Indexes
CREATE INDEX idx_guest_tokens_token ON public.guest_auth_tokens USING btree (token);
CREATE INDEX idx_guest_tokens_session ON public.guest_auth_tokens USING btree (session_id);
CREATE INDEX idx_guest_tokens_expires ON public.guest_auth_tokens USING btree (expires_at);

-- =============================================================================
-- 2. Add is_recommended field to reconciliation_rules
-- =============================================================================

ALTER TABLE public.reconciliation_rules 
ADD COLUMN IF NOT EXISTS is_recommended boolean DEFAULT false;

COMMENT ON COLUMN public.reconciliation_rules.is_recommended IS '是否为推荐规则';

CREATE INDEX idx_rules_is_recommended ON public.reconciliation_rules USING btree (is_recommended);
