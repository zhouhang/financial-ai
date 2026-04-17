ALTER TABLE IF EXISTS public.data_source_datasets
    ADD COLUMN IF NOT EXISTS schema_name character varying(128) DEFAULT ''::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS object_name character varying(255) DEFAULT ''::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS object_type character varying(30) DEFAULT 'unknown'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS publish_status character varying(20) DEFAULT 'unpublished'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS business_domain character varying(64) DEFAULT ''::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS business_object_type character varying(64) DEFAULT ''::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS grain character varying(64) DEFAULT ''::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS verified_status character varying(20) DEFAULT 'unverified'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS usage_count integer DEFAULT 0 NOT NULL,
    ADD COLUMN IF NOT EXISTS last_used_at timestamp with time zone,
    ADD COLUMN IF NOT EXISTS search_text text DEFAULT ''::text NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_publish_status_check') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_publish_status_check CHECK (
                (publish_status)::text = ANY (
                    ARRAY[
                        ('unpublished'::character varying)::text,
                        ('published'::character varying)::text,
                        ('deprecated'::character varying)::text
                    ]
                )
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_verified_status_check') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_verified_status_check CHECK (
                (verified_status)::text = ANY (
                    ARRAY[
                        ('unverified'::character varying)::text,
                        ('verified'::character varying)::text,
                        ('rejected'::character varying)::text
                    ]
                )
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_usage_count_check') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_usage_count_check CHECK (usage_count >= 0);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'data_source_datasets_object_type_not_empty_check') THEN
        ALTER TABLE ONLY public.data_source_datasets
            ADD CONSTRAINT data_source_datasets_object_type_not_empty_check CHECK ((length((object_type)::text) > 0));
    END IF;
END $$;

UPDATE public.data_source_datasets
SET schema_name = CASE
        WHEN NULLIF(btrim(schema_name), '') IS NOT NULL THEN btrim(schema_name)
        WHEN position('.' in COALESCE(NULLIF(btrim(resource_key), ''), '')) > 0 THEN split_part(btrim(resource_key), '.', 1)
        WHEN position('.' in COALESCE(NULLIF(btrim(dataset_name), ''), '')) > 0 THEN split_part(btrim(dataset_name), '.', 1)
        ELSE ''
    END,
    object_name = CASE
        WHEN NULLIF(btrim(object_name), '') IS NOT NULL THEN btrim(object_name)
        WHEN position('.' in COALESCE(NULLIF(btrim(resource_key), ''), '')) > 0 THEN split_part(btrim(resource_key), '.', 2)
        WHEN position('.' in COALESCE(NULLIF(btrim(dataset_name), ''), '')) > 0 THEN split_part(btrim(dataset_name), '.', 2)
        WHEN NULLIF(btrim(resource_key), '') IS NOT NULL THEN btrim(resource_key)
        WHEN NULLIF(btrim(dataset_name), '') IS NOT NULL THEN btrim(dataset_name)
        ELSE dataset_code
    END,
    object_type = CASE
        WHEN COALESCE(NULLIF(btrim(object_type), ''), '') <> '' THEN lower(btrim(object_type))
        WHEN COALESCE(NULLIF(btrim(schema_summary->>'object_type'), ''), '') <> '' THEN lower(btrim(schema_summary->>'object_type'))
        WHEN COALESCE(NULLIF(btrim(dataset_kind), ''), '') <> '' THEN lower(btrim(dataset_kind))
        ELSE 'unknown'
    END,
    publish_status = COALESCE(NULLIF(publish_status, ''), 'unpublished'),
    verified_status = COALESCE(NULLIF(verified_status, ''), 'unverified'),
    usage_count = GREATEST(COALESCE(usage_count, 0), 0);

UPDATE public.data_source_datasets
SET search_text = lower(trim(
        BOTH ' ' FROM concat_ws(
            ' ',
            COALESCE(dataset_name, ''),
            COALESCE(dataset_code, ''),
            COALESCE(resource_key, ''),
            COALESCE(schema_name, ''),
            COALESCE(object_name, ''),
            COALESCE(object_type, ''),
            COALESCE(business_domain, ''),
            COALESCE(business_object_type, ''),
            COALESCE(grain, '')
        )
    ))
WHERE COALESCE(search_text, '') = '';

UPDATE public.data_source_datasets
SET object_type = 'unknown'
WHERE NULLIF(btrim(object_type), '') IS NULL;

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_source_publish_status
    ON public.data_source_datasets USING btree (company_id, data_source_id, publish_status, status, is_enabled);

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_business_filter
    ON public.data_source_datasets USING btree (company_id, business_object_type, publish_status, verified_status);

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_schema_filter
    ON public.data_source_datasets USING btree (company_id, schema_name, object_type, publish_status);

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_last_used
    ON public.data_source_datasets USING btree (company_id, usage_count DESC, last_used_at DESC);

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_search_text
    ON public.data_source_datasets USING btree (company_id, lower(search_text));
