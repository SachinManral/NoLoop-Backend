"""Unit tests for CacheService."""

from app.core.cache import CacheService


def test_cache_set_and_get():
    cache = CacheService()
    cache.set("claim:CLM-1001", {"status": "APPROVED", "amount": 50000}, ttl_seconds=60)

    val = cache.get("claim:CLM-1001")
    assert val is not None
    assert val["status"] == "APPROVED"
    assert val["amount"] == 50000


def test_cache_miss():
    cache = CacheService()
    assert cache.get("non_existent_key") is None


def test_cache_delete():
    cache = CacheService()
    cache.set("key1", "val1")
    assert cache.get("key1") == "val1"

    cache.delete("key1")
    assert cache.get("key1") is None
