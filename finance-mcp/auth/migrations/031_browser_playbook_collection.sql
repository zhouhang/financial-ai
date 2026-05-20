CREATE TABLE IF NOT EXISTS public.playbooks (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    playbook_id character varying(128) NOT NULL,
    version character varying(32) NOT NULL,
    title character varying(255) NOT NULL DEFAULT ''::character varying,
    description text NOT NULL DEFAULT ''::text,
    target jsonb NOT NULL DEFAULT '{}'::jsonb,
    params_schema jsonb NOT NULL DEFAULT '{}'::jsonb,
    playbook_body jsonb NOT NULL DEFAULT '{}'::jsonb,
    schema_check_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    replay_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    sample_data_path text NOT NULL DEFAULT ''::text,
    transcript_path text NOT NULL DEFAULT ''::text,
    canary_shop_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    emergency_page_changed boolean NOT NULL DEFAULT false,
    bypass_canary_reason text NOT NULL DEFAULT ''::text,
    created_by uuid,
    approved_by uuid,
    approved_at timestamptz,
    canary_started_at timestamptz,
    canary_completed_at timestamptz,
    status character varying(20) NOT NULL DEFAULT 'draft'::character varying,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT playbooks_status_check CHECK (
        status = ANY (ARRAY[
            'draft'::character varying,
            'replayed'::character varying,
            'approved'::character varying,
            'canary'::character varying,
            'active'::character varying,
            'deprecated'::character varying
        ])
    ),
    CONSTRAINT playbooks_company_playbook_version_key UNIQUE (company_id, playbook_id, version)
);

ALTER TABLE public.playbooks
    ADD COLUMN IF NOT EXISTS description text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS schema_check_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS replay_result jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS sample_data_path text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS transcript_path text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS canary_shop_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS emergency_page_changed boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS bypass_canary_reason text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS created_by uuid,
    ADD COLUMN IF NOT EXISTS approved_by uuid,
    ADD COLUMN IF NOT EXISTS approved_at timestamptz,
    ADD COLUMN IF NOT EXISTS canary_started_at timestamptz,
    ADD COLUMN IF NOT EXISTS canary_completed_at timestamptz;

ALTER TABLE public.playbooks
    ALTER COLUMN status SET DEFAULT 'draft'::character varying;

ALTER TABLE public.playbooks
    DROP CONSTRAINT IF EXISTS playbooks_status_check;

ALTER TABLE public.playbooks
    ADD CONSTRAINT playbooks_status_check CHECK (
        status = ANY (ARRAY[
            'draft'::character varying,
            'replayed'::character varying,
            'approved'::character varying,
            'canary'::character varying,
            'active'::character varying,
            'deprecated'::character varying
        ])
    );

CREATE INDEX IF NOT EXISTS idx_playbooks_company_active
    ON public.playbooks (company_id, playbook_id, status, updated_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'playbooks_company_id_fkey') THEN
        ALTER TABLE ONLY public.playbooks
            ADD CONSTRAINT playbooks_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'playbooks_created_by_fkey') THEN
        ALTER TABLE ONLY public.playbooks
            ADD CONSTRAINT playbooks_created_by_fkey
            FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'playbooks_approved_by_fkey') THEN
        ALTER TABLE ONLY public.playbooks
            ADD CONSTRAINT playbooks_approved_by_fkey
            FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.agents (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    agent_id character varying(128) NOT NULL,
    hostname character varying(255) NOT NULL DEFAULT ''::character varying,
    version character varying(64) NOT NULL DEFAULT ''::character varying,
    status character varying(32) NOT NULL DEFAULT 'offline'::character varying,
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_heartbeat_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agents_status_check CHECK (
        status = ANY (ARRAY['online'::character varying, 'offline'::character varying, 'draining'::character varying])
    ),
    CONSTRAINT agents_company_agent_key UNIQUE (company_id, agent_id)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agents_company_id_fkey') THEN
        ALTER TABLE ONLY public.agents
            ADD CONSTRAINT agents_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DROP TRIGGER IF EXISTS update_agents_updated_at ON public.agents;
CREATE TRIGGER update_agents_updated_at
    BEFORE UPDATE ON public.agents
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TABLE IF NOT EXISTS public.shop_runtime_bindings (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    shop_id character varying(128) NOT NULL DEFAULT ''::character varying,
    playbook_id character varying(128) NOT NULL DEFAULT ''::character varying,
    agent_id character varying(128) NOT NULL DEFAULT ''::character varying,
    egress_group character varying(128) NOT NULL DEFAULT ''::character varying,
    credential_ref text NOT NULL DEFAULT ''::text,
    profile_status character varying(32) NOT NULL DEFAULT 'none'::character varying,
    playbook_status character varying(32) NOT NULL DEFAULT 'ok'::character varying,
    cron_pause_reason character varying(64),
    last_collection_at timestamptz,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT shop_runtime_bindings_profile_status_check CHECK (
        profile_status = ANY (ARRAY['none'::character varying, 'active'::character varying, 'needs_reauth'::character varying, 'risk_blocked'::character varying])
    ),
    CONSTRAINT shop_runtime_bindings_playbook_status_check CHECK (
        playbook_status = ANY (ARRAY['ok'::character varying, 'stale'::character varying])
    ),
    CONSTRAINT shop_runtime_bindings_company_source_key UNIQUE (company_id, data_source_id)
);

CREATE INDEX IF NOT EXISTS idx_shop_runtime_bindings_agent
    ON public.shop_runtime_bindings (agent_id, profile_status, playbook_status);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'shop_runtime_bindings_company_id_fkey') THEN
        ALTER TABLE ONLY public.shop_runtime_bindings
            ADD CONSTRAINT shop_runtime_bindings_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'shop_runtime_bindings_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.shop_runtime_bindings
            ADD CONSTRAINT shop_runtime_bindings_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DROP TRIGGER IF EXISTS update_shop_runtime_bindings_updated_at ON public.shop_runtime_bindings;
