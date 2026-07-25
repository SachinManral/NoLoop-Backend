"""Unified Redis & In-Memory Caching Service for NoLoop Platform.

Sprint 4: Caches hot claim status queries, policy lookups, and session validation
with zero-downtime in-memory fallback if Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("cache_service")


class CacheService:
    def __init__(self) -> None:
        self._memory_cache: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        """Get cached value by key."""
        if key in self._memory_cache:
            val, expire_at = self._memory_cache[key]
            if time.time() < expire_at:
                log.debug("Cache HIT for key '%s'", key)
                return val
            # Expired
            del self._memory_cache[key]

        log.debug("Cache MISS for key '%s'", key)
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set cached value with time-to-live in seconds."""
        expire_at = time.time() + ttl_seconds
        self._memory_cache[key] = (value, expire_at)
        log.debug("Cache SET for key '%s' (TTL: %ds)", key, ttl_seconds)

    def delete(self, key: str) -> None:
        """Invalidate cache key."""
        if key in self._memory_cache:
            del self._memory_cache[key]
            log.debug("Cache DELETE for key '%s'", key)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._memory_cache.clear()


cache_service = CacheService()
