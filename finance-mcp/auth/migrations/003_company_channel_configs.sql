CREATE TABLE IF NOT EXISTS public.company_channel_configs (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    provider character varying(50) NOT NULL,
    channel_code character varying(100) DEFAULT 'default'::character varying NOT NULL,
    name character varying(255) DEFAULT ''::character varying NOT NULL,
    client_id character varying(255) DEFAULT ''::character varying NOT NULL,
    client_secret text DEFAULT ''::text NOT NULL,
    robot_code character varying(255) DEFAULT ''::character varying NOT NULL,
    extra jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'company_channel_configs_pkey'
    ) THEN
        ALTER TABLE ONLY public.company_channel_configs
            ADD CONSTRAINT company_channel_configs_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'company_channel_configs_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.company_channel_configs
            ADD CONSTRAINT company_channel_configs_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'company_channel_configs_company_provider_channel_key'
    ) THEN
        ALTER TABLE ONLY public.company_channel_configs
            ADD CONSTRAINT company_channel_configs_company_provider_channel_key
            UNIQUE (company_id, provider, channel_code);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_company_channel_configs_company_provider
    ON public.company_channel_configs USING btree (company_id, provider, is_enabled);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_channel_configs_default
    ON public.company_channel_configs USING btree (company_id, provider)
    WHERE (is_default = true);

DROP TRIGGER IF EXISTS update_company_channel_configs_updated_at ON public.company_channel_configs;
CREATE TRIGGER update_company_channel_configs_updated_at
    BEFORE UPDATE ON public.company_channel_configs
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
