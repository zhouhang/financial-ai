-- Prevent duplicate active digest subscriptions for the same recipient/scope.
-- This keeps scheduler compensation idempotent even if subscription setup is retried.

CREATE UNIQUE INDEX IF NOT EXISTS idx_recon_digest_subscriptions_active_natural_key
    ON public.recon_digest_subscriptions (
        company_id,
        domain,
        view,
        period,
        target_type,
        conversation_id,
        (scope::text),
        (recipient_json::text)
    )
    WHERE status = 'active';
