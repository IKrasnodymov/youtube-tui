from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional


class PlaybackMode(Enum):
    EXTERNAL = "external"
    AUDIO_ONLY = "audio"
    IN_TERMINAL = "kitty"


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    channel_name: str
    channel_id: Optional[str] = None
    duration_s: Optional[int] = None
    view_count: Optional[int] = None
    published_at: Optional[str] = None  # ISO8601 date string
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    is_live: bool = False

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    @property
    def duration_human(self) -> str:
        if self.is_live:
            return "LIVE"
        if self.duration_s is None:
            return "—"
        h, rem = divmod(int(self.duration_s), 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def views_human(self) -> str:
        if self.view_count is None:
            return ""
        n = int(self.view_count)
        if n < 1000:
            return f"{n} views"
        if n < 1_000_000:
            return f"{n/1000:.1f}K views".replace(".0K", "K")
        if n < 1_000_000_000:
            return f"{n/1_000_000:.1f}M views".replace(".0M", "M")
        return f"{n/1_000_000_000:.1f}B views".replace(".0B", "B")

    @classmethod
    def from_ytdlp(cls, entry: dict[str, Any]) -> "Video":
        vid = (
            entry.get("id")
            or entry.get("video_id")
            or _id_from_url(entry.get("url") or entry.get("webpage_url") or "")
            or ""
        )
        if not vid:
            raise ValueError(f"yt-dlp entry missing video id: {entry!r}")

        title = entry.get("title") or entry.get("fulltitle") or "(untitled)"
        channel_name = (
            entry.get("channel")
            or entry.get("uploader")
            or entry.get("creator")
            or "(unknown)"
        )
        channel_id = entry.get("channel_id") or entry.get("uploader_id")

        duration = entry.get("duration")
        duration_s = int(duration) if isinstance(duration, (int, float)) else None

        view_count = entry.get("view_count")
        view_count = int(view_count) if isinstance(view_count, (int, float)) else None

        published_at = _normalize_upload_date(
            entry.get("upload_date") or entry.get("release_date")
        )
        if published_at is None and isinstance(entry.get("timestamp"), (int, float)):
            published_at = (
                datetime.fromtimestamp(entry["timestamp"], tz=timezone.utc)
                .date()
                .isoformat()
            )

        thumbnail_url = entry.get("thumbnail")
        if not thumbnail_url:
            thumbs = entry.get("thumbnails") or []
            thumbnail_url = _pick_thumbnail(thumbs)
        if not thumbnail_url and vid:
            thumbnail_url = f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"

        description = entry.get("description")

        is_live = bool(
            entry.get("is_live")
            or entry.get("live_status") in {"is_live", "is_upcoming"}
        )

        return cls(
            id=vid,
            title=title,
            channel_name=channel_name,
            channel_id=channel_id,
            duration_s=duration_s,
            view_count=view_count,
            published_at=published_at,
            thumbnail_url=thumbnail_url,
            description=description,
            is_live=is_live,
        )


@dataclass(frozen=True)
class SearchResult:
    query: str
    videos: tuple[Video, ...]
    fetched_at: float

    @classmethod
    def make(cls, query: str, videos: Iterable[Video], fetched_at: float) -> "SearchResult":
        return cls(query=query, videos=tuple(videos), fetched_at=fetched_at)


def _id_from_url(url: str) -> Optional[str]:
    if not url:
        return None
    if "watch?v=" in url:
        tail = url.split("watch?v=", 1)[1]
        return tail.split("&", 1)[0] or None
    if "youtu.be/" in url:
        tail = url.split("youtu.be/", 1)[1]
        return tail.split("?", 1)[0].split("/", 1)[0] or None
    return None


def _normalize_upload_date(value: Any) -> Optional[str]:
    if not value:
        return None
    s = str(value)
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _pick_thumbnail(thumbs: list[dict[str, Any]]) -> Optional[str]:
    if not thumbs:
        return None
    rated = [t for t in thumbs if t.get("url")]
    if not rated:
        return None
    rated.sort(key=lambda t: (t.get("height") or 0) + (t.get("width") or 0))
    medium = [t for t in rated if 100 <= (t.get("height") or 0) <= 240]
    if medium:
        return medium[-1]["url"]
    return rated[len(rated) // 2]["url"]
