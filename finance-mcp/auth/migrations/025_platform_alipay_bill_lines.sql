CREATE TABLE IF NOT EXISTS public.platform_alipay_bill_lines (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    shop_connection_id uuid NOT NULL,
    external_shop_id character varying(128) DEFAULT ''::character varying NOT NULL,
    bill_type character varying(64) NOT NULL,
    bill_date date NOT NULL,
    source_file_name text DEFAULT ''::text NOT NULL,
    source_row_number integer,
    source_row_key character varying(128) NOT NULL,
    alipay_trade_no character varying(128) DEFAULT ''::character varying NOT NULL,
    merchant_order_no character varying(128) DEFAULT ''::character varying NOT NULL,
    business_order_no character varying(128) DEFAULT ''::character varying NOT NULL,
    amount numeric(18, 2),
    income_amount numeric(18, 2),
    expense_amount numeric(18, 2),
    trade_time timestamp with time zone,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    first_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    latest_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_company_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_dataset_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_dataset_id_fkey
            FOREIGN KEY (dataset_id) REFERENCES public.data_source_datasets(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_shop_connection_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_shop_connection_id_fkey
            FOREIGN KEY (shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_unique_bill_row') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_unique_bill_row
            UNIQUE (company_id, shop_connection_id, bill_type, bill_date, source_row_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_dataset_date
    ON public.platform_alipay_bill_lines USING btree (company_id, dataset_id, bill_date, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_source_dataset_date
    ON public.platform_alipay_bill_lines USING btree (company_id, data_source_id, dataset_id, bill_date DESC);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_shop_type_date
    ON public.platform_alipay_bill_lines USING btree (company_id, shop_connection_id, bill_type, bill_date DESC);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_alipay_trade_no
    ON public.platform_alipay_bill_lines USING btree (company_id, alipay_trade_no);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_merchant_order_no
    ON public.platform_alipay_bill_lines USING btree (company_id, merchant_order_no);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_business_order_no
    ON public.platform_alipay_bill_lines USING btree (company_id, business_order_no);

DROP TRIGGER IF EXISTS update_platform_alipay_bill_lines_updated_at ON public.platform_alipay_bill_lines;
CREATE TRIGGER update_platform_alipay_bill_lines_updated_at
    BEFORE UPDATE ON public.platform_alipay_bill_lines
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
