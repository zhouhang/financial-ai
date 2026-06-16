-- Douyin order pagination size labels vary by merchant/session. Setting 100
-- rows per page is an optimization only; JSON pagination can still collect all
-- rows via the next-page control. Make the 100/page choice optional and accept
-- compact/no-space labels.
WITH target_playbooks(playbook_id) AS (
    VALUES
        ('browser-collection-af964a23bc'),
        ('browser-collection-5f14be0cb4'),
        ('browser-collection-eff0a0000f')
),
matched_steps AS (
    SELECT
        p.playbook_id,
        (step.ord - 1)::int AS step_index
    FROM public.playbooks p
    JOIN target_playbooks t ON t.playbook_id = p.playbook_id
    CROSS JOIN LATERAL jsonb_array_elements(p.playbook_body #> '{steps}') WITH ORDINALITY AS step(value, ord)
    WHERE step.value->>'id' = 'choose_100_per_page'
)
UPDATE public.playbooks p
SET playbook_body = jsonb_set(
        jsonb_set(
            jsonb_set(
                p.playbook_body,
                ARRAY['steps', ms.step_index::text, 'action'],
                to_jsonb('click_if_present'::text),
                true
            ),
            ARRAY['steps', ms.step_index::text, 'selector'],
            to_jsonb('text=/100\\s*条\\/页/, text=100条/页, text=100 条/页, .auxo-select-item:has-text("100"), [class*=select-item]:has-text("100")'::text),
            true
        ),
        ARRAY['steps', ms.step_index::text, 'visible_timeout_ms'],
        to_jsonb(3000),
        true
    ),
    updated_at = now()
FROM matched_steps ms
WHERE p.playbook_id = ms.playbook_id;
