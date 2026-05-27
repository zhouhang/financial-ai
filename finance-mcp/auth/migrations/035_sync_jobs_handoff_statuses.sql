ALTER TABLE public.sync_jobs
    ALTER COLUMN job_status TYPE varchar(32);

ALTER TABLE public.sync_jobs
    DROP CONSTRAINT IF EXISTS sync_jobs_status_check;

ALTER TABLE public.sync_jobs
    ADD CONSTRAINT sync_jobs_status_check CHECK (
        (job_status)::text = ANY (
            ARRAY[
                ('pending'::character varying)::text,
                ('running'::character varying)::text,
                ('waiting_human_verification'::character varying)::text,
                ('resuming'::character varying)::text,
                ('success'::character varying)::text,
                ('failed'::character varying)::text,
                ('cancelled'::character varying)::text,
                ('partial'::character varying)::text
            ]
        )
    );
