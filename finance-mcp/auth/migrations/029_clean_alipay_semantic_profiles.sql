WITH hidden_fields(raw_name) AS (
    VALUES
        ('source_row_key'),
        ('source_file_name'),
        ('source_row_number'),
        ('data_source_id'),
        ('dataset_id'),
        ('shop_connection_id'),
        ('resource_key'),
        ('created_at'),
        ('updated_at'),
        ('bill_type'),
        ('bill_date'),
        ('biz_date'),
        ('company_id'),
        ('external_shop_id'),
        ('platform_code'),
        ('merchant_display_name'),
        ('alipay_trade_no'),
        ('merchant_order_no'),
        ('business_order_no'),
        ('amount'),
        ('income_amount'),
        ('expense_amount'),
        ('trade_time'),
        ('raw'),
        ('payload'),
        ('meta'),
        ('metadata')
),
alipay_datasets AS (
    SELECT d.id, COALESCE(d.meta, '{}'::jsonb) AS meta
    FROM public.data_source_datasets d
    WHERE (
        d.resource_key LIKE 'alipay_bill:%'
        OR d.schema_summary->>'storage' = 'platform_alipay_bill_lines'
        OR d.extract_config->>'storage' = 'platform_alipay_bill_lines'
    )
      AND COALESCE(d.meta, '{}'::jsonb) ? 'semantic_profile'
),
cleaned AS (
    SELECT
        d.id,
        jsonb_set(
            d.meta,
            '{semantic_profile}',
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            d.meta->'semantic_profile',
                            '{fields}',
                            COALESCE(
                                (
                                    SELECT jsonb_agg(item)
                                    FROM jsonb_array_elements(
                                        CASE
                                            WHEN jsonb_typeof(d.meta->'semantic_profile'->'fields') = 'array'
                                            THEN d.meta->'semantic_profile'->'fields'
                                            ELSE '[]'::jsonb
                                        END
                                    ) AS item
                                    WHERE COALESCE(item->>'raw_name', item->>'name', '') <> ''
                                      AND NOT EXISTS (
                                          SELECT 1
                                          FROM hidden_fields h
                                          WHERE h.raw_name = COALESCE(item->>'raw_name', item->>'name', '')
                                      )
                                      AND COALESCE(item->>'raw_name', item->>'name', '') NOT LIKE 'raw.%'
                                ),
                                '[]'::jsonb
                            ),
                            true
                        ),
                        '{field_label_map}',
                        COALESCE(
                            (
                                SELECT jsonb_object_agg(entry.key, entry.value)
                                FROM jsonb_each(
                                    CASE
                                        WHEN jsonb_typeof(d.meta->'semantic_profile'->'field_label_map') = 'object'
                                        THEN d.meta->'semantic_profile'->'field_label_map'
                                        ELSE '{}'::jsonb
                                    END
                                ) AS entry
                                WHERE entry.key <> ''
                                  AND NOT EXISTS (
                                      SELECT 1
                                      FROM hidden_fields h
                                      WHERE h.raw_name = entry.key
                                  )
                                  AND entry.key NOT LIKE 'raw.%'
                            ),
                            '{}'::jsonb
                        ),
                        true
                    ),
                    '{key_fields}',
                    COALESCE(
                        (
                            SELECT jsonb_agg(to_jsonb(raw_name))
                            FROM jsonb_array_elements_text(
                                CASE
                                    WHEN jsonb_typeof(d.meta->'semantic_profile'->'key_fields') = 'array'
                                    THEN d.meta->'semantic_profile'->'key_fields'
                                    ELSE '[]'::jsonb
                                END
                            ) AS raw_name
                            WHERE raw_name <> ''
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM hidden_fields h
                                  WHERE h.raw_name = raw_name
                              )
                              AND raw_name NOT LIKE 'raw.%'
                        ),
                        '[]'::jsonb
                    ),
                    true
                ),
                '{low_confidence_fields}',
                COALESCE(
                    (
                        SELECT jsonb_agg(to_jsonb(raw_name))
                        FROM jsonb_array_elements_text(
                            CASE
                                WHEN jsonb_typeof(d.meta->'semantic_profile'->'low_confidence_fields') = 'array'
                                THEN d.meta->'semantic_profile'->'low_confidence_fields'
                                ELSE '[]'::jsonb
                            END
                        ) AS raw_name
                        WHERE raw_name <> ''
                          AND NOT EXISTS (
                              SELECT 1
                              FROM hidden_fields h
                              WHERE h.raw_name = raw_name
                          )
                          AND raw_name NOT LIKE 'raw.%'
                    ),
                    '[]'::jsonb
                ),
                true
            ),
            true
        ) AS meta
    FROM alipay_datasets d
)
UPDATE public.data_source_datasets d
SET meta = cleaned.meta,
    updated_at = CURRENT_TIMESTAMP
FROM cleaned
WHERE d.id = cleaned.id
  AND d.meta IS DISTINCT FROM cleaned.meta;
