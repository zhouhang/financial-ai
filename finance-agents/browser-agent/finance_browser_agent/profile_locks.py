"""Per-shop Chrome profile lock registry.

Chrome ``user-data-dir`` is not safe for concurrent processes — two browser sessions writing the
same profile can corrupt cookies and storage. The dispatcher loop wraps every browser run in an
``asyncio.Lock`` keyed by ``shop_id``: concurrent jobs for different shops run in parallel,
concurrent jobs for the same shop serialize.

This means ``BROWSER_AGENT_MAX_CONCURRENCY=2`` only achieves 2x throughput when the queue
contains jobs for ≥2 distinct shops. Single-shop first-store therefore caps at 1x by design.
"""

from __future__ import annotations

import asyncio


class ProfileLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for_shop(self, shop_id: str) -> asyncio.Lock:
        key = str(shop_id or "unknown").strip() or "unknown"
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]
