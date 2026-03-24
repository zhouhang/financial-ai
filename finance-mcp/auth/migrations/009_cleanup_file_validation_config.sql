WITH cleaned AS (
  SELECT
    id,
    jsonb_set(
      (rule::jsonb)
        #- '{file_validation_rules,validation_config,match_strategy}'
        #- '{file_validation_rules,validation_config,case_sensitive_description}'
        #- '{file_validation_rules,validation_config,match_strategy_description}'
        #- '{file_validation_rules,validation_config,ignore_whitespace_description}'
        #- '{file_validation_rules,validation_config,allow_multi_rule_match_description}'
        #- '{file_validation_rules,validation_config,file_count,min_description}'
        #- '{file_validation_rules,validation_config,file_count,max_description}'
        #- '{file_validation_rules,validation_config,file_count,allow_multiple_description}',
      '{file_validation_rules,table_schemas}',
      (
        SELECT jsonb_agg(item - 'max_file_match_count_description')
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
