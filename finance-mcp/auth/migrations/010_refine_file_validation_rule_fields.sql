WITH cleaned AS (
  SELECT
    id,
    jsonb_set(
      (
        (rule::jsonb)
          #- '{file_validation_rules,validation_config,allow_multi_rule_match}'
      ),
      '{file_validation_rules,table_schemas}',
      (
        SELECT jsonb_agg(
          (
            (item - 'is_ness' - 'max_file_match_count' - 'enabled')
            || jsonb_build_object(
              'is_required', COALESCE(item->'is_ness', 'false'::jsonb),
              'max_match_count', COALESCE(item->'max_file_match_count', '0'::jsonb)
            )
          )
        )
        FROM jsonb_array_elements((rule::jsonb)->'file_validation_rules'->'table_schemas') AS item
      )
    ) AS cleaned_rule
  FROM rule_detail
  WHERE id = 6
)
UPDATE rule_detail AS rd
SET rule = cleaned.cleaned_rule
FROM cleaned
WHERE rd.id = cleaned.id;
