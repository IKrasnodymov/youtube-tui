from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import httpx

from ..config import THUMB_CACHE_DIR, ensure_dirs

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# Cap concurrent thumbnail downloads — without this, mounting 25 cards
# fires 25 simultaneous TLS handshakes against i.ytimg.com.
_FETCH_SEMAPHORE = asyncio.Semaphore(8)
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None
_HTTP_LOCK = asyncio.Lock()
_NEGATIVE_TTL_S = 300.0
_NEGATIVE_CACHE: dict[tuple[str, str], float] = {}
_PRUNE_INTERVAL_S = 600.0
_MAX_CACHE_FILES = 800
_last_prune = 0.0

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
    )
}


async def _get_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        async with _HTTP_LOCK:
            if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
                _HTTP_CLIENT = httpx.AsyncClient(
                    timeout=_TIMEOUT,
                    headers=_DEFAULT_HEADERS,
                    limits=httpx.Limits(
                        max_keepalive_connections=8, max_connections=16
                    ),
                )
    return _HTTP_CLIENT


async def aclose_client() -> None:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None and not _HTTP_CLIENT.is_closed:
        try:
            await _HTTP_CLIENT.aclose()
        except Exception:
            pass
    _HTTP_CLIENT = None


def _is_cached(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _write_atomic(target: Path, content: bytes) -> None:
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(target)


def _prune_cache() -> None:
    global _last_prune
    now = time.monotonic()
    if now - _last_prune < _PRUNE_INTERVAL_S:
        return
    _last_prune = now
    try:
        files = [p for p in THUMB_CACHE_DIR.iterdir() if p.is_file()]
    except OSError:
        return
    overflow = len(files) - _MAX_CACHE_FILES
    if overflow <= 0:
        return
    def mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    files.sort(key=mtime)
    for path in files[:overflow]:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


async def fetch_thumbnail(video_id: str, url: str) -> Optional[Path]:
    ensure_dirs()
    await asyncio.to_thread(_prune_cache)
    negative_key = (video_id, url)
    failed_at = _NEGATIVE_CACHE.get(negative_key)
    if failed_at is not None and time.monotonic() - failed_at < _NEGATIVE_TTL_S:
        return None
    target = THUMB_CACHE_DIR / f"{video_id}.jpg"
    if _is_cached(target):
        return target
    async with _FETCH_SEMAPHORE:
        if _is_cached(target):
            return target
        try:
            client = await _get_client()
            r = await client.get(url)
            r.raise_for_status()
            await asyncio.to_thread(_write_atomic, target, r.content)
            _NEGATIVE_CACHE.pop(negative_key, None)
            return target
        except Exception:
            target.unlink(missing_ok=True)
            _NEGATIVE_CACHE[negative_key] = time.monotonic()
            return None
