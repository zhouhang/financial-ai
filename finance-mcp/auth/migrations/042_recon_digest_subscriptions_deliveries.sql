-- recon digest subscriptions and delivery outbox.
-- Subscriptions define who receives boss/finance digest messages. Deliveries
-- record each send attempt/result so digest finalization is idempotent.

CREATE TABLE IF NOT EXISTS public.recon_digest_subscriptions (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    domain character varying(32) DEFAULT 'ecom'::character varying NOT NULL,
    view character varying(32) NOT NULL,
    period character varying(32) DEFAULT 'daily'::character varying NOT NULL,
    scope jsonb DEFAULT '{"mode":"company_all"}'::jsonb NOT NULL,
    channel_config_id uuid,
    target_type character varying(32) DEFAULT 'user'::character varying NOT NULL,
    recipient_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    conversation_id text DEFAULT ''::text NOT NULL,
    send_window jsonb DEFAULT '{}'::jsonb NOT NULL,
    failure_recipients jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(32) DEFAULT 'active'::character varying NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_subscriptions_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest_subscriptions
            ADD CONSTRAINT recon_digest_subscriptions_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_subscriptions_channel_config_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest_subscriptions
            ADD CONSTRAINT recon_digest_subscriptions_channel_config_id_fkey
            FOREIGN KEY (channel_config_id) REFERENCES public.company_channel_configs(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_digest_subscriptions_company_period
    ON public.recon_digest_subscriptions (company_id, period, enabled, status);
CREATE INDEX IF NOT EXISTS idx_recon_digest_subscriptions_company_view
    ON public.recon_digest_subscriptions (company_id, view, enabled, status);

CREATE TABLE IF NOT EXISTS public.recon_digest_deliveries (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    digest_id uuid NOT NULL,
    company_id uuid NOT NULL,
    subscription_id uuid NOT NULL,
    view character varying(32) NOT NULL,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    error text DEFAULT ''::text NOT NULL,
    message_id text DEFAULT ''::text NOT NULL,
    detail_url text DEFAULT ''::text NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    delivered_at timestamp with time zone,
    raw_result jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_deliveries_digest_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest_deliveries
            ADD CONSTRAINT recon_digest_deliveries_digest_id_fkey
            FOREIGN KEY (digest_id) REFERENCES public.recon_digest(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_deliveries_company_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest_deliveries
            ADD CONSTRAINT recon_digest_deliveries_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_deliveries_subscription_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest_deliveries
            ADD CONSTRAINT recon_digest_deliveries_subscription_id_fkey
            FOREIGN KEY (subscription_id) REFERENCES public.recon_digest_subscriptions(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_deliveries_unique'
    ) THEN
        ALTER TABLE ONLY public.recon_digest_deliveries
            ADD CONSTRAINT recon_digest_deliveries_unique UNIQUE (digest_id, view, subscription_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recon_digest_deliveries_company_status
    ON public.recon_digest_deliveries (company_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recon_digest_deliveries_subscription
    ON public.recon_digest_deliveries (subscription_id, created_at DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_subscription_id_fkey'
    ) THEN
        ALTER TABLE ONLY public.recon_digest
            ADD CONSTRAINT recon_digest_subscription_id_fkey
            FOREIGN KEY (subscription_id) REFERENCES public.recon_digest_subscriptions(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'recon_digest_unique_subscription_period'
    ) THEN
        ALTER TABLE ONLY public.recon_digest
            ADD CONSTRAINT recon_digest_unique_subscription_period
            UNIQUE (subscription_id, period_start, period_end);
    END IF;
END $$;

DROP TRIGGER IF EXISTS update_recon_digest_subscriptions_updated_at ON public.recon_digest_subscriptions;
CREATE TRIGGER update_recon_digest_subscriptions_updated_at
    BEFORE UPDATE ON public.recon_digest_subscriptions
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_recon_digest_deliveries_updated_at ON public.recon_digest_deliveries;
CREATE TRIGGER update_recon_digest_deliveries_updated_at
    BEFORE UPDATE ON public.recon_digest_deliveries
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
