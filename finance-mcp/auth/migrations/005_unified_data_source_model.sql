CREATE TABLE IF NOT EXISTS public.data_sources (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    source_kind character varying(30) NOT NULL,
    domain_type character varying(30) NOT NULL,
    provider_code character varying(80) NOT NULL,
    execution_mode character varying(20) DEFAULT 'deterministic'::character varying NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT data_sources_source_kind_check CHECK (
        (source_kind)::text = ANY (
            ARRAY[
                ('platform_oauth'::character varying)::text,
                ('database'::character varying)::text,
                ('api'::character varying)::text,
                ('file'::character varying)::text,
                ('browser'::character varying)::text,
                ('desktop_cli'::character varying)::text
            ]
        )
    ),
    CONSTRAINT data_sources_domain_type_check CHECK (
        (domain_type)::text = ANY (
            ARRAY[
                ('ecommerce'::character varying)::text,
                ('bank'::character varying)::text,
                ('finance_mid'::character varying)::text,
                ('erp'::character varying)::text,
                ('supplier'::character varying)::text,
                ('internal_business'::character varying)::text
            ]
        )
    ),
    CONSTRAINT data_sources_execution_mode_check CHECK (
        (execution_mode)::text = ANY (
            ARRAY[
                ('deterministic'::character varying)::text,
                ('agent_assisted'::character varying)::text
            ]
        )
    ),
    CONSTRAINT data_sources_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('active'::character varying)::text,
                ('disabled'::character varying)::text,
                ('deleted'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.data_source_credentials (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    credential_type character varying(30) DEFAULT 'default'::character varying NOT NULL,
    secret_payload text DEFAULT ''::text NOT NULL,
    secret_version integer DEFAULT 1 NOT NULL,
    secret_updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    extra jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.data_source_configs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    config_type character varying(30) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT data_source_configs_type_check CHECK (
        (config_type)::text = ANY (
            ARRAY[
                ('connection'::character varying)::text,
                ('extract'::character varying)::text,
                ('mapping'::character varying)::text,
                ('runtime'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.sync_jobs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    trigger_mode character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    resource_key character varying(100) DEFAULT 'default'::character varying NOT NULL,
    window_start timestamp with time zone,
    window_end timestamp with time zone,
    idempotency_key character varying(255),
    job_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    request_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    checkpoint_before jsonb DEFAULT '{}'::jsonb NOT NULL,
    checkpoint_after jsonb DEFAULT '{}'::jsonb NOT NULL,
    active_snapshot_id uuid,
    published_snapshot_id uuid,
    current_attempt integer DEFAULT 0 NOT NULL,
    error_message text DEFAULT ''::text NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT sync_jobs_trigger_mode_check CHECK (
        (trigger_mode)::text = ANY (
            ARRAY[
                ('manual'::character varying)::text,
                ('scheduled'::character varying)::text,
                ('event'::character varying)::text,
                ('retry'::character varying)::text
            ]
        )
    ),
    CONSTRAINT sync_jobs_status_check CHECK (
        (job_status)::text = ANY (
            ARRAY[
                ('pending'::character varying)::text,
                ('running'::character varying)::text,
                ('success'::character varying)::text,
                ('failed'::character varying)::text,
                ('cancelled'::character varying)::text,
                ('partial'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.sync_job_attempts (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    sync_job_id uuid NOT NULL,
    attempt_no integer NOT NULL,
    attempt_status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    finished_at timestamp with time zone,
    error_message text DEFAULT ''::text NOT NULL,
    metrics jsonb DEFAULT '{}'::jsonb NOT NULL,
    checkpoint_before jsonb DEFAULT '{}'::jsonb NOT NULL,
    checkpoint_after jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT sync_job_attempts_status_check CHECK (
        (attempt_status)::text = ANY (
            ARRAY[
                ('running'::character varying)::text,
                ('success'::character varying)::text,
                ('failed'::character varying)::text,
                ('cancelled'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.dataset_bindings (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    binding_scope character varying(30) DEFAULT 'recon'::character varying NOT NULL,
    binding_code character varying(128) NOT NULL,
    binding_name character varying(255) DEFAULT ''::character varying NOT NULL,
    data_source_id uuid NOT NULL,
    resource_key character varying(100) DEFAULT 'default'::character varying NOT NULL,
    role_code character varying(30) DEFAULT 'source'::character varying NOT NULL,
    is_required boolean DEFAULT true NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    filter_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    mapping_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT dataset_bindings_scope_check CHECK (
        (binding_scope)::text = ANY (
            ARRAY[
                ('recon'::character varying)::text,
                ('proc'::character varying)::text,
                ('exception'::character varying)::text,
                ('generic'::character varying)::text
            ]
        )
    ),
    CONSTRAINT dataset_bindings_role_check CHECK (
        (role_code)::text = ANY (
            ARRAY[
                ('source'::character varying)::text,
                ('target'::character varying)::text,
                ('aux'::character varying)::text,
                ('input'::character varying)::text,
                ('output'::character varying)::text
            ]
        )
    ),
    CONSTRAINT dataset_bindings_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('active'::character varying)::text,
                ('disabled'::character varying)::text,
                ('deleted'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.data_source_events (
    id bigserial PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    sync_job_id uuid,
    event_type character varying(50) NOT NULL,
    event_level character varying(10) DEFAULT 'info'::character varying NOT NULL,
    event_message text DEFAULT ''::text NOT NULL,
    event_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT data_source_events_level_check CHECK (
        (event_level)::text = ANY (
            ARRAY[
                ('info'::character varying)::text,
                ('warn'::character varying)::text,
                ('error'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_sources_company_id_fkey') THEN
        ALTER TABLE ONLY public.data_sources
            ADD CONSTRAINT data_sources_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_credentials_company_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_credentials
            ADD CONSTRAINT data_source_credentials_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_credentials_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_credentials
            ADD CONSTRAINT data_source_credentials_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_configs_company_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_configs
            ADD CONSTRAINT data_source_configs_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_configs_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_configs
            ADD CONSTRAINT data_source_configs_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sync_jobs_company_id_fkey') THEN
        ALTER TABLE ONLY public.sync_jobs
            ADD CONSTRAINT sync_jobs_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sync_jobs_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.sync_jobs
            ADD CONSTRAINT sync_jobs_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sync_job_attempts_company_id_fkey') THEN
        ALTER TABLE ONLY public.sync_job_attempts
            ADD CONSTRAINT sync_job_attempts_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sync_job_attempts_sync_job_id_fkey') THEN
        ALTER TABLE ONLY public.sync_job_attempts
            ADD CONSTRAINT sync_job_attempts_sync_job_id_fkey
            FOREIGN KEY (sync_job_id) REFERENCES public.sync_jobs(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_bindings_company_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_bindings
            ADD CONSTRAINT dataset_bindings_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_bindings_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_bindings
            ADD CONSTRAINT dataset_bindings_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_events_company_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_events
            ADD CONSTRAINT data_source_events_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_events_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_events
            ADD CONSTRAINT data_source_events_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_events_sync_job_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_events
            ADD CONSTRAINT data_source_events_sync_job_id_fkey
            FOREIGN KEY (sync_job_id) REFERENCES public.sync_jobs(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_sources_company_code_key') THEN
        ALTER TABLE ONLY public.data_sources
            ADD CONSTRAINT data_sources_company_code_key UNIQUE (company_id, code);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_credentials_source_type_key') THEN
        ALTER TABLE ONLY public.data_source_credentials
            ADD CONSTRAINT data_source_credentials_source_type_key UNIQUE (data_source_id, credential_type);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sync_job_attempts_job_attempt_no_key') THEN
        ALTER TABLE ONLY public.sync_job_attempts
            ADD CONSTRAINT sync_job_attempts_job_attempt_no_key UNIQUE (sync_job_id, attempt_no);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_bindings_scope_code_source_key') THEN
        ALTER TABLE ONLY public.dataset_bindings
            ADD CONSTRAINT dataset_bindings_scope_code_source_key
            UNIQUE (company_id, binding_scope, binding_code, role_code, data_source_id, resource_key);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_data_source_configs_active_type
    ON public.data_source_configs USING btree (data_source_id, config_type)
    WHERE (is_active = true);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_jobs_idempotency
    ON public.sync_jobs USING btree (company_id, data_source_id, idempotency_key)
    WHERE (idempotency_key IS NOT NULL);

CREATE INDEX IF NOT EXISTS idx_data_sources_company_status
    ON public.data_sources USING btree (company_id, status, source_kind, provider_code);

CREATE INDEX IF NOT EXISTS idx_sync_jobs_company_source_status
    ON public.sync_jobs USING btree (company_id, data_source_id, job_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_job_attempts_job_status
    ON public.sync_job_attempts USING btree (sync_job_id, attempt_status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_dataset_bindings_scope_code
    ON public.dataset_bindings USING btree (company_id, binding_scope, binding_code, status);

CREATE INDEX IF NOT EXISTS idx_data_source_events_source_created
    ON public.data_source_events USING btree (data_source_id, created_at DESC);

DROP TRIGGER IF EXISTS update_data_sources_updated_at ON public.data_sources;
CREATE TRIGGER update_data_sources_updated_at
    BEFORE UPDATE ON public.data_sources
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_data_source_credentials_updated_at ON public.data_source_credentials;
CREATE TRIGGER update_data_source_credentials_updated_at
    BEFORE UPDATE ON public.data_source_credentials
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_data_source_configs_updated_at ON public.data_source_configs;
CREATE TRIGGER update_data_source_configs_updated_at
    BEFORE UPDATE ON public.data_source_configs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_sync_jobs_updated_at ON public.sync_jobs;
CREATE TRIGGER update_sync_jobs_updated_at
    BEFORE UPDATE ON public.sync_jobs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_sync_job_attempts_updated_at ON public.sync_job_attempts;
CREATE TRIGGER update_sync_job_attempts_updated_at
    BEFORE UPDATE ON public.sync_job_attempts
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_dataset_bindings_updated_at ON public.dataset_bindings;
CREATE TRIGGER update_dataset_bindings_updated_at
    BEFORE UPDATE ON public.dataset_bindings
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
