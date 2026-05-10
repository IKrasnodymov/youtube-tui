from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

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
_EXTRACT_SEMAPHORE = asyncio.Semaphore(3)
_INFLIGHT: dict[tuple[Any, ...], asyncio.Task[Any]] = {}
_INFLIGHT_LOCK = asyncio.Lock()
T = TypeVar("T")


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
    async with _EXTRACT_SEMAPHORE:
        return await asyncio.to_thread(_extract, url, extra)


async def _dedupe_inflight(
    key: tuple[Any, ...], factory: Callable[[], Awaitable[T]]
) -> T:
    async with _INFLIGHT_LOCK:
        task = _INFLIGHT.get(key)
        if task is None:
            task = asyncio.create_task(factory())
            _INFLIGHT[key] = task
    try:
        return await asyncio.shield(task)
    finally:
        if task.done():
            async with _INFLIGHT_LOCK:
                if _INFLIGHT.get(key) is task:
                    _INFLIGHT.pop(key, None)


async def search(query: str, n: int = 25) -> list[Video]:
    key = ("search", query, n)
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)

    async def load() -> tuple[Video, ...]:
        cached = _cache.get(key)
        if cached is not None:
            return cached
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
        result = tuple(videos)
        _cache.put(key, result, _SEARCH_TTL_S)
        return result

    return list(await _dedupe_inflight(key, load))


# YouTube retired /feed/trending — use the search "trending today" filter as primary,
# fall back to a date-sorted search if that ever breaks too.
_TRENDING_SOURCES: list[tuple[str, dict[str, Any]]] = [
    (
        "https://www.youtube.com/results?search_query=trending+today&sp=EgIIAQ%253D%253D",
        {"extract_flat": "in_playlist"},
    ),
    ("ytsearch50:trending today", {"extract_flat": "in_playlist"}),
]


async def trending(n: int = 25) -> list[Video]:
    key = ("trending", n)
    cached = _cache.get(key)
    if cached is not None:
        return list(cached)

    async def load() -> tuple[Video, ...]:
        cached = _cache.get(key)
        if cached is not None:
            return cached
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
                result = tuple(videos)
                _cache.put(key, result, _TRENDING_TTL_S)
                return result
        if last_error is not None:
            raise YTDLPError(f"all trending sources failed: {last_error}")
        return ()

    return list(await _dedupe_inflight(key, load))


async def detail(video_id: str) -> Video:
    key = ("detail", video_id)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    async def load() -> Video:
        cached = _cache.get(key)
        if cached is not None:
            return cached
        url = f"https://www.youtube.com/watch?v={video_id}"
        info = await _extract_async(url)
        video = Video.from_ytdlp(info)
        _cache.put(key, video, _DETAIL_TTL_S)
        return video

    return await _dedupe_inflight(key, load)
