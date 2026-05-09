from __future__ import annotations

import asyncio
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


async def fetch_thumbnail(video_id: str, url: str) -> Optional[Path]:
    ensure_dirs()
    target = THUMB_CACHE_DIR / f"{video_id}.jpg"
    if target.exists() and target.stat().st_size > 0:
        return target
    async with _FETCH_SEMAPHORE:
        if target.exists() and target.stat().st_size > 0:
            return target
        try:
            client = await _get_client()
            r = await client.get(url)
            r.raise_for_status()
            target.write_bytes(r.content)
            return target
        except Exception:
            target.unlink(missing_ok=True)
            return None
