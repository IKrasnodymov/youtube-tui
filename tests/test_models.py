from __future__ import annotations

from dataclasses import replace

import pytest

from youtube_tui.models import Video


def test_from_ytdlp_search_entry() -> None:
    entry = {
        "id": "abc123XYZ_-",
        "title": "How to Python",
        "channel": "Pythonistas",
        "duration": 615,
        "view_count": 12345,
        "thumbnail": "https://example.com/t.jpg",
    }
    v = Video.from_ytdlp(entry)
    assert v.id == "abc123XYZ_-"
    assert v.title == "How to Python"
    assert v.channel_name == "Pythonistas"
    assert v.duration_s == 615
    assert v.view_count == 12345
    assert v.thumbnail_url == "https://example.com/t.jpg"
    assert v.is_live is False


def test_from_ytdlp_detail_entry_with_full_metadata() -> None:
    entry = {
        "id": "DEEP_video1",
        "title": "Deep Dive",
        "uploader": "Channel Z",
        "channel_id": "UC_chan_z",
        "duration": 3723,
        "view_count": 9_999_999,
        "upload_date": "20240115",
        "description": "A long description.",
        "live_status": "is_live",
        "thumbnail": "https://example.com/d.jpg",
    }
    v = Video.from_ytdlp(entry)
    assert v.id == "DEEP_video1"
    assert v.title == "Deep Dive"
    assert v.channel_name == "Channel Z"
    assert v.channel_id == "UC_chan_z"
    assert v.published_at == "2024-01-15"
    assert v.description == "A long description."
    assert v.is_live is True


def test_from_ytdlp_falls_back_to_ytimg_thumbnail() -> None:
    entry = {
        "id": "noThumbVid",
        "title": "no thumb",
        "channel": "X",
    }
    v = Video.from_ytdlp(entry)
    assert v.thumbnail_url == "https://i.ytimg.com/vi/noThumbVid/mqdefault.jpg"


def test_from_ytdlp_extracts_id_from_webpage_url() -> None:
    entry = {
        "webpage_url": "https://www.youtube.com/watch?v=URLid12345&t=10",
        "title": "via url",
        "channel": "X",
    }
    v = Video.from_ytdlp(entry)
    assert v.id == "URLid12345"


def test_duration_human_formats() -> None:
    base = Video(id="x", title="t", channel_name="c")
    assert replace(base, duration_s=42).duration_human == "0:42"
    assert replace(base, duration_s=194).duration_human == "3:14"
    assert replace(base, duration_s=3723).duration_human == "1:02:03"
    assert replace(base, duration_s=42, is_live=True).duration_human == "LIVE"


def test_views_human_formats() -> None:
    base = Video(id="x", title="t", channel_name="c")
    assert replace(base, view_count=999).views_human == "999 views"
    assert replace(base, view_count=1500).views_human == "1.5K views"
    assert replace(base, view_count=1_500_000).views_human == "1.5M views"


def test_from_ytdlp_missing_id_raises() -> None:
    with pytest.raises(ValueError):
        Video.from_ytdlp({"title": "no id"})
