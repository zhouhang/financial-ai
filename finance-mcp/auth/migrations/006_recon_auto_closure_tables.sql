-- 006: 自动对账任务与异常闭环模型
-- 目标：
-- 1) 扩展 company_channel_configs 以支持公司级协作通道标准字段
-- 2) 新增 recon_auto_tasks / recon_auto_runs / recon_exception_tasks / recon_run_jobs
-- 3) 明确 run（业务批次）与 run_job（短动作执行）拆分

-- ------------------------------------------------------------
-- company_channel_configs 扩展（兼容旧字段 provider/name/client_id/...）
-- ------------------------------------------------------------
ALTER TABLE IF EXISTS public.company_channel_configs
    ADD COLUMN IF NOT EXISTS channel_type character varying(50),
    ADD COLUMN IF NOT EXISTS channel_name character varying(255),
    ADD COLUMN IF NOT EXISTS credential_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    ADD COLUMN IF NOT EXISTS default_delivery_mode character varying(30) DEFAULT 'bot'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS receipt_enabled boolean DEFAULT false NOT NULL;

UPDATE public.company_channel_configs
SET channel_type = provider
WHERE channel_type IS NULL OR channel_type = '';

UPDATE public.company_channel_configs
SET channel_name = COALESCE(NULLIF(name, ''), provider)
WHERE channel_name IS NULL OR channel_name = '';

