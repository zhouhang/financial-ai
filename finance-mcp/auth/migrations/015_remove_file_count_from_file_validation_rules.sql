-- 015: 从 file_validation 规则中移除废弃的 validation_config.file_count

BEGIN;

UPDATE public.rule_detail
SET rule = CASE
    WHEN COALESCE(rule #> '{file_validation_rules,validation_config}', '{}'::jsonb) ? 'file_count' THEN
        jsonb_set(
            rule,
            '{file_validation_rules,validation_config}',
            COALESCE(rule #> '{file_validation_rules,validation_config}', '{}'::jsonb) - 'file_count',
            true
        )
    WHEN COALESCE(rule #> '{validation_config}', '{}'::jsonb) ? 'file_count' THEN
        jsonb_set(
            rule,
            '{validation_config}',
            COALESCE(rule #> '{validation_config}', '{}'::jsonb) - 'file_count',
            true
        )
    ELSE rule
END
WHERE rule_type = 'file'
  AND (
      COALESCE(rule #> '{file_validation_rules,validation_config}', '{}'::jsonb) ? 'file_count'
      OR COALESCE(rule #> '{validation_config}', '{}'::jsonb) ? 'file_count'
  );

COMMIT;
