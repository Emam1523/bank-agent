"""In-memory TTL cache: the agent's short-term memory of answered questions.

A repeated question is answered without calling the LLM or the database.
Entries expire after a TTL so bank data is never served stale for long.
"""

import re
import time
from typing import Any, Dict, Optional, Tuple


class InMemoryCache:
    """Dict-based cache with TTL, key normalization, size limit and hit/miss stats."""

    def __init__(self, default_ttl_seconds: float = 120.0, max_entries: int = 256):
        self._store: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expires_at)
        self.default_ttl = default_ttl_seconds
        self.max_entries = max_entries
        self.hits_count = 0
        self.misses_count = 0

    @staticmethod
    def normalize_key(query: str) -> str:
        """'  Show banks in DHAKA? ' -> 'show banks in dhaka'."""
        q = re.sub(r"[?!.;,]+$", "", (query or "").strip().lower()).strip()
        return re.sub(r"\s+", " ", q)

    def get(self, query: str) -> Optional[Any]:
        """Return the cached value, or None on a miss or expired entry."""
        key = self.normalize_key(query)
        entry = self._store.get(key)
        if entry is None or entry[1] < time.time():
            self._store.pop(key, None)
            self.misses_count += 1
            return None
        self.hits_count += 1
        return entry[0]

    def set(self, query: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        """Store a value; evicts the oldest entry when full."""
        key = self.normalize_key(query)
        if not key:
            return
        if key not in self._store and len(self._store) >= self.max_entries:
            self._store.pop(next(iter(self._store)))
        ttl = self.default_ttl if ttl_seconds is None else ttl_seconds
        self._store[key] = (value, time.time() + ttl)

    def invalidate(self, query: Optional[str] = None) -> None:
        """Remove one entry, or everything when `query` is None."""
        if query is None:
            self._store.clear()
        else:
            self._store.pop(self.normalize_key(query), None)

    def stats(self) -> Dict[str, Any]:
        """Purge expired entries and return usage statistics."""
        now = time.time()
        self._store = {k: v for k, v in self._store.items() if v[1] >= now}
        total = self.hits_count + self.misses_count
        return {
            "total_keys": len(self._store),
            "hits": self.hits_count,
            "misses": self.misses_count,
            "hit_ratio_percent": round(self.hits_count / total * 100, 2) if total else 0.0,
            "keys": list(self._store),
        }
