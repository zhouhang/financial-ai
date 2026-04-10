-- 009: 对账方案 + 运行计划 + 执行记录模型
-- 目标：
-- 1) 新增 execution_schemes / execution_run_plans / execution_runs / execution_run_exceptions
-- 2) 支持 scheme + run_plan + run + exception 分层模型
-- 3) execution_runs 支持 failed_stage / failed_reason / subtasks_json（采集作为 run 内子任务）

-- ------------------------------------------------------------
-- execution_schemes
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.execution_schemes (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    scheme_code character varying(120) NOT NULL,
    scheme_name character varying(255) NOT NULL,
    scheme_type character varying(50) DEFAULT 'recon'::character varying NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    file_rule_code character varying(120) DEFAULT ''::character varying NOT NULL,
    proc_rule_code character varying(120) DEFAULT ''::character varying NOT NULL,
    recon_rule_code character varying(120) DEFAULT ''::character varying NOT NULL,
    scheme_meta_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT execution_schemes_pkey PRIMARY KEY (id),
    CONSTRAINT execution_schemes_scheme_type_check CHECK (
        (scheme_type)::text = ANY (
            ARRAY[
                ('recon'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'execution_schemes_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.execution_schemes
            ADD CONSTRAINT execution_schemes_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_schemes_company_scheme_code
    ON public.execution_schemes USING btree (company_id, scheme_code);

CREATE INDEX IF NOT EXISTS idx_execution_schemes_company_enabled_updated
    ON public.execution_schemes USING btree (company_id, is_enabled, updated_at DESC);

DROP TRIGGER IF EXISTS update_execution_schemes_updated_at ON public.execution_schemes;
CREATE TRIGGER update_execution_schemes_updated_at
    BEFORE UPDATE ON public.execution_schemes
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ------------------------------------------------------------
-- execution_run_plans
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.execution_run_plans (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    plan_code character varying(120) NOT NULL,
    plan_name character varying(255) NOT NULL,
    scheme_code character varying(120) NOT NULL,
    schedule_type character varying(30) DEFAULT 'daily'::character varying NOT NULL,
    schedule_expr character varying(255) DEFAULT ''::character varying NOT NULL,
    biz_date_offset character varying(30) DEFAULT 'previous_day'::character varying NOT NULL,
    input_bindings_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    channel_config_id uuid,
    owner_mapping_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    plan_meta_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_by uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT execution_run_plans_pkey PRIMARY KEY (id),
    CONSTRAINT execution_run_plans_schedule_type_check CHECK (
        (schedule_type)::text = ANY (
            ARRAY[
                ('manual_trigger'::character varying)::text,
                ('daily'::character varying)::text,
                ('weekly'::character varying)::text,
                ('cron'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'execution_run_plans_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.execution_run_plans
            ADD CONSTRAINT execution_run_plans_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'execution_run_plans_channel_config_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.execution_run_plans
            ADD CONSTRAINT execution_run_plans_channel_config_id_fkey
            FOREIGN KEY (channel_config_id) REFERENCES public.company_channel_configs(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_run_plans_company_plan_code
    ON public.execution_run_plans USING btree (company_id, plan_code);

CREATE INDEX IF NOT EXISTS idx_execution_run_plans_company_scheme_enabled
    ON public.execution_run_plans USING btree (company_id, scheme_code, is_enabled, updated_at DESC);

DROP TRIGGER IF EXISTS update_execution_run_plans_updated_at ON public.execution_run_plans;
CREATE TRIGGER update_execution_run_plans_updated_at
    BEFORE UPDATE ON public.execution_run_plans
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ------------------------------------------------------------
-- execution_runs
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.execution_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    run_code character varying(120) NOT NULL,
    scheme_code character varying(120) NOT NULL,
    plan_code character varying(120),
    scheme_type character varying(50) DEFAULT 'recon'::character varying NOT NULL,
    trigger_type character varying(20) DEFAULT 'chat'::character varying NOT NULL,
    entry_mode character varying(20) DEFAULT 'file'::character varying NOT NULL,
    execution_status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    failed_stage character varying(40) DEFAULT ''::character varying NOT NULL,
    failed_reason text DEFAULT ''::text NOT NULL,
    run_context_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_snapshot_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    subtasks_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    proc_result_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    recon_result_summary_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    artifacts_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    anomaly_count integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT execution_runs_pkey PRIMARY KEY (id),
    CONSTRAINT execution_runs_scheme_type_check CHECK (
        (scheme_type)::text = ANY (
            ARRAY[
                ('recon'::character varying)::text
            ]
        )
    ),
    CONSTRAINT execution_runs_trigger_type_check CHECK (
        (trigger_type)::text = ANY (
            ARRAY[
                ('chat'::character varying)::text,
                ('schedule'::character varying)::text,
                ('api'::character varying)::text
            ]
        )
    ),
    CONSTRAINT execution_runs_entry_mode_check CHECK (
        (entry_mode)::text = ANY (
            ARRAY[
                ('file'::character varying)::text,
                ('dataset'::character varying)::text
            ]
        )
    ),
    CONSTRAINT execution_runs_execution_status_check CHECK (
        (execution_status)::text = ANY (
            ARRAY[
                ('running'::character varying)::text,
                ('success'::character varying)::text,
                ('failed'::character varying)::text
            ]
        )
    ),
    CONSTRAINT execution_runs_anomaly_count_check CHECK (anomaly_count >= 0)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'execution_runs_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.execution_runs
            ADD CONSTRAINT execution_runs_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_runs_company_run_code
    ON public.execution_runs USING btree (company_id, run_code);

CREATE INDEX IF NOT EXISTS idx_execution_runs_company_created
    ON public.execution_runs USING btree (company_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_execution_runs_company_scheme
    ON public.execution_runs USING btree (company_id, scheme_code, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_execution_runs_company_plan
    ON public.execution_runs USING btree (company_id, plan_code, created_at DESC)
    WHERE plan_code IS NOT NULL;

DROP TRIGGER IF EXISTS update_execution_runs_updated_at ON public.execution_runs;
CREATE TRIGGER update_execution_runs_updated_at
    BEFORE UPDATE ON public.execution_runs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ------------------------------------------------------------
-- execution_run_exceptions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.execution_run_exceptions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    run_id uuid NOT NULL,
    scheme_code character varying(120) NOT NULL,
    anomaly_key character varying(255) NOT NULL,
    anomaly_type character varying(100) DEFAULT ''::character varying NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    detail_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    owner_name character varying(100) DEFAULT ''::character varying NOT NULL,
    owner_identifier character varying(200) DEFAULT ''::character varying NOT NULL,
    owner_contact_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    reminder_status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    processing_status character varying(40) DEFAULT 'pending'::character varying NOT NULL,
    fix_status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    latest_feedback text DEFAULT ''::text NOT NULL,
    feedback_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_closed boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT execution_run_exceptions_pkey PRIMARY KEY (id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'execution_run_exceptions_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.execution_run_exceptions
            ADD CONSTRAINT execution_run_exceptions_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'execution_run_exceptions_run_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.execution_run_exceptions
            ADD CONSTRAINT execution_run_exceptions_run_id_fkey
            FOREIGN KEY (run_id) REFERENCES public.execution_runs(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_run_exceptions_run_anomaly
    ON public.execution_run_exceptions USING btree (run_id, anomaly_key);

CREATE INDEX IF NOT EXISTS idx_execution_run_exceptions_company_run
    ON public.execution_run_exceptions USING btree (company_id, run_id, created_at DESC);

DROP TRIGGER IF EXISTS update_execution_run_exceptions_updated_at ON public.execution_run_exceptions;
CREATE TRIGGER update_execution_run_exceptions_updated_at
    BEFORE UPDATE ON public.execution_run_exceptions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
