CREATE TABLE IF NOT EXISTS public.storage_objects (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    logical_path text NOT NULL,
    owner_user_id uuid,
    company_id uuid,
    module character varying(128) NOT NULL DEFAULT ''::character varying,
    storage_provider character varying(32) NOT NULL DEFAULT 'local'::character varying,
    storage_bucket text NOT NULL DEFAULT ''::text,
    storage_key text NOT NULL DEFAULT ''::text,
    storage_uri text NOT NULL DEFAULT ''::text,
    local_path text NOT NULL DEFAULT ''::text,
    original_filename text NOT NULL DEFAULT ''::text,
    content_type character varying(255) NOT NULL DEFAULT ''::character varying,
    size_bytes bigint NOT NULL DEFAULT 0,
    checksum character varying(128) NOT NULL DEFAULT ''::character varying,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT storage_objects_logical_path_key UNIQUE (logical_path)
);

CREATE INDEX IF NOT EXISTS idx_storage_objects_owner
    ON public.storage_objects (owner_user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_storage_objects_company_module
    ON public.storage_objects (company_id, module, updated_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'storage_objects_owner_user_id_fkey') THEN
        ALTER TABLE ONLY public.storage_objects
            ADD CONSTRAINT storage_objects_owner_user_id_fkey
            FOREIGN KEY (owner_user_id) REFERENCES public.users(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'storage_objects_company_id_fkey') THEN
        ALTER TABLE ONLY public.storage_objects
            ADD CONSTRAINT storage_objects_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DROP TRIGGER IF EXISTS update_storage_objects_updated_at ON public.storage_objects;
CREATE TRIGGER update_storage_objects_updated_at
    BEFORE UPDATE ON public.storage_objects
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.browser_capture_files
    ADD COLUMN IF NOT EXISTS storage_provider character varying(32) NOT NULL DEFAULT 'local'::character varying,
    ADD COLUMN IF NOT EXISTS storage_bucket text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS storage_key text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS storage_uri text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS content_type character varying(255) NOT NULL DEFAULT ''::character varying,
    ADD COLUMN IF NOT EXISTS size_bytes bigint NOT NULL DEFAULT 0;
