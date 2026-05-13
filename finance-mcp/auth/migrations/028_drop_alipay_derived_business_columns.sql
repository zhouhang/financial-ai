DROP INDEX IF EXISTS public.idx_platform_alipay_bill_lines_alipay_trade_no;
DROP INDEX IF EXISTS public.idx_platform_alipay_bill_lines_merchant_order_no;
DROP INDEX IF EXISTS public.idx_platform_alipay_bill_lines_business_order_no;

UPDATE public.platform_alipay_bill_lines
SET payload = (
    CASE
        WHEN jsonb_typeof(payload -> 'raw') = 'object' THEN payload -> 'raw'
        ELSE payload
    END
) - 'raw'
  - 'payload'
  - 'meta'
  - 'metadata'
  - 'company_id'
  - 'data_source_id'
  - 'dataset_id'
  - 'shop_connection_id'
  - 'external_shop_id'
  - 'bill_type'
  - 'bill_date'
  - 'biz_date'
  - 'source_file_name'
  - 'source_row_number'
  - 'source_row_key'
  - 'platform_code'
  - 'merchant_display_name'
  - 'alipay_trade_no'
  - 'merchant_order_no'
  - 'business_order_no'
  - 'amount'
  - 'income_amount'
  - 'expense_amount'
  - 'trade_time'
WHERE payload IS NOT NULL;

ALTER TABLE public.platform_alipay_bill_lines
    DROP COLUMN IF EXISTS alipay_trade_no,
    DROP COLUMN IF EXISTS merchant_order_no,
    DROP COLUMN IF EXISTS business_order_no,
    DROP COLUMN IF EXISTS amount,
    DROP COLUMN IF EXISTS income_amount,
    DROP COLUMN IF EXISTS expense_amount,
    DROP COLUMN IF EXISTS trade_time;
