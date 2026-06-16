-- Douyin order range picker can close after selecting the start day. Configure
-- the end input so the browser runner can reopen the panel and select the same
-- biz_date as range end before querying paged JSON results.
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
    WHERE step.value->>'id' = 'set_order_time_to_biz_date'
      AND step.value->>'action' = 'set_range_calendar_day'
)
UPDATE public.playbooks p
SET playbook_body = jsonb_set(
        p.playbook_body,
        ARRAY['steps', ms.step_index::text, 'end_selector'],
        to_jsonb('input[placeholder=''结束时间''], input[placeholder=''结束日期'']'::text),
        true
    ),
    updated_at = now()
FROM matched_steps ms
WHERE p.playbook_id = ms.playbook_id;
