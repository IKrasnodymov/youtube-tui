from __future__ import annotations

import time
from dataclasses import replace

import pytest

from youtube_tui.models import Video
from youtube_tui.storage.db import Library


def _make_video(vid: str = "abc123", title: str = "Hello") -> Video:
    return Video(
        id=vid,
        title=title,
        channel_name="Some Channel",
        channel_id="UC123",
        duration_s=42,
        view_count=1000,
        published_at="2024-01-01",
        thumbnail_url="https://i.ytimg.com/vi/abc123/mqdefault.jpg",
        description="desc",
        is_live=False,
    )


@pytest.fixture
def lib(tmp_path):
    library = Library(path=tmp_path / "test.db")
    try:
        yield library
    finally:
        library.close()


def test_upsert_video_idempotent(lib: Library) -> None:
    v1 = _make_video(title="First")
    lib.upsert_video(v1)
    v2 = replace(v1, title="Second")
    lib.upsert_video(v2)

    cur = lib._conn.execute("SELECT id, title FROM videos")
    rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["id"] == v1.id
    assert rows[0]["title"] == "Second"


def test_record_watch_appends_history_and_upserts_video(lib: Library) -> None:
    v = _make_video()
    lib.record_watch(v, position_s=10)

    vrows = lib._conn.execute("SELECT id FROM videos").fetchall()
    assert len(vrows) == 1
    hrows = lib._conn.execute(
        "SELECT video_id, position_s FROM history"
    ).fetchall()
    assert len(hrows) == 1
    assert hrows[0]["video_id"] == v.id
    assert hrows[0]["position_s"] == 10

    time.sleep(0.01)
    lib.record_watch(v, position_s=25)
    hrows2 = lib._conn.execute("SELECT position_s FROM history").fetchall()
    assert len(hrows2) == 2


def test_toggle_favorite_round_trip(lib: Library) -> None:
    v = _make_video()
    assert lib.is_favorited(v.id) is False

    state1 = lib.toggle_favorite(v)
    assert state1 is True
    assert lib.is_favorited(v.id) is True

    state2 = lib.toggle_favorite(v)
    assert state2 is False
    assert lib.is_favorited(v.id) is False

    vrows = lib._conn.execute(
        "SELECT id FROM videos WHERE id = ?", (v.id,)
    ).fetchall()
    assert len(vrows) == 1


def test_recent_history_deduped_and_ordered(lib: Library) -> None:
    a = _make_video("aaa", "A")
    b = _make_video("bbb", "B")

    lib.record_watch(a)
    time.sleep(0.01)
    lib.record_watch(b)
    time.sleep(0.01)
    lib.record_watch(a)

    history = lib.recent_history()
    assert [v.id for v in history] == ["aaa", "bbb"]


def test_recent_searches_increments_hits_and_orders_by_recency(lib: Library) -> None:
    lib.record_search("python")
    time.sleep(0.01)
    lib.record_search("rust")
    time.sleep(0.01)
    lib.record_search("python")

    rows = lib._conn.execute(
        "SELECT query, hits FROM search_history WHERE query = 'python'"
    ).fetchall()
    assert rows[0]["hits"] == 2

    queries = lib.recent_searches()
    assert queries == ["python", "rust"]


def test_list_favorites_orders_by_added_at_desc(lib: Library) -> None:
    a = _make_video("aaa", "A")
    b = _make_video("bbb", "B")
    c = _make_video("ccc", "C")

    lib.toggle_favorite(a)
    time.sleep(0.01)
    lib.toggle_favorite(b)
    time.sleep(0.01)
    lib.toggle_favorite(c)

    favs = lib.list_favorites()
    assert [v.id for v in favs] == ["ccc", "bbb", "aaa"]
