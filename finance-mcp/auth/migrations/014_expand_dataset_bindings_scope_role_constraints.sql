-- 014: 扩展 dataset_bindings 的执行作用域与动态角色编码约束

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'dataset_bindings_scope_check'
          AND conrelid = 'public.dataset_bindings'::regclass
    ) THEN
        ALTER TABLE public.dataset_bindings DROP CONSTRAINT dataset_bindings_scope_check;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'dataset_bindings_role_check'
          AND conrelid = 'public.dataset_bindings'::regclass
    ) THEN
        ALTER TABLE public.dataset_bindings DROP CONSTRAINT dataset_bindings_role_check;
    END IF;
END $$;

ALTER TABLE public.dataset_bindings
    ADD CONSTRAINT dataset_bindings_scope_check CHECK (
        (binding_scope)::text = ANY (
            ARRAY[
                ('recon'::character varying)::text,
                ('proc'::character varying)::text,
                ('exception'::character varying)::text,
                ('generic'::character varying)::text,
                ('execution_scheme'::character varying)::text,
                ('execution_run_plan'::character varying)::text,
                ('recon_scheme'::character varying)::text,
                ('recon_task'::character varying)::text
            ]
        )
    );

ALTER TABLE public.dataset_bindings
    ADD CONSTRAINT dataset_bindings_role_check CHECK (
        (role_code)::text ~ '^(source|target|aux|input|output|left|right)(_[0-9]+)?$'
    );
