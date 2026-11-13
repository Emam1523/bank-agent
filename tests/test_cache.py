"""Tests for In-Memory Cache (Normalization, TTL, Expiration, Stats)."""

import time
import pytest
from agent.cache import InMemoryCache


def test_cache_set_and_get():
    """Verify that a value stored in cache can be retrieved."""
    cache = InMemoryCache(default_ttl_seconds=60)
    cache.set("Show all banks in Dhaka", "Sonali Bank, BRAC Bank")

    result = cache.get("Show all banks in Dhaka")
    assert result == "Sonali Bank, BRAC Bank"
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 0


def test_cache_normalization():
    """Verify case, punctuation, and whitespace normalization produce cache hits."""
    cache = InMemoryCache(default_ttl_seconds=60)
    cache.set("Show all active banks in Dhaka", "Cached Result")

    # Lowercase + question mark
    assert cache.get("show all active banks in dhaka?") == "Cached Result"
    # Multiple spaces + trailing exclamation
    assert cache.get("  SHOW   all  active   BANKS in Dhaka!  ") == "Cached Result"
    # Semicolon / period
    assert cache.get("Show all active banks in Dhaka.") == "Cached Result"


def test_cache_miss():
    """Verify cache miss returns None and increments misses count."""
    cache = InMemoryCache(default_ttl_seconds=60)
    result = cache.get("Non-existent query")
    assert result is None
    stats = cache.stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_cache_ttl_expiration():
    """Verify that entries expire and return None after TTL."""
    # Create cache with 0.5s TTL
    cache = InMemoryCache(default_ttl_seconds=0.5)
    cache.set("Quick query", "Temporary data")

    # Immediate lookup -> hit
    assert cache.get("Quick query") == "Temporary data"

    # Wait for TTL to elapse
    time.sleep(0.7)

    # Lookup after TTL -> miss and removed
    assert cache.get("Quick query") is None
    stats = cache.stats()
    assert stats["total_keys"] == 0


def test_cache_invalidation_specific_and_all():
    """Verify single key invalidation and full cache flush."""
    cache = InMemoryCache(default_ttl_seconds=60)
    cache.set("Query 1", "Data 1")
    cache.set("Query 2", "Data 2")

    # Invalidate Query 1
    cache.invalidate("Query 1")
    assert cache.get("Query 1") is None
    assert cache.get("Query 2") == "Data 2"

    # Flush all
    cache.invalidate()
    assert cache.get("Query 2") is None
    assert cache.stats()["total_keys"] == 0


def test_cache_stats_and_hit_ratio():
    """Verify hit ratio calculation and stats accuracy."""
    cache = InMemoryCache(default_ttl_seconds=60)
    cache.set("q1", "ans1")

    cache.get("q1")  # Hit
    cache.get("q1")  # Hit
    cache.get("q2")  # Miss
    cache.get("q3")  # Miss

    stats = cache.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 2
    assert stats["hit_ratio_percent"] == 50.0
