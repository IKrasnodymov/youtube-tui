from __future__ import annotations

import os

import pytest

from youtube_tui.data import cache as cache_mod
from youtube_tui.data.cache import TTLCache


def test_cache_hit_and_miss() -> None:
    c = TTLCache(max_size=4)
    assert c.get("missing") is None
    c.put("k", "v", ttl_s=60)
    assert c.get("k") == "v"


def test_cache_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    now = {"t": 1000.0}

    def fake_monotonic() -> float:
        return now["t"]

    monkeypatch.setattr(cache_mod.time, "monotonic", fake_monotonic)

    c = TTLCache(max_size=4)
    c.put("k", "v", ttl_s=10)
    assert c.get("k") == "v"

    now["t"] = 1009.999
    assert c.get("k") == "v"

    now["t"] = 1010.0
    assert c.get("k") is None
    assert len(c) == 0


def test_cache_eviction_at_maxsize() -> None:
    c = TTLCache(max_size=3)
    c.put("a", 1, ttl_s=60)
    c.put("b", 2, ttl_s=60)
    c.put("c", 3, ttl_s=60)
    assert c.get("a") == 1  # promote 'a' to MRU
    c.put("d", 4, ttl_s=60)  # should evict LRU which is now 'b'
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3
    assert c.get("d") == 4
    assert len(c) == 3


def test_cache_update_keeps_value_fresh() -> None:
    c = TTLCache(max_size=2)
    c.put("a", 1, ttl_s=60)
    c.put("b", 2, ttl_s=60)
    c.put("a", 99, ttl_s=60)
    c.put("c", 3, ttl_s=60)
    assert c.get("b") is None
    assert c.get("a") == 99
    assert c.get("c") == 3


@pytest.mark.skipif(
    not bool(os.getenv("YTUI_NET")), reason="set YTUI_NET=1 to run live network smoke"
)
async def test_search_smoke() -> None:
    from youtube_tui.data.ytdlp_client import search

    results = await search("python tutorial", n=2)
    assert len(results) >= 1
    assert results[0].title
