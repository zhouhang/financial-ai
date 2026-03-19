BEGIN;

UPDATE public.user_tasks
SET user_id = (
    SELECT id
    FROM public.users
    WHERE username = 'admin'
    LIMIT 1
)
WHERE task_code IN ('verif_recog', 'audio_recon', 'verif_recog_merge');

UPDATE public.rule_detail
SET rule_type = 'proc'
WHERE id IN (2, 3);

UPDATE public.rule_detail
SET rule_type = 'recon'
WHERE id = 4;

COMMIT;
