-- 011: rule_detail 增加 supported_entry_modes，区分上传文件场景与数据源场景

ALTER TABLE public.rule_detail
    ADD COLUMN IF NOT EXISTS supported_entry_modes text[];

COMMENT ON COLUMN public.rule_detail.supported_entry_modes IS '规则支持的入口模式：upload=上传文件，dataset=数据源/方案';

UPDATE public.rule_detail
SET supported_entry_modes = CASE
    WHEN lower(coalesce(rule_type, '')) = 'file' THEN ARRAY['upload']::text[]
    WHEN lower(coalesce(rule_type, '')) IN ('proc', 'recon')
         AND NULLIF(btrim(coalesce(rule ->> 'file_rule_code', '')), '') IS NOT NULL
        THEN ARRAY['upload']::text[]
    ELSE ARRAY['dataset']::text[]
END
WHERE supported_entry_modes IS NULL
   OR coalesce(array_length(supported_entry_modes, 1), 0) = 0;

UPDATE public.rule_detail
SET supported_entry_modes = ARRAY(
    SELECT DISTINCT mode
    FROM unnest(supported_entry_modes) AS mode
    WHERE mode IN ('upload', 'dataset')
)
WHERE supported_entry_modes IS NOT NULL;

UPDATE public.rule_detail
SET supported_entry_modes = ARRAY['upload']::text[]
WHERE coalesce(array_length(supported_entry_modes, 1), 0) = 0;

ALTER TABLE public.rule_detail
    ALTER COLUMN supported_entry_modes SET DEFAULT ARRAY['upload']::text[];

ALTER TABLE public.rule_detail
    ALTER COLUMN supported_entry_modes SET NOT NULL;
