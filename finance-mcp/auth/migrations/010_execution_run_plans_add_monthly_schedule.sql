-- 010: execution_run_plans 支持 monthly 调度

ALTER TABLE public.execution_run_plans
    DROP CONSTRAINT IF EXISTS execution_run_plans_schedule_type_check;

ALTER TABLE public.execution_run_plans
    ADD CONSTRAINT execution_run_plans_schedule_type_check CHECK (
        (schedule_type)::text = ANY (
            ARRAY[
                ('manual_trigger'::character varying)::text,
                ('daily'::character varying)::text,
                ('weekly'::character varying)::text,
                ('monthly'::character varying)::text,
                ('cron'::character varying)::text
            ]
        )
    );
