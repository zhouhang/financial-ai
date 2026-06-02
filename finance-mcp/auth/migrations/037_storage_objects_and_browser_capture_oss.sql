CREATE TABLE IF NOT EXISTS public.storage_objects (
    object_id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    logical_path text NOT NULL UNIQUE,
    owner_user_id uuid,
    company_id uuid,
    module character varying(64) NOT NULL DEFAULT ''::character varying,
    storage_provider character varying(32) NOT NULL,
    storage_bucket text NOT NULL DEFAULT ''::text,
    storage_key text NOT NULL DEFAULT ''::text,
    storage_uri text NOT NULL DEFAULT ''::text,
    local_path text NOT NULL DEFAULT ''::text,
    original_filename text NOT NULL DEFAULT ''::text,
    content_type text NOT NULL DEFAULT ''::text,
    size_bytes bigint NOT NULL DEFAULT 0,
    checksum text NOT NULL DEFAULT ''::text,
    metadata_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_storage_objects_owner_user_id
    ON public.storage_objects(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_storage_objects_company_module
    ON public.storage_objects(company_id, module);

DROP TRIGGER IF EXISTS update_storage_objects_updated_at ON public.storage_objects;
CREATE TRIGGER update_storage_objects_updated_at
    BEFORE UPDATE ON public.storage_objects
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.browser_capture_files
    ADD COLUMN IF NOT EXISTS storage_provider character varying(32) NOT NULL DEFAULT 'local',
    ADD COLUMN IF NOT EXISTS storage_bucket text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS storage_key text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS storage_uri text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS content_type text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS size_bytes bigint NOT NULL DEFAULT 0;
