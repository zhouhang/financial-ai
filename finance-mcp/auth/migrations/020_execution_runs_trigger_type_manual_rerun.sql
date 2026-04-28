ALTER TABLE public.execution_runs
    DROP CONSTRAINT IF EXISTS execution_runs_trigger_type_check;

ALTER TABLE public.execution_runs
    ADD CONSTRAINT execution_runs_trigger_type_check CHECK (
        (trigger_type)::text = ANY (
            ARRAY[
                ('chat'::character varying)::text,
                ('schedule'::character varying)::text,
                ('api'::character varying)::text,
                ('manual'::character varying)::text,
                ('rerun'::character varying)::text
            ]
        )
    );
