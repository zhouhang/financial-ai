ALTER TABLE IF EXISTS public.data_sources
    DROP CONSTRAINT IF EXISTS data_sources_source_kind_check;

ALTER TABLE IF EXISTS public.data_sources
    ADD CONSTRAINT data_sources_source_kind_check CHECK (
        (source_kind)::text = ANY (
            ARRAY[
                ('platform_oauth'::character varying)::text,
                ('database'::character varying)::text,
                ('api'::character varying)::text,
                ('file'::character varying)::text,
                ('browser'::character varying)::text,
                ('browser_playbook'::character varying)::text,
                ('desktop_cli'::character varying)::text
            ]
        )
    );
