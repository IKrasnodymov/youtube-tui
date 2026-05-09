from __future__ import annotations

import asyncio
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError, YoutubeDLError

from ..models import Video
from .cache import TTLCache


class YTDLPError(RuntimeError):
    pass


_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "socket_timeout": 15,
}

_SEARCH_TTL_S = 600.0
_TRENDING_TTL_S = 600.0
_DETAIL_TTL_S = 3600.0

# Each call builds its own YoutubeDL instance, so concurrent extracts in
# separate threads are safe — no shared mutable state.
_cache = TTLCache(max_size=256)


def _build_ydl(extra: dict[str, Any] | None = None) -> yt_dlp.YoutubeDL:
    opts = dict(_BASE_OPTS)
    if extra:
        opts.update(extra)
    return yt_dlp.YoutubeDL(opts)


def _extract(url: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    ydl = _build_ydl(extra)
    try:
        info = ydl.extract_info(url, download=False)
    except (DownloadError, YoutubeDLError) as exc:
        raise YTDLPError(str(exc)) from exc
    finally:
        try:
            ydl.close()
        except Exception:
            pass
    if info is None:
        raise YTDLPError(f"yt-dlp returned no info for {url!r}")
    return info


async def _extract_async(url: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return await asyncio.to_thread(_extract, url, extra)


async def search(query: str, n: int = 25) -> list[Video]:
    key = ("search", query, n)
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)

    url = f"ytsearch{n}:{query}"
    info = await _extract_async(url, {"extract_flat": "in_playlist"})
    entries = info.get("entries") or []
    videos: list[Video] = []
    for entry in entries:
        if not entry:
            continue
        try:
            videos.append(Video.from_ytdlp(entry))
        except ValueError:
            continue

    _cache.put(key, tuple(videos), _SEARCH_TTL_S)
    return videos


# YouTube retired /feed/trending — use the search "trending today" filter as primary,
# fall back to a date-sorted search if that ever breaks too.
_TRENDING_SOURCES: list[tuple[str, dict[str, Any]]] = [
    (
        "https://www.youtube.com/results?search_query=trending+today&sp=EgIIAQ%253D%253D",
        {"extract_flat": "in_playlist"},
    ),
    ("ytsearchdate50:trending today", {"extract_flat": "in_playlist"}),
]


async def trending(n: int = 25) -> list[Video]:
    key = ("trending", n)
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)

    last_error: Exception | None = None
    for url, extra in _TRENDING_SOURCES:
        try:
            info = await _extract_async(url, extra)
        except YTDLPError as e:
            last_error = e
            continue
        entries = info.get("entries") or []
        videos: list[Video] = []
        for entry in entries[:n]:
            if not entry:
                continue
            try:
                videos.append(Video.from_ytdlp(entry))
            except ValueError:
                continue
        if videos:
            _cache.put(key, tuple(videos), _TRENDING_TTL_S)
            return videos

    if last_error is not None:
        raise YTDLPError(f"all trending sources failed: {last_error}")
    return []


async def detail(video_id: str) -> Video:
    key = ("detail", video_id)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    url = f"https://www.youtube.com/watch?v={video_id}"
    info = await _extract_async(url)
    video = Video.from_ytdlp(info)
    _cache.put(key, video, _DETAIL_TTL_S)
    return video