CREATE TRIGGER update_shop_runtime_bindings_updated_at
    BEFORE UPDATE ON public.shop_runtime_bindings
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TABLE IF NOT EXISTS public.browser_collection_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    dataset_code character varying(128) NOT NULL DEFAULT ''::character varying,
    resource_key character varying(255) NOT NULL DEFAULT ''::character varying,
    shop_id character varying(128) NOT NULL DEFAULT ''::character varying,
    playbook_id character varying(128) NOT NULL DEFAULT ''::character varying,
    biz_date date NOT NULL,
    item_key text NOT NULL,
    item_key_values jsonb NOT NULL DEFAULT '{}'::jsonb,
    item_hash character varying(64) NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    record_status character varying(32) NOT NULL DEFAULT 'active'::character varying,
    first_seen_job_id uuid,
    latest_seen_job_id uuid,
    first_seen_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    latest_seen_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    captured_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT browser_collection_records_status_check CHECK (
        record_status = ANY (ARRAY['active'::character varying, 'updated'::character varying, 'unchanged'::character varying, 'deleted'::character varying])
    ),
    CONSTRAINT browser_collection_records_unique_item UNIQUE (company_id, dataset_id, biz_date, item_key)
);

CREATE INDEX IF NOT EXISTS idx_browser_collection_records_lookup
    ON public.browser_collection_records (company_id, data_source_id, dataset_id, biz_date, record_status);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_collection_records_company_id_fkey') THEN
        ALTER TABLE ONLY public.browser_collection_records
            ADD CONSTRAINT browser_collection_records_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_collection_records_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.browser_collection_records
            ADD CONSTRAINT browser_collection_records_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_collection_records_dataset_id_fkey') THEN
        ALTER TABLE ONLY public.browser_collection_records
            ADD CONSTRAINT browser_collection_records_dataset_id_fkey
            FOREIGN KEY (dataset_id) REFERENCES public.data_source_datasets(id) ON DELETE CASCADE;
    END IF;
END $$;

DROP TRIGGER IF EXISTS update_browser_collection_records_updated_at ON public.browser_collection_records;
CREATE TRIGGER update_browser_collection_records_updated_at
    BEFORE UPDATE ON public.browser_collection_records
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE TABLE IF NOT EXISTS public.browser_capture_files (
    file_id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_id uuid,
    sync_job_id uuid,
    resource_key character varying(255) NOT NULL DEFAULT ''::character varying,
    shop_id character varying(128) NOT NULL DEFAULT ''::character varying,
    playbook_id character varying(128) NOT NULL DEFAULT ''::character varying,
    biz_date date,
    storage_path text NOT NULL,
    encoding character varying(64) NOT NULL DEFAULT ''::character varying,
    checksum character varying(128) NOT NULL DEFAULT ''::character varying,
    row_count integer NOT NULL DEFAULT 0,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE public.browser_capture_files
    ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT CURRENT_TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_capture_files_company_id_fkey') THEN
        ALTER TABLE ONLY public.browser_capture_files
            ADD CONSTRAINT browser_capture_files_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_capture_files_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.browser_capture_files
            ADD CONSTRAINT browser_capture_files_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_capture_files_dataset_id_fkey') THEN
        ALTER TABLE ONLY public.browser_capture_files
            ADD CONSTRAINT browser_capture_files_dataset_id_fkey
            FOREIGN KEY (dataset_id) REFERENCES public.data_source_datasets(id) ON DELETE SET NULL;
    END IF;
END $$;

DROP TRIGGER IF EXISTS update_browser_capture_files_updated_at ON public.browser_capture_files;
CREATE TRIGGER update_browser_capture_files_updated_at
    BEFORE UPDATE ON public.browser_capture_files
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.recon_execution_queue
    DROP CONSTRAINT IF EXISTS recon_execution_queue_status_check;

ALTER TABLE public.recon_execution_queue
    ADD CONSTRAINT recon_execution_queue_status_check CHECK (
        status = ANY (ARRAY['queued'::character varying, 'running'::character varying, 'waiting_data'::character varying, 'done'::character varying, 'failed'::character varying])
    );

ALTER TABLE public.recon_execution_queue
    ADD COLUMN IF NOT EXISTS next_retry_at timestamptz,
    ADD COLUMN IF NOT EXISTS wait_deadline_at timestamptz,
    ADD COLUMN IF NOT EXISTS waiting_reason text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS waiting_datasets jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS collection_job_ids jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_recon_execution_queue_waiting_data
    ON public.recon_execution_queue (next_retry_at ASC)
    WHERE status = 'waiting_data';
