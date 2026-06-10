-- recon_period_rollup: 三件套+底稿金额指标唯一可信全量聚合落点。
-- 覆盖全量付款日 cohort（含平账 matched_exact），与只落差异行的 canonical_recon_line
-- 及会被采样截断的 execution_run_exceptions 解耦。
CREATE TABLE IF NOT EXISTS public.recon_period_rollup (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    domain character varying(32) DEFAULT 'ecom'::character varying NOT NULL,
    plan_code character varying(128) NOT NULL,
    plan_name_snapshot text DEFAULT ''::text NOT NULL,
    recon_type character varying(16) NOT NULL,
    biz_date date NOT NULL,
    as_of_ts timestamp with time zone NOT NULL,
    receivable_amount_total numeric DEFAULT 0 NOT NULL,
    refund_amount_total numeric DEFAULT 0 NOT NULL,
    net_receivable_amount_total numeric DEFAULT 0 NOT NULL,
    settled_amount_total numeric DEFAULT 0 NOT NULL,
    normal_in_transit_amount_total numeric DEFAULT 0 NOT NULL,
    stuck_amount_total numeric DEFAULT 0 NOT NULL,
    net_deduction_total numeric DEFAULT 0 NOT NULL,
    net_deduction_rate numeric,
    diff_amount_total numeric DEFAULT 0 NOT NULL,
    cohort_order_count integer DEFAULT 0 NOT NULL,
    settled_order_count integer DEFAULT 0 NOT NULL,
    normal_in_transit_count integer DEFAULT 0 NOT NULL,
    stuck_order_count integer DEFAULT 0 NOT NULL,
    matched_with_diff_count integer DEFAULT 0 NOT NULL,
    source_only_count integer DEFAULT 0 NOT NULL,
    target_only_count integer DEFAULT 0 NOT NULL,
    payback_days_sum numeric DEFAULT 0 NOT NULL,
    payback_days_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'recon_period_rollup_unique') THEN
        ALTER TABLE ONLY public.recon_period_rollup
            ADD CONSTRAINT recon_period_rollup_unique
            UNIQUE (company_id, plan_code, biz_date, recon_type);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_period_rollup_company_biz
    ON public.recon_period_rollup (company_id, biz_date);
CREATE INDEX IF NOT EXISTS idx_recon_period_rollup_plan_biz
    ON public.recon_period_rollup (plan_code, biz_date);
