-- Let the verified Douyin playbooks switch from the default mobile-login
-- screen to email login, accept the login agreement, then fill saved credentials.
-- First successful login can land on a "请选择店铺" page; treat that page as
-- post-login so the existing per-playbook shop selection step can click the
-- target shop by its configured selector.
WITH target_playbooks(playbook_id) AS (
    VALUES
        ('browser-collection-e7456c34e4'),
        ('browser-collection-af964a23bc'),
        ('browser-collection-5f14be0cb4'),
        ('browser-collection-bcd0b552d1'),
        ('browser-collection-eff0a0000f'),
        ('browser-collection-91fe9866c4')
),
login_configured AS (
    SELECT
        p.playbook_id,
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        jsonb_set(
                            jsonb_set(
                                p.playbook_body,
                                '{steps,1,username_selector}',
                                to_jsonb('input[name="email"], input[placeholder="请输入邮箱"]'::text),
                                true
                            ),
                            '{steps,1,password_selector}',
                            to_jsonb('input[name="password"], input[type="password"]'::text),
                            true
                        ),
                        '{steps,1,submit_selector}',
                        to_jsonb('.account-center-action-button:has-text("登录"), button:has-text("登录"), button:has-text("登 录")'::text),
                        true
                    ),
                    '{steps,1,login_mode_selectors}',
                    '["text=邮箱登录"]'::jsonb,
                    true
                ),
                '{steps,1,pre_submit_click_selectors}',
                '["input[type=\"checkbox\"].auxo-checkbox-input"]'::jsonb,
                true
            ),
            '{steps,1,post_login_wait_selector}',
            to_jsonb('.auxo-btn-dashed, .auxo-pagination-next, text=请选择店铺'::text),
            true
        ) AS body
    FROM public.playbooks p
    JOIN target_playbooks t ON t.playbook_id = p.playbook_id
    WHERE p.playbook_body #>> '{steps,1,id}' = 'login_if_needed'
      AND p.playbook_body #>> '{steps,1,action}' = 'login_if_needed'
),
with_optional_shop_step AS (
    SELECT
        playbook_id,
        CASE
            WHEN jsonb_path_exists(body, '$.steps[*] ? (@.id == "select_login_shop_if_present")') THEN body
            ELSE jsonb_set(
                body,
                '{steps}',
                jsonb_build_array(
                    body #> '{steps,0}',
                    body #> '{steps,1}',
                    jsonb_build_object(
                        'id', 'select_login_shop_if_present',
                        'action', 'click_if_present',
                        'selector', body #>> '{steps,4,selector}',
                        'timeout_ms', 30000,
                        'visible_timeout_ms', 1000
                    )
                )
                    || COALESCE(
                        (SELECT jsonb_agg(step.value ORDER BY ord)
                         FROM jsonb_array_elements(body #> '{steps}') WITH ORDINALITY AS step(value, ord)
                         WHERE ord >= 3),
                        '[]'::jsonb
                    ),
                true
            )
        END AS body
    FROM login_configured
)
UPDATE public.playbooks p
SET playbook_body = s.body,
    updated_at = now()
FROM with_optional_shop_step s
WHERE p.playbook_id = s.playbook_id;
