CREATE TABLE IF NOT EXISTS public.platform_pending_authorizations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    platform_code character varying(50) NOT NULL,
    platform_app_id uuid,
    app_id character varying(128) DEFAULT ''::character varying NOT NULL,
    source character varying(128) DEFAULT ''::character varying NOT NULL,
    claim_code character varying(64) NOT NULL,
    status character varying(32) DEFAULT 'pending_claim'::character varying NOT NULL,
    access_token text DEFAULT ''::text NOT NULL,
    refresh_token text DEFAULT ''::text NOT NULL,
    token_expires_at timestamp with time zone,
    refresh_expires_at timestamp with time zone,
    raw_auth_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    callback_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    external_shop_id character varying(255) DEFAULT ''::character varying NOT NULL,
    external_seller_id character varying(255) DEFAULT ''::character varying NOT NULL,
    merchant_display_name character varying(255) DEFAULT ''::character varying NOT NULL,
    claimed_company_id uuid,
    claimed_by_user_id uuid,
    claimed_shop_connection_id uuid,
    claimed_at timestamp with time zone,
    expires_at timestamp with time zone NOT NULL,
    last_error text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT platform_pending_authorizations_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('pending_claim'::character varying)::text,
                ('claimed'::character varying)::text,
                ('expired'::character varying)::text,
                ('failed'::character varying)::text,
                ('discarded'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_pending_authorizations_pkey'
    ) THEN
        ALTER TABLE ONLY public.platform_pending_authorizations
            ADD CONSTRAINT platform_pending_authorizations_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_pending_authorizations_platform_app_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.platform_pending_authorizations
            ADD CONSTRAINT platform_pending_authorizations_platform_app_id_fkey
            FOREIGN KEY (platform_app_id) REFERENCES public.platform_apps(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_pending_authorizations_claimed_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.platform_pending_authorizations
            ADD CONSTRAINT platform_pending_authorizations_claimed_company_id_fkey
            FOREIGN KEY (claimed_company_id) REFERENCES public.company(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_pending_authorizations_claimed_by_user_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.platform_pending_authorizations
            ADD CONSTRAINT platform_pending_authorizations_claimed_by_user_id_fkey
            FOREIGN KEY (claimed_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_pending_authorizations_claimed_shop_connection_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.platform_pending_authorizations
            ADD CONSTRAINT platform_pending_authorizations_claimed_shop_connection_id_fkey
            FOREIGN KEY (claimed_shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_pending_authorizations_claim_code_active
    ON public.platform_pending_authorizations USING btree (claim_code)
    WHERE ((status)::text = 'pending_claim'::text);

CREATE INDEX IF NOT EXISTS idx_platform_pending_authorizations_platform_status
    ON public.platform_pending_authorizations USING btree (platform_code, status, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_pending_authorizations_external_shop
    ON public.platform_pending_authorizations USING btree (platform_code, external_shop_id);

DROP TRIGGER IF EXISTS update_platform_pending_authorizations_updated_at
    ON public.platform_pending_authorizations;
CREATE TRIGGER update_platform_pending_authorizations_updated_at
    BEFORE UPDATE ON public.platform_pending_authorizations
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();
