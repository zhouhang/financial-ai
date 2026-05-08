ALTER TABLE public.auth_sessions
    ADD COLUMN IF NOT EXISTS extra jsonb DEFAULT '{}'::jsonb NOT NULL;
