INSERT INTO public.company (
    id,
    name,
    code,
    max_users,
    max_departments,
    enabled_features,
    status
) VALUES (
    '00000000-0000-0000-0000-00000000dd01',
    '武汉对对科技有限公司',
    'TALLY_SERVICE_PROVIDER',
    1000,
    100,
    '["reconciliation", "data_prep", "platform_oauth"]'::jsonb,
    'active'
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    code = EXCLUDED.code,
    enabled_features = EXCLUDED.enabled_features,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;
