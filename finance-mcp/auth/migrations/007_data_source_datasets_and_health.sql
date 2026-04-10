ALTER TABLE IF EXISTS public.data_sources
    ADD COLUMN IF NOT EXISTS health_status character varying(20) DEFAULT 'unknown'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS last_checked_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS last_error_message text DEFAULT ''::text NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_sources_health_status_check') THEN
        ALTER TABLE ONLY public.data_sources
            ADD CONSTRAINT data_sources_health_status_check CHECK (
                (health_status)::text = ANY (
                    ARRAY[
                        ('unknown'::character varying)::text,
                        ('healthy'::character varying)::text,
                        ('warning'::character varying)::text,
                        ('error'::character varying)::text,
                        ('auth_expired'::character varying)::text,
                        ('disabled'::character varying)::text
                    ]
                )
            );
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.data_source_datasets (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_code character varying(128) NOT NULL,
    dataset_name character varying(255) NOT NULL,
    resource_key character varying(100) DEFAULT 'default'::character varying NOT NULL,
    dataset_kind character varying(30) DEFAULT 'table'::character varying NOT NULL,
    origin_type character varying(30) DEFAULT 'manual'::character varying NOT NULL,
    extract_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    schema_summary jsonb DEFAULT '{}'::jsonb NOT NULL,
    sync_strategy jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    health_status character varying(20) DEFAULT 'unknown'::character varying NOT NULL,
    last_checked_at timestamp with time zone,
    last_sync_at timestamp with time zone,
    last_error_message text DEFAULT ''::text NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT data_source_datasets_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('active'::character varying)::text,
                ('disabled'::character varying)::text,
                ('deleted'::character varying)::text
            ]
        )
    ),
    CONSTRAINT data_source_datasets_origin_type_check CHECK (
        (origin_type)::text = ANY (
            ARRAY[
                ('fixed'::character varying)::text,
                ('discovered'::character varying)::text,
                ('imported_openapi'::character varying)::text,
                ('manual'::character varying)::text
            ]
        )
    ),
    CONSTRAINT data_source_datasets_health_status_check CHECK (
        (health_status)::text = ANY (
            ARRAY[
                ('unknown'::character varying)::text,
                ('healthy'::character varying)::text,
                ('warning'::character varying)::text,
                ('error'::character varying)::text,
                ('auth_expired'::character varying)::text,
                ('disabled'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_company_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_company_source_code_key') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_company_source_code_key
            UNIQUE (company_id, data_source_id, dataset_code);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_source_status
    ON public.data_source_datasets USING btree (data_source_id, status, is_enabled, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_source_resource
    ON public.data_source_datasets USING btree (data_source_id, resource_key, status, updated_at DESC);

DROP TRIGGER IF EXISTS update_data_source_datasets_updated_at ON public.data_source_datasets;
CREATE TRIGGER update_data_source_datasets_updated_at
    BEFORE UPDATE ON public.data_source_datasets
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
