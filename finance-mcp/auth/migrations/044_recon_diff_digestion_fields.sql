-- 044_recon_diff_digestion_fields.sql
-- 差异消化:exceptions 加复核审计字段;runs 加复核轮次/时间。
ALTER TABLE public.execution_run_exceptions
    ADD COLUMN IF NOT EXISTS review_round integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS resolved_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS resolved_to character varying(40) DEFAULT '';

ALTER TABLE public.execution_runs
    ADD COLUMN IF NOT EXISTS review_round integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_resolved_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS resolution_summary_json jsonb NOT NULL DEFAULT '{}'::jsonb;

-- 消化复核工作清单按 (run_id, is_closed) 拉取
CREATE INDEX IF NOT EXISTS idx_run_exceptions_run_open
    ON public.execution_run_exceptions (run_id, is_closed);
