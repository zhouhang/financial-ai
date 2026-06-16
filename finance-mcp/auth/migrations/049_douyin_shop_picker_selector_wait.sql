-- Douyin can land on a shop/sub-account picker right after login. The picker
-- renders asynchronously and class names vary, so wait longer and allow a plain
-- text fallback for the configured target shop.
WITH target_playbooks(playbook_id) AS (
    VALUES
        ('browser-collection-e7456c34e4'),
        ('browser-collection-af964a23bc'),
        ('browser-collection-5f14be0cb4'),
        ('browser-collection-bcd0b552d1'),
        ('browser-collection-eff0a0000f'),
        ('browser-collection-91fe9866c4')
),
matched_steps AS (
    SELECT
        p.playbook_id,
        (step.ord - 1)::int AS step_index,
        step.value->>'selector' AS old_selector,
        substring(step.value->>'selector' from ':has-text\\(''([^'']+)''\\)') AS shop_name
    FROM public.playbooks p
    JOIN target_playbooks t ON t.playbook_id = p.playbook_id
    CROSS JOIN LATERAL jsonb_array_elements(p.playbook_body #> '{steps}') WITH ORDINALITY AS step(value, ord)
    WHERE step.value->>'id' = 'select_login_shop_if_present'
      AND step.value->>'action' = 'click_if_present'
)
UPDATE public.playbooks p
SET playbook_body = jsonb_set(
        jsonb_set(
            p.playbook_body,
            ARRAY['steps', ms.step_index::text, 'selector'],
            to_jsonb(ms.old_selector || ', text=' || ms.shop_name),
            true
        ),
        ARRAY['steps', ms.step_index::text, 'visible_timeout_ms'],
        to_jsonb(10000),
        true
    ),
    updated_at = now()
FROM matched_steps ms
WHERE p.playbook_id = ms.playbook_id
  AND ms.old_selector IS NOT NULL
  AND ms.shop_name IS NOT NULL
  AND ms.old_selector NOT LIKE '%, text=%';
