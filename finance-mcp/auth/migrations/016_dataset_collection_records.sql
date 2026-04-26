CREATE TABLE IF NOT EXISTS public.dataset_collection_records (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    dataset_code character varying(128) NOT NULL,
    resource_key character varying(100) DEFAULT 'default'::character varying NOT NULL,
    biz_date character varying(32) NOT NULL,
    item_key text NOT NULL,
    item_key_values jsonb DEFAULT '{}'::jsonb NOT NULL,
    item_hash character varying(64) DEFAULT ''::character varying NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    record_status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    first_seen_job_id uuid,
    latest_seen_job_id uuid,
    first_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    latest_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT dataset_collection_records_status_check CHECK (
        (record_status)::text = ANY (
            ARRAY[
                ('active'::character varying)::text,
                ('updated'::character varying)::text,
                ('unchanged'::character varying)::text,
                ('deleted'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_collection_records_company_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_collection_records
            ADD CONSTRAINT dataset_collection_records_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_collection_records_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_collection_records
            ADD CONSTRAINT dataset_collection_records_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_collection_records_dataset_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_collection_records
            ADD CONSTRAINT dataset_collection_records_dataset_id_fkey
            FOREIGN KEY (dataset_id) REFERENCES public.data_source_datasets(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_collection_records_first_seen_job_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_collection_records
            ADD CONSTRAINT dataset_collection_records_first_seen_job_id_fkey
            FOREIGN KEY (first_seen_job_id) REFERENCES public.sync_jobs(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_collection_records_latest_seen_job_id_fkey') THEN
        ALTER TABLE ONLY public.dataset_collection_records
            ADD CONSTRAINT dataset_collection_records_latest_seen_job_id_fkey
            FOREIGN KEY (latest_seen_job_id) REFERENCES public.sync_jobs(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'dataset_collection_records_unique_item') THEN
        ALTER TABLE ONLY public.dataset_collection_records
            ADD CONSTRAINT dataset_collection_records_unique_item
            UNIQUE (company_id, dataset_id, biz_date, item_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_dataset_collection_records_source_resource
    ON public.dataset_collection_records USING btree (company_id, data_source_id, resource_key, biz_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_dataset_collection_records_dataset_status
    ON public.dataset_collection_records USING btree (company_id, dataset_id, biz_date DESC, record_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_dataset_collection_records_latest_job
    ON public.dataset_collection_records USING btree (latest_seen_job_id, updated_at DESC);

DROP TRIGGER IF EXISTS update_dataset_collection_records_updated_at ON public.dataset_collection_records;
CREATE TRIGGER update_dataset_collection_records_updated_at
    BEFORE UPDATE ON public.dataset_collection_records
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
