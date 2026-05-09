ALTER TABLE public.sync_jobs
    DROP CONSTRAINT IF EXISTS sync_jobs_trigger_mode_check;

ALTER TABLE public.sync_jobs
    ADD CONSTRAINT sync_jobs_trigger_mode_check CHECK (
        (trigger_mode)::text = ANY (
            ARRAY[
                ('manual'::character varying)::text,
                ('scheduled'::character varying)::text,
                ('schedule'::character varying)::text,
                ('event'::character varying)::text,
                ('retry'::character varying)::text,
                ('initial'::character varying)::text,
                ('daily'::character varying)::text
            ]
        )
    );
