CREATE TABLE IF NOT EXISTS public.platform_apps (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    platform_code character varying(50) NOT NULL,
    app_name character varying(255) DEFAULT ''::character varying NOT NULL,
    app_key character varying(255) DEFAULT ''::character varying NOT NULL,
    app_secret text DEFAULT ''::text NOT NULL,
    app_type character varying(30) DEFAULT 'isv'::character varying NOT NULL,
    auth_base_url text DEFAULT ''::text NOT NULL,
    token_url text DEFAULT ''::text NOT NULL,
    refresh_url text DEFAULT ''::text NOT NULL,
    scopes_config jsonb DEFAULT '[]'::jsonb NOT NULL,
    extra jsonb DEFAULT '{}'::jsonb NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT platform_apps_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('active'::character varying)::text,
                ('inactive'::character varying)::text,
                ('deleted'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.shop_connections (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    platform_code character varying(50) NOT NULL,
    external_shop_id character varying(128) NOT NULL,
    external_shop_name character varying(255) DEFAULT ''::character varying NOT NULL,
    external_seller_id character varying(128) DEFAULT ''::character varying NOT NULL,
    auth_subject_name character varying(255) DEFAULT ''::character varying NOT NULL,
    shop_type character varying(30) DEFAULT 'standard'::character varying NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    meta jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT shop_connections_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('active'::character varying)::text,
                ('disabled'::character varying)::text,
                ('deleted'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.shop_authorizations (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    shop_connection_id uuid NOT NULL,
    platform_app_id uuid NOT NULL,
    auth_type character varying(50) DEFAULT 'oauth_code'::character varying NOT NULL,
    access_token text DEFAULT ''::text NOT NULL,
    refresh_token text DEFAULT ''::text NOT NULL,
    token_expires_at timestamp with time zone,
    refresh_expires_at timestamp with time zone,
    scope_text text DEFAULT ''::text NOT NULL,
    auth_status character varying(30) DEFAULT 'authorized'::character varying NOT NULL,
    is_current boolean DEFAULT true NOT NULL,
    auth_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    last_refresh_at timestamp with time zone,
    last_error text DEFAULT ''::text NOT NULL,
    raw_auth_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT shop_authorizations_status_check CHECK (
        (auth_status)::text = ANY (
            ARRAY[
                ('authorized'::character varying)::text,
                ('expired'::character varying)::text,
                ('revoked'::character varying)::text,
                ('reauth_required'::character varying)::text,
                ('failed'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.sync_sources (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    shop_connection_id uuid NOT NULL,
    source_type character varying(30) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    sync_strategy character varying(40) DEFAULT 'full_then_incremental'::character varying NOT NULL,
    last_sync_cursor text DEFAULT ''::text NOT NULL,
    last_sync_at timestamp with time zone,
    last_success_at timestamp with time zone,
    last_status character varying(20) DEFAULT 'idle'::character varying NOT NULL,
    last_error text DEFAULT ''::text NOT NULL,
    extra jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT sync_sources_status_check CHECK (
        (last_status)::text = ANY (
            ARRAY[
                ('idle'::character varying)::text,
                ('running'::character varying)::text,
                ('success'::character varying)::text,
                ('failed'::character varying)::text,
                ('paused'::character varying)::text
            ]
        )
    )
);

CREATE TABLE IF NOT EXISTS public.auth_sessions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    company_id uuid NOT NULL,
    platform_code character varying(50) NOT NULL,
    operator_user_id uuid,
    shop_connection_id uuid,
    state_token character varying(255) NOT NULL,
    return_path character varying(500) DEFAULT ''::character varying NOT NULL,
    redirect_uri text DEFAULT ''::text NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    callback_code character varying(255) DEFAULT ''::character varying NOT NULL,
    callback_error text DEFAULT ''::text NOT NULL,
    callback_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp with time zone,
    CONSTRAINT auth_sessions_status_check CHECK (
        (status)::text = ANY (
            ARRAY[
                ('pending'::character varying)::text,
                ('authorized'::character varying)::text,
                ('failed'::character varying)::text,
                ('expired'::character varying)::text,
                ('cancelled'::character varying)::text
            ]
        )
    )
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_apps_pkey'
    ) THEN
        ALTER TABLE ONLY public.platform_apps
            ADD CONSTRAINT platform_apps_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_connections_pkey'
    ) THEN
        ALTER TABLE ONLY public.shop_connections
            ADD CONSTRAINT shop_connections_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_authorizations_pkey'
    ) THEN
        ALTER TABLE ONLY public.shop_authorizations
            ADD CONSTRAINT shop_authorizations_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sync_sources_pkey'
    ) THEN
        ALTER TABLE ONLY public.sync_sources
            ADD CONSTRAINT sync_sources_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'auth_sessions_pkey'
    ) THEN
        ALTER TABLE ONLY public.auth_sessions
            ADD CONSTRAINT auth_sessions_pkey PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_apps_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.platform_apps
            ADD CONSTRAINT platform_apps_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_connections_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.shop_connections
            ADD CONSTRAINT shop_connections_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_authorizations_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.shop_authorizations
            ADD CONSTRAINT shop_authorizations_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_authorizations_shop_connection_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.shop_authorizations
            ADD CONSTRAINT shop_authorizations_shop_connection_id_fkey
            FOREIGN KEY (shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_authorizations_platform_app_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.shop_authorizations
            ADD CONSTRAINT shop_authorizations_platform_app_id_fkey
            FOREIGN KEY (platform_app_id) REFERENCES public.platform_apps(id) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sync_sources_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.sync_sources
            ADD CONSTRAINT sync_sources_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sync_sources_shop_connection_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.sync_sources
            ADD CONSTRAINT sync_sources_shop_connection_id_fkey
            FOREIGN KEY (shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'auth_sessions_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.auth_sessions
            ADD CONSTRAINT auth_sessions_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'auth_sessions_operator_user_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.auth_sessions
            ADD CONSTRAINT auth_sessions_operator_user_id_fkey
            FOREIGN KEY (operator_user_id) REFERENCES public.users(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'auth_sessions_shop_connection_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.auth_sessions
            ADD CONSTRAINT auth_sessions_shop_connection_id_fkey
            FOREIGN KEY (shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_apps_company_platform_appkey_key'
    ) THEN
        ALTER TABLE ONLY public.platform_apps
            ADD CONSTRAINT platform_apps_company_platform_appkey_key
            UNIQUE (company_id, platform_code, app_key);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'shop_connections_company_platform_shop_key'
    ) THEN
        ALTER TABLE ONLY public.shop_connections
            ADD CONSTRAINT shop_connections_company_platform_shop_key
            UNIQUE (company_id, platform_code, external_shop_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sync_sources_shop_source_key'
    ) THEN
        ALTER TABLE ONLY public.sync_sources
            ADD CONSTRAINT sync_sources_shop_source_key
            UNIQUE (shop_connection_id, source_type);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'auth_sessions_state_token_key'
    ) THEN
        ALTER TABLE ONLY public.auth_sessions
            ADD CONSTRAINT auth_sessions_state_token_key
            UNIQUE (state_token);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_platform_apps_company_platform
    ON public.platform_apps USING btree (company_id, platform_code, status);

CREATE INDEX IF NOT EXISTS idx_shop_connections_company_platform
    ON public.shop_connections USING btree (company_id, platform_code, status);

CREATE INDEX IF NOT EXISTS idx_shop_authorizations_shop_status
    ON public.shop_authorizations USING btree (shop_connection_id, auth_status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_sync_sources_company_shop
    ON public.sync_sources USING btree (company_id, shop_connection_id, source_type);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_company_platform_status
    ON public.auth_sessions USING btree (company_id, platform_code, status, expires_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_shop_authorizations_current
    ON public.shop_authorizations USING btree (shop_connection_id)
    WHERE (is_current = true);

DROP TRIGGER IF EXISTS update_platform_apps_updated_at ON public.platform_apps;
CREATE TRIGGER update_platform_apps_updated_at
    BEFORE UPDATE ON public.platform_apps
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_shop_connections_updated_at ON public.shop_connections;
CREATE TRIGGER update_shop_connections_updated_at
    BEFORE UPDATE ON public.shop_connections
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_shop_authorizations_updated_at ON public.shop_authorizations;
CREATE TRIGGER update_shop_authorizations_updated_at
    BEFORE UPDATE ON public.shop_authorizations
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_sync_sources_updated_at ON public.sync_sources;
CREATE TRIGGER update_sync_sources_updated_at
    BEFORE UPDATE ON public.sync_sources
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_auth_sessions_updated_at ON public.auth_sessions;
CREATE TRIGGER update_auth_sessions_updated_at
    BEFORE UPDATE ON public.auth_sessions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