UPDATE public.company_channel_configs
SET credential_json = jsonb_strip_nulls(
    jsonb_build_object(
        'client_id', NULLIF(client_id, ''),
        'client_secret', NULLIF(client_secret, ''),
        'robot_code', NULLIF(robot_code, '')
    )
)
WHERE credential_json = '{}'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'company_channel_configs_default_delivery_mode_check'
    ) THEN
        ALTER TABLE ONLY public.company_channel_configs
            ADD CONSTRAINT company_channel_configs_default_delivery_mode_check
            CHECK (
                (default_delivery_mode)::text = ANY (
                    ARRAY[
                        ('bot'::character varying)::text,
                        ('todo'::character varying)::text,
                        ('card'::character varying)::text
                    ]
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_company_channel_configs_company_channel_type_enabled
    ON public.company_channel_configs USING btree (company_id, channel_type, is_enabled);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_channel_configs_company_channel_type_default
    ON public.company_channel_configs USING btree (company_id, channel_type)
    WHERE (is_default = true);

-- ------------------------------------------------------------
-- recon_auto_tasks: 自动运行任务定义
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recon_auto_tasks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    task_code character varying(100) DEFAULT ''::character varying NOT NULL,
    task_name character varying(255) NOT NULL,
    rule_code character varying(100) NOT NULL,
    rule_id character varying(120) DEFAULT ''::character varying NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    schedule_type character varying(30) DEFAULT 'daily'::character varying NOT NULL,
    schedule_expr character varying(255) DEFAULT ''::character varying NOT NULL,
    biz_date_offset character varying(20) DEFAULT 'T-1'::character varying NOT NULL,
    max_wait_until character varying(30) DEFAULT ''::character varying NOT NULL,
    retry_policy_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    input_mode character varying(30) DEFAULT 'bound_source'::character varying NOT NULL,
    bound_data_source_ids jsonb DEFAULT '[]'::jsonb NOT NULL,
    completeness_policy_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    auto_create_exceptions boolean DEFAULT true NOT NULL,
    auto_remind boolean DEFAULT false NOT NULL,
    channel_config_id uuid,
    reminder_policy_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    owner_mapping_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    task_meta_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT recon_auto_tasks_pkey PRIMARY KEY (id),
    CONSTRAINT recon_auto_tasks_schedule_type_check CHECK (
        (schedule_type)::text = ANY (
            ARRAY[
                ('daily'::character varying)::text,
                ('weekly'::character varying)::text,
                ('monthly'::character varying)::text,
                ('cron'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_auto_tasks_input_mode_check CHECK (
        (input_mode)::text = ANY (
            ARRAY[
                ('upload_template'::character varying)::text,
                ('bound_source'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_auto_tasks_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_auto_tasks
            ADD CONSTRAINT recon_auto_tasks_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_auto_tasks_channel_config_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_auto_tasks
            ADD CONSTRAINT recon_auto_tasks_channel_config_id_fkey
            FOREIGN KEY (channel_config_id) REFERENCES public.company_channel_configs(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_recon_auto_tasks_company_task_code
    ON public.recon_auto_tasks USING btree (company_id, task_code)
    WHERE task_code <> ''::character varying;

CREATE INDEX IF NOT EXISTS idx_recon_auto_tasks_company_enabled_updated
    ON public.recon_auto_tasks USING btree (company_id, is_enabled, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_recon_auto_tasks_company_rule
    ON public.recon_auto_tasks USING btree (company_id, rule_code);

DROP TRIGGER IF EXISTS update_recon_auto_tasks_updated_at ON public.recon_auto_tasks;
CREATE TRIGGER update_recon_auto_tasks_updated_at
    BEFORE UPDATE ON public.recon_auto_tasks
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ------------------------------------------------------------
-- recon_auto_runs: 自动运行批次（run）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recon_auto_runs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    auto_task_id uuid NOT NULL,
    biz_date date NOT NULL,
    run_status character varying(40) DEFAULT 'scheduled'::character varying NOT NULL,
    readiness_status character varying(30) DEFAULT 'waiting_data'::character varying NOT NULL,
    closure_status character varying(30) DEFAULT 'open'::character varying NOT NULL,
    trigger_mode character varying(30) DEFAULT 'cron'::character varying NOT NULL,
    run_no integer DEFAULT 1 NOT NULL,
    task_snapshot_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_snapshot_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    recon_result_summary_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    anomaly_count integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    error_message text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT recon_auto_runs_pkey PRIMARY KEY (id),
    CONSTRAINT recon_auto_runs_run_status_check CHECK (
        (run_status)::text = ANY (
            ARRAY[
                ('scheduled'::character varying)::text,
                ('waiting_data'::character varying)::text,
                ('ready'::character varying)::text,
                ('running_recon'::character varying)::text,
                ('recon_succeeded'::character varying)::text,
                ('recon_failed'::character varying)::text,
                ('exception_open'::character varying)::text,
                ('waiting_manual_fix'::character varying)::text,
                ('waiting_verify'::character varying)::text,
                ('verifying'::character varying)::text,
                ('closed'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_auto_runs_readiness_status_check CHECK (
        (readiness_status)::text = ANY (
            ARRAY[
                ('waiting_data'::character varying)::text,
                ('data_partial'::character varying)::text,
                ('data_ready'::character varying)::text,
                ('data_failed'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_auto_runs_closure_status_check CHECK (
        (closure_status)::text = ANY (
            ARRAY[
                ('open'::character varying)::text,
                ('in_progress'::character varying)::text,
                ('waiting_verify'::character varying)::text,
                ('closed'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_auto_runs_trigger_mode_check CHECK (
        (trigger_mode)::text = ANY (
            ARRAY[
                ('cron'::character varying)::text,
                ('manual'::character varying)::text,
                ('rerun'::character varying)::text,
                ('verify'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_auto_runs_run_no_check CHECK (run_no > 0),
    CONSTRAINT recon_auto_runs_anomaly_count_check CHECK (anomaly_count >= 0)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_auto_runs_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_auto_runs
            ADD CONSTRAINT recon_auto_runs_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_auto_runs_auto_task_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_auto_runs
            ADD CONSTRAINT recon_auto_runs_auto_task_id_fkey
            FOREIGN KEY (auto_task_id) REFERENCES public.recon_auto_tasks(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_recon_auto_runs_task_biz_date_run_no
    ON public.recon_auto_runs USING btree (auto_task_id, biz_date, run_no);

CREATE INDEX IF NOT EXISTS idx_recon_auto_runs_company_status_created
    ON public.recon_auto_runs USING btree (company_id, run_status, closure_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recon_auto_runs_company_biz_date
    ON public.recon_auto_runs USING btree (company_id, biz_date DESC, created_at DESC);

DROP TRIGGER IF EXISTS update_recon_auto_runs_updated_at ON public.recon_auto_runs;
CREATE TRIGGER update_recon_auto_runs_updated_at
    BEFORE UPDATE ON public.recon_auto_runs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ------------------------------------------------------------
-- recon_exception_tasks: 批次异常任务
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recon_exception_tasks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    auto_task_id uuid NOT NULL,
    auto_run_id uuid NOT NULL,
    anomaly_key character varying(255) NOT NULL,
    anomaly_type character varying(100) DEFAULT ''::character varying NOT NULL,
    summary text DEFAULT ''::text NOT NULL,
    detail_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    owner_name character varying(100) DEFAULT ''::character varying NOT NULL,
    owner_identifier character varying(200) DEFAULT ''::character varying NOT NULL,
    owner_contact_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    reminder_status character varying(30) DEFAULT 'not_sent'::character varying NOT NULL,
    processing_status character varying(40) DEFAULT 'new'::character varying NOT NULL,
    fix_status character varying(30) DEFAULT 'unknown'::character varying NOT NULL,
    latest_feedback text DEFAULT ''::text NOT NULL,
    feedback_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    verify_required boolean DEFAULT true NOT NULL,
    verify_run_id uuid,
    last_verified_at timestamp with time zone,
    is_closed boolean DEFAULT false NOT NULL,
    closed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT recon_exception_tasks_pkey PRIMARY KEY (id),
    CONSTRAINT recon_exception_tasks_reminder_status_check CHECK (
        (reminder_status)::text = ANY (
            ARRAY[
                ('not_sent'::character varying)::text,
                ('sent'::character varying)::text,
                ('failed'::character varying)::text,
                ('acknowledged'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_exception_tasks_processing_status_check CHECK (
        (processing_status)::text = ANY (
            ARRAY[
                ('new'::character varying)::text,
                ('reminded'::character varying)::text,
                ('processing'::character varying)::text,
                ('fixed_pending_verify'::character varying)::text,
                ('verified_closed'::character varying)::text,
                ('reopened'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_exception_tasks_fix_status_check CHECK (
        (fix_status)::text = ANY (
            ARRAY[
                ('unknown'::character varying)::text,
                ('pending'::character varying)::text,
                ('fixed'::character varying)::text,
                ('not_applicable'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_exception_tasks_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_exception_tasks
            ADD CONSTRAINT recon_exception_tasks_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_exception_tasks_auto_task_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_exception_tasks
            ADD CONSTRAINT recon_exception_tasks_auto_task_id_fkey
            FOREIGN KEY (auto_task_id) REFERENCES public.recon_auto_tasks(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_exception_tasks_auto_run_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_exception_tasks
            ADD CONSTRAINT recon_exception_tasks_auto_run_id_fkey
            FOREIGN KEY (auto_run_id) REFERENCES public.recon_auto_runs(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_exception_tasks_verify_run_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_exception_tasks
            ADD CONSTRAINT recon_exception_tasks_verify_run_id_fkey
            FOREIGN KEY (verify_run_id) REFERENCES public.recon_auto_runs(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_exception_tasks_auto_run_anomaly_key_key'
    ) THEN
        ALTER TABLE ONLY public.recon_exception_tasks
            ADD CONSTRAINT recon_exception_tasks_auto_run_anomaly_key_key
            UNIQUE (auto_run_id, anomaly_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_exception_tasks_run_status
    ON public.recon_exception_tasks USING btree (auto_run_id, processing_status, is_closed, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recon_exception_tasks_company_owner
    ON public.recon_exception_tasks USING btree (company_id, owner_identifier, processing_status, is_closed);

CREATE INDEX IF NOT EXISTS idx_recon_exception_tasks_company_type_created
    ON public.recon_exception_tasks USING btree (company_id, anomaly_type, created_at DESC);

DROP TRIGGER IF EXISTS update_recon_exception_tasks_updated_at ON public.recon_exception_tasks;
CREATE TRIGGER update_recon_exception_tasks_updated_at
    BEFORE UPDATE ON public.recon_exception_tasks
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ------------------------------------------------------------
-- recon_run_jobs: run 下短动作执行记录（job）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.recon_run_jobs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    auto_run_id uuid NOT NULL,
    job_type character varying(50) NOT NULL,
    job_status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    attempt_no integer DEFAULT 1 NOT NULL,
    idempotency_key character varying(255) DEFAULT ''::character varying NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    input_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_message text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT recon_run_jobs_pkey PRIMARY KEY (id),
    CONSTRAINT recon_run_jobs_job_status_check CHECK (
        (job_status)::text = ANY (
            ARRAY[
                ('queued'::character varying)::text,
                ('running'::character varying)::text,
                ('succeeded'::character varying)::text,
                ('failed'::character varying)::text,
                ('cancelled'::character varying)::text
            ]
        )
    ),
    CONSTRAINT recon_run_jobs_attempt_no_check CHECK (attempt_no > 0)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_run_jobs_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_run_jobs
            ADD CONSTRAINT recon_run_jobs_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_run_jobs_auto_run_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_run_jobs
            ADD CONSTRAINT recon_run_jobs_auto_run_id_fkey
            FOREIGN KEY (auto_run_id) REFERENCES public.recon_auto_runs(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_recon_run_jobs_auto_run_idempotency
    ON public.recon_run_jobs USING btree (auto_run_id, job_type, idempotency_key)
    WHERE idempotency_key <> ''::character varying;

CREATE INDEX IF NOT EXISTS idx_recon_run_jobs_run_type_created
    ON public.recon_run_jobs USING btree (auto_run_id, job_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recon_run_jobs_company_status_created
    ON public.recon_run_jobs USING btree (company_id, job_status, created_at DESC);

DROP TRIGGER IF EXISTS update_recon_run_jobs_updated_at ON public.recon_run_jobs;
CREATE TRIGGER update_recon_run_jobs_updated_at
    BEFORE UPDATE ON public.recon_run_jobs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
