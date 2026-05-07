CREATE TABLE IF NOT EXISTS public.platform_order_lines (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    shop_connection_id uuid NOT NULL,
    platform_code character varying(50) NOT NULL,
    external_shop_id character varying(128) DEFAULT ''::character varying NOT NULL,
    biz_date date NOT NULL,
    tid character varying(128) NOT NULL,
    oid character varying(128) NOT NULL,
    trade_status character varying(80) DEFAULT ''::character varying NOT NULL,
    order_status character varying(80) DEFAULT ''::character varying NOT NULL,
    refund_status character varying(80) DEFAULT ''::character varying NOT NULL,
    pay_time timestamp with time zone,
    modified timestamp with time zone,
    end_time timestamp with time zone,
    alipay_no character varying(128) DEFAULT ''::character varying NOT NULL,
    payment numeric(18, 2),
    order_payment numeric(18, 2),
    total_fee numeric(18, 2),
    order_total_fee numeric(18, 2),
    discount_fee numeric(18, 2),
    order_discount_fee numeric(18, 2),
    post_fee numeric(18, 2),
    commission_fee numeric(18, 2),
    sku_id character varying(128) DEFAULT ''::character varying NOT NULL,
    outer_sku_id character varying(255) DEFAULT ''::character varying NOT NULL,
    outer_iid character varying(255) DEFAULT ''::character varying NOT NULL,
    num_iid character varying(128) DEFAULT ''::character varying NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    sku_properties_name text DEFAULT ''::text NOT NULL,
    quantity numeric(18, 4),
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_modified_at timestamp with time zone,
    first_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    latest_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_order_lines_company_id_fkey') THEN
        ALTER TABLE ONLY public.platform_order_lines
            ADD CONSTRAINT platform_order_lines_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_order_lines_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.platform_order_lines
            ADD CONSTRAINT platform_order_lines_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_order_lines_dataset_id_fkey') THEN
        ALTER TABLE ONLY public.platform_order_lines
            ADD CONSTRAINT platform_order_lines_dataset_id_fkey
            FOREIGN KEY (dataset_id) REFERENCES public.data_source_datasets(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_order_lines_shop_connection_id_fkey') THEN
        ALTER TABLE ONLY public.platform_order_lines
            ADD CONSTRAINT platform_order_lines_shop_connection_id_fkey
            FOREIGN KEY (shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_order_lines_unique_order_line') THEN
        ALTER TABLE ONLY public.platform_order_lines
            ADD CONSTRAINT platform_order_lines_unique_order_line
            UNIQUE (company_id, shop_connection_id, tid, oid);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_platform_order_lines_dataset_date
    ON public.platform_order_lines USING btree (company_id, dataset_id, biz_date, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_order_lines_source_dataset_date
    ON public.platform_order_lines USING btree (company_id, data_source_id, dataset_id, biz_date DESC);

CREATE INDEX IF NOT EXISTS idx_platform_order_lines_shop_modified
    ON public.platform_order_lines USING btree (company_id, shop_connection_id, modified DESC);

CREATE INDEX IF NOT EXISTS idx_platform_order_lines_platform_tid
    ON public.platform_order_lines USING btree (company_id, platform_code, external_shop_id, tid);

DROP TRIGGER IF EXISTS update_platform_order_lines_updated_at ON public.platform_order_lines;
CREATE TRIGGER update_platform_order_lines_updated_at
    BEFORE UPDATE ON public.platform_order_lines
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
