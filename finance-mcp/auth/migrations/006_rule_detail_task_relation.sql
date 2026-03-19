BEGIN;

ALTER TABLE public.rule_detail
ADD COLUMN IF NOT EXISTS name character varying(255);

ALTER TABLE public.rule_detail
ADD COLUMN IF NOT EXISTS task_id integer;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'rule_detail_task_id_fkey'
    ) THEN
        ALTER TABLE public.rule_detail
        ADD CONSTRAINT rule_detail_task_id_fkey
        FOREIGN KEY (task_id) REFERENCES public.user_tasks(id) ON DELETE SET NULL;
    END IF;
END $$;

UPDATE public.rule_detail AS rd
SET task_id = ut.id
FROM public.user_tasks AS ut
WHERE rd.rule_type = 'bus'
  AND rd.rule_code = ut.task_code
  AND rd.task_id IS NULL;

UPDATE public.rule_detail AS rd
SET task_id = ut.id
FROM public.user_tasks AS ut
JOIN public.rule_detail AS parent_rule
  ON parent_rule.task_id = ut.id
 AND parent_rule.rule_type = 'bus'
WHERE rd.rule_type = 'file'
  AND rd.task_id IS NULL
  AND parent_rule.rule ->> 'file_rule_code' = rd.rule_code;

UPDATE public.rule_detail
SET name = CASE
    WHEN rule_type = 'bus' AND jsonb_typeof(rule) = 'object' AND rule ? 'merge_rules'
        THEN COALESCE(rule -> 'merge_rules' -> 0 ->> 'rule_name', remark, rule_code)
    WHEN rule_type = 'bus' AND jsonb_typeof(rule) = 'object' AND rule ? 'rules'
        THEN COALESCE(rule -> 'rules' -> 0 ->> 'rule_name', rule ->> 'role_desc', remark, rule_code)
    WHEN rule_type = 'bus' AND jsonb_typeof(rule) = 'object'
        THEN COALESCE(rule ->> 'role_desc', remark, rule_code)
    ELSE COALESCE(remark, rule_code)
END
WHERE name IS NULL OR btrim(name) = '';

CREATE INDEX IF NOT EXISTS idx_rule_detail_task_id ON public.rule_detail(task_id);
CREATE INDEX IF NOT EXISTS idx_rule_detail_name ON public.rule_detail(name);

COMMIT;
