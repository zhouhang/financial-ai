-- recon digest foundation tables consumed by public boss/finance detail pages.
-- These tables are generic report artifacts. Industry-specific source fields stay
-- in domain adapters and never appear in this schema.

CREATE TABLE IF NOT EXISTS public.recon_digest (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    subscription_id uuid,
    company_id uuid NOT NULL,
    period character varying(32) DEFAULT 'daily'::character varying NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    structured jsonb DEFAULT '{}'::jsonb NOT NULL,
    narrative text DEFAULT ''::text NOT NULL,
    completeness jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'draft'::character varying NOT NULL,
    delivered_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest
            ADD CONSTRAINT recon_digest_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_digest_company_period
    ON public.recon_digest (company_id, period_start DESC, period_end DESC, status);

CREATE TABLE IF NOT EXISTS public.canonical_recon_line (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    domain character varying(32) DEFAULT 'ecom'::character varying NOT NULL,
    execution_run_id uuid,
    exception_id uuid,
    plan_code character varying(128) NOT NULL,
    plan_name_snapshot text DEFAULT ''::text NOT NULL,
    recon_type character varying(16) NOT NULL,
    biz_date date NOT NULL,
    order_no text DEFAULT ''::text NOT NULL,
    channel text DEFAULT ''::text NOT NULL,
    receivable_amount numeric DEFAULT 0 NOT NULL,
    settled_amount numeric DEFAULT 0 NOT NULL,
    refund_amount numeric DEFAULT 0 NOT NULL,
    left_amount numeric DEFAULT 0 NOT NULL,
    right_amount numeric DEFAULT 0 NOT NULL,
    diff_amount numeric DEFAULT 0 NOT NULL,
    pay_time timestamp with time zone,
    settle_time timestamp with time zone,
    finish_time timestamp with time zone,
    match_status character varying(32) DEFAULT ''::character varying NOT NULL,
    order_status text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_recon_line_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.canonical_recon_line
            ADD CONSTRAINT canonical_recon_line_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_recon_line_execution_run_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.canonical_recon_line
            ADD CONSTRAINT canonical_recon_line_execution_run_id_fkey
            FOREIGN KEY (execution_run_id) REFERENCES public.execution_runs(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_recon_line_exception_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.canonical_recon_line
            ADD CONSTRAINT canonical_recon_line_exception_id_fkey
            FOREIGN KEY (exception_id) REFERENCES public.execution_run_exceptions(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_canonical_recon_line_company_biz_domain
    ON public.canonical_recon_line (company_id, biz_date, domain);
CREATE INDEX IF NOT EXISTS idx_canonical_recon_line_plan_biz
    ON public.canonical_recon_line (plan_code, biz_date);
CREATE INDEX IF NOT EXISTS idx_canonical_recon_line_execution_run
    ON public.canonical_recon_line (execution_run_id);
CREATE INDEX IF NOT EXISTS idx_canonical_recon_line_exception
    ON public.canonical_recon_line (exception_id);

CREATE TABLE IF NOT EXISTS public.recon_attribution (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    line_id uuid NOT NULL,
    rule_code text DEFAULT ''::text NOT NULL,
    reason_code text DEFAULT ''::text NOT NULL,
    is_true_diff boolean,
    confidence numeric,
    explain_text text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_attribution_line_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_attribution
            ADD CONSTRAINT recon_attribution_line_id_fkey
            FOREIGN KEY (line_id) REFERENCES public.canonical_recon_line(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_attribution_line_id
    ON public.recon_attribution (line_id);

CREATE TABLE IF NOT EXISTS public.recon_alert (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    domain character varying(32) DEFAULT 'ecom'::character varying NOT NULL,
    biz_date date NOT NULL,
    plan_code character varying(128) NOT NULL,
    plan_name_snapshot text DEFAULT ''::text NOT NULL,
    alert_code character varying(128) NOT NULL,
    severity character varying(32) DEFAULT 'warning'::character varying NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    explain_text text DEFAULT ''::text NOT NULL,
    amount numeric DEFAULT 0 NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'open'::character varying NOT NULL,
    first_seen_biz_date date,
    last_seen_biz_date date,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_alert_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_alert
            ADD CONSTRAINT recon_alert_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_alert_company_biz_domain
    ON public.recon_alert (company_id, biz_date, domain);
CREATE INDEX IF NOT EXISTS idx_recon_alert_plan_code
    ON public.recon_alert (plan_code, biz_date);

DROP TRIGGER IF EXISTS update_recon_digest_updated_at ON public.recon_digest;
CREATE TRIGGER update_recon_digest_updated_at
    BEFORE UPDATE ON public.recon_digest
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_canonical_recon_line_updated_at ON public.canonical_recon_line;
CREATE TRIGGER update_canonical_recon_line_updated_at
    BEFORE UPDATE ON public.canonical_recon_line
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_recon_alert_updated_at ON public.recon_alert;
CREATE TRIGGER update_recon_alert_updated_at
    BEFORE UPDATE ON public.recon_alert
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
