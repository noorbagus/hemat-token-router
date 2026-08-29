"""Thread-safe bounded caching for routing results with LRU and TTL variants.

This module extracts the duplicated caching logic from dispatcher.py into
a reusable, tested component that maintains the original semantics exactly:
- LRU cache: recency-based eviction (popitem(last=False)) when over capacity
- TTL cache: timestamp-based expiration + oldest-entry eviction when over capacity

Thread safety is preserved via per-cache locks.
"""

import threading
import time
from collections import OrderedDict
from typing import Callable, Dict, Optional, Tuple

from router.logger import (
    logger,
    ROUTING_CACHE_HIT,
    ROUTING_CACHE_MISS,
    ROUTING_CACHE_EXPIRED,
    ROUTING_CACHE_PUT,
)
from router.ollama_scorer import RoutingResult


__all__ = [
    "LRURoutingCache",
    "TTLRoutingCache",
]


class LRURoutingCache:
    """Thread-safe bounded LRU cache for RoutingResult keyed by session key.

    Semantics matching original _ROUTING_CACHE:
    - On get: existing entries are moved to the end (recency bump)
    - On put: after insertion, if over capacity, evict the oldest (first entry)
    - Capacity capped at max_entries (original: 128)
    """

    def __init__(self, max_entries: int = 128) -> None:
        self._cache: OrderedDict[str, RoutingResult] = OrderedDict()
        self._lock: threading.Lock = threading.Lock()
        self._max_entries: int = max_entries

    def get(self, key: str) -> Optional[RoutingResult]:
        """Lookup a cached entry and bump its recency if present."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                self._cache.move_to_end(key)
            size = len(self._cache)
            result = entry
        if result is not None:
            logger.log(ROUTING_CACHE_HIT, cache="lru", key=key, size=size)
        else:
            logger.log(ROUTING_CACHE_MISS, cache="lru", key=key, size=size)
        return result

    def put(self, key: str, value: RoutingResult) -> None:
        """Insert/replace an entry, evicting oldest if over capacity."""
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            evicted = None
            if len(self._cache) > self._max_entries:
                evicted, _ = self._cache.popitem(last=False)
            size = len(self._cache)
        logger.log(ROUTING_CACHE_PUT, cache="lru", key=key, size=size, evicted=evicted)

    def __len__(self) -> int:
        """Return current number of cached entries (for testing)."""
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        """Clear all cached entries (for testing)."""
        with self._lock:
            self._cache.clear()


class TTLRoutingCache:
    """Thread-safe bounded TTL cache for RoutingResult keyed by context directory.

    Semantics matching original _ROUTING_TTL_CACHE:
    - On get: entries older than TTL are evicted and None is returned
    - On put: after insertion, if over capacity, evict the oldest entry by timestamp
    - Capacity capped at max_entries (original: 16)
    """

    def __init__(
        self,
        max_entries: int = 16,
        default_ttl_seconds: float = 120.0,
        ttl_seconds_provider: Optional[Callable[[], float]] = None,
    ) -> None:
        self._cache: Dict[str, Tuple[float, RoutingResult]] = {}
        self._lock: threading.Lock = threading.Lock()
        self._max_entries: int = max_entries
        self._default_ttl_seconds: float = default_ttl_seconds
        self._ttl_seconds_provider: Callable[[], float] = (
            ttl_seconds_provider if ttl_seconds_provider is not None
            else lambda: self._get_env_ttl()
        )

    def _get_env_ttl(self) -> float:
        """Read TTL from environment variable CSMART_ROUTING_TTL if present."""
        import os
        raw = os.environ.get("CSMART_ROUTING_TTL", "")
        if not raw:
            return self._default_ttl_seconds
        try:
            return max(0.0, float(raw))
        except ValueError:
            return self._default_ttl_seconds

    def ttl_seconds(self) -> float:
        """Return current effective TTL from environment or default."""
        return self._ttl_seconds_provider()

    def get(self, key: str) -> Optional[RoutingResult]:
        """Lookup a cached entry, evicting if stale (older than TTL)."""
        now = time.monotonic()
        ttl = self.ttl_seconds()
        with self._lock:
            size = len(self._cache)
            result: Optional[RoutingResult] = None
            outcome = "miss"
            age_ms = 0
            entry = self._cache.get(key)
            if entry is not None:
                stored_ts, routing = entry
                if now - stored_ts > ttl:
                    self._cache.pop(key, None)
                    outcome = "expired"
                    age_ms = int((now - stored_ts) * 1000)
                    size = len(self._cache)
                else:
                    outcome = "hit"
                    size = len(self._cache)
                    result = routing
        if outcome == "hit":
            logger.log(ROUTING_CACHE_HIT, cache="ttl", key=key, size=size, ttl_seconds=ttl)
        elif outcome == "expired":
            logger.log(ROUTING_CACHE_EXPIRED, cache="ttl", key=key, ttl_seconds=ttl, age_ms=age_ms)
        else:
            logger.log(ROUTING_CACHE_MISS, cache="ttl", key=key, size=size, ttl_seconds=ttl)
        return result

    def put(self, key: str, value: RoutingResult) -> None:
        """Insert/replace an entry, evicting oldest if over capacity."""
        now = time.monotonic()
        with self._lock:
            self._cache[key] = (now, value)
            evicted = None
            if len(self._cache) > self._max_entries:
                # Find the oldest entry by timestamp and evict it
                oldest_key = min(
                    self._cache,
                    key=lambda k: self._cache[k][0],
                )
                self._cache.pop(oldest_key, None)
                evicted = oldest_key
            size = len(self._cache)
        logger.log(ROUTING_CACHE_PUT, cache="ttl", key=key, size=size, evicted=evicted)

    def __len__(self) -> int:
        """Return current number of cached entries (for testing)."""
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        """Clear all cached entries (for testing)."""
        with self._lock:
            self._cache.clear()
