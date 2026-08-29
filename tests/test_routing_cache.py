"""Hermetic tests for router/routing_cache.py structured-log cache events."""

import json
import time

import pytest

import router.routing_cache as mod
from router.logger import (
    ROUTING_CACHE_EXPIRED,
    ROUTING_CACHE_HIT,
    ROUTING_CACHE_MISS,
    ROUTING_CACHE_PUT,
    StructuredLogger,
)
from router.ollama_scorer import RoutingResult
from router.routing_cache import LRURoutingCache, TTLRoutingCache


def _value() -> RoutingResult:
    return RoutingResult(target_files=["a.py"], confidence=0.9, reasoning="r")


@pytest.fixture
def capture_logger(tmp_path, monkeypatch):
    lg = StructuredLogger(log_dir=tmp_path)
    monkeypatch.setattr(mod, "logger", lg)
    yield lg
    lg.close()


def _read_records(tmp_path):
    (logfile,) = tmp_path.glob("session_*.jsonl")
    return [json.loads(line) for line in logfile.read_text("utf-8").strip().splitlines()]


# --- LRU ---


def test_lru_put_then_get_hit(capture_logger, tmp_path):
    cache = LRURoutingCache(max_entries=8)
    cache.put("k1", _value())
    out = cache.get("k1")

    assert out is not None
    capture_logger.flush()

    records = _read_records(tmp_path)
    assert [r["event"] for r in records] == [ROUTING_CACHE_PUT, ROUTING_CACHE_HIT]
    assert records[0]["cache"] == "lru"
    assert records[0]["key"] == "k1"
    assert records[0]["size"] == 1
    assert records[0]["evicted"] is None
    assert records[1]["cache"] == "lru"
    assert records[1]["key"] == "k1"
    assert records[1]["size"] == 1


def test_lru_get_miss(capture_logger, tmp_path):
    cache = LRURoutingCache(max_entries=8)
    out = cache.get("unknown")

    assert out is None
    capture_logger.flush()

    (rec,) = _read_records(tmp_path)
    assert rec["event"] == ROUTING_CACHE_MISS
    assert rec["cache"] == "lru"
    assert rec["key"] == "unknown"
    assert rec["size"] == 0


def test_lru_put_eviction_reports_evicted_key(capture_logger, tmp_path):
    cache = LRURoutingCache(max_entries=2)
    cache.put("a", _value())
    cache.put("b", _value())
    cache.put("c", _value())  # over capacity -> evicts oldest ("a")

    # "a" should have been evicted and no longer be retrievable
    assert cache.get("a") is None
    capture_logger.flush()

    records = _read_records(tmp_path)
    assert [r["event"] for r in records] == [
        ROUTING_CACHE_PUT,
        ROUTING_CACHE_PUT,
        ROUTING_CACHE_PUT,
        ROUTING_CACHE_MISS,
    ]
    assert records[0]["evicted"] is None
    assert records[1]["evicted"] is None
    assert records[2]["evicted"] == "a"
    assert records[2]["size"] == 2
    # get("a") after eviction is a miss on the now-2-entry cache
    assert records[3]["event"] == ROUTING_CACHE_MISS
    assert records[3]["size"] == 2


# --- TTL ---


def test_ttl_put_then_get_fresh_hit(capture_logger, tmp_path):
    cache = TTLRoutingCache(max_entries=8, ttl_seconds_provider=lambda: 100.0)
    cache.put("k", _value())
    out = cache.get("k")

    assert out is not None
    capture_logger.flush()

    records = _read_records(tmp_path)
    assert [r["event"] for r in records] == [ROUTING_CACHE_PUT, ROUTING_CACHE_HIT]
    assert records[0]["cache"] == "ttl"
    assert records[0]["key"] == "k"
    assert records[0]["size"] == 1
    assert records[0]["evicted"] is None
    assert records[1]["cache"] == "ttl"
    assert records[1]["size"] == 1
    assert records[1]["ttl_seconds"] == 100.0


def test_ttl_get_expired(capture_logger, tmp_path):
    # TTL of 0.0 => any entry is instantly stale once time has advanced past it.
    cache = TTLRoutingCache(max_entries=8, ttl_seconds_provider=lambda: 0.0)
    cache.put("k", _value())
    time.sleep(0.01)
    out = cache.get("k")

    assert out is None
    capture_logger.flush()

    records = _read_records(tmp_path)
    assert [r["event"] for r in records] == [ROUTING_CACHE_PUT, ROUTING_CACHE_EXPIRED]
    assert records[1]["cache"] == "ttl"
    assert records[1]["key"] == "k"
    assert records[1]["ttl_seconds"] == 0.0
    assert isinstance(records[1]["age_ms"], int)
    assert records[1]["age_ms"] >= 0


def test_ttl_get_miss(capture_logger, tmp_path):
    cache = TTLRoutingCache(max_entries=8, ttl_seconds_provider=lambda: 100.0)
    out = cache.get("unknown")

    assert out is None
    capture_logger.flush()

    (rec,) = _read_records(tmp_path)
    assert rec["event"] == ROUTING_CACHE_MISS
    assert rec["cache"] == "ttl"
    assert rec["key"] == "unknown"
    assert rec["size"] == 0
    assert rec["ttl_seconds"] == 100.0


def test_ttl_put_eviction_reports_oldest_key(capture_logger, tmp_path):
    cache = TTLRoutingCache(max_entries=2, ttl_seconds_provider=lambda: 100.0)
    cache.put("a", _value())
    cache.put("b", _value())
    cache.put("c", _value())  # over capacity -> evicts oldest by timestamp ("a")

    assert cache.get("a") is None
    capture_logger.flush()

    records = _read_records(tmp_path)
    assert records[2]["event"] == ROUTING_CACHE_PUT
    assert records[2]["evicted"] == "a"
    assert records[2]["size"] == 2
