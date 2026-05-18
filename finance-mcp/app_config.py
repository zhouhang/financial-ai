"""Application-level configuration shared by finance-mcp modules."""

from __future__ import annotations

import os

DEFAULT_SERVICE_PROVIDER_COMPANY_ID = "00000000-0000-0000-0000-00000000dd01"


def get_service_provider_company_id() -> str:
    """Return the Tally service provider company id for platform app ownership."""
    return os.getenv("SERVICE_PROVIDER_COMPANY_ID", DEFAULT_SERVICE_PROVIDER_COMPANY_ID).strip() or (
        DEFAULT_SERVICE_PROVIDER_COMPANY_ID
    )


SERVICE_PROVIDER_COMPANY_ID = get_service_provider_company_id()
