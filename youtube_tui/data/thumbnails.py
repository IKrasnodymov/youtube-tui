from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Tuple

import httpx
from PIL import Image
from rich.text import Text

from ..config import THUMB_CACHE_DIR, ensure_dirs

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# Cap concurrent thumbnail downloads — without this, mounting 25 cards
# fires 25 simultaneous TLS handshakes against i.ytimg.com.
_FETCH_SEMAPHORE = asyncio.Semaphore(8)
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None
_HTTP_LOCK = asyncio.Lock()


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

# Quadrant glyphs indexed by 4-bit mask: bit 0=TL, 1=TR, 2=BL, 3=BR.
# Each glyph carries fg color for "1" pixels and bg color for "0" pixels.
_QUADRANTS: tuple[str, ...] = (
    " ",   # 0000
    "▘",  # 0001 TL
    "▝",  # 0010 TR
    "▀",  # 0011 TL+TR
    "▖",  # 0100 BL
    "▌",  # 0101 TL+BL
    "▞",  # 0110 TR+BL
    "▛",  # 0111 TL+TR+BL
    "▗",  # 1000 BR
    "▚",  # 1001 TL+BR
    "▐",  # 1010 TR+BR
    "▜",  # 1011 TL+TR+BR
    "▄",  # 1100 BL+BR
    "▙",  # 1101 TL+BL+BR
    "▟",  # 1110 TR+BL+BR
    "█",  # 1111
)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
    )
}


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
            if target.exists():
                target.unlink(missing_ok=True)
            return None


def _luma(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _split_2x2(quad: list[tuple[int, int, int]]) -> tuple[int, tuple[int, int, int], tuple[int, int, int]]:
    """Pick the brightest and darkest pixels as fg/bg, threshold by average luma."""
    lumas = [_luma(p) for p in quad]
    lo = min(lumas)
    hi = max(lumas)
    threshold = (lo + hi) / 2 if hi > lo else 128.0
    mask = 0
    fg_pixels: list[tuple[int, int, int]] = []
    bg_pixels: list[tuple[int, int, int]] = []
    for i, (p, l) in enumerate(zip(quad, lumas)):
        if l >= threshold and hi > lo:
            mask |= 1 << i
            fg_pixels.append(p)
        else:
            bg_pixels.append(p)
    if not fg_pixels:
        fg_pixels = quad
    if not bg_pixels:
        bg_pixels = quad
    fg = tuple(int(sum(c) / len(fg_pixels)) for c in zip(*fg_pixels))  # type: ignore[assignment]
    bg = tuple(int(sum(c) / len(bg_pixels)) for c in zip(*bg_pixels))  # type: ignore[assignment]
    return mask, fg, bg  # type: ignore[return-value]


def render_quadrants(image_path: Path, cols: int, rows: int) -> Text:
    """Render an image as Unicode quadrant blocks (▘▝▀▖▌▞▛▗▚▐▜▄▙▟█).
    Each cell encodes a 2×2 pixel block — 4 pixels of detail per character,
    twice the resolution of half-blocks (and 4× per row)."""
    img = Image.open(image_path).convert("RGB")
    target_w = max(2, cols * 2)
    target_h = max(2, rows * 2)
    img = img.resize((target_w, target_h), Image.LANCZOS)
    px = img.load()
    text = Text(no_wrap=True, overflow="ellipsis")
    for cy in range(rows):
        py = cy * 2
        for cx in range(cols):
            qx = cx * 2
            quad = [
                px[qx, py],         # TL
                px[qx + 1, py],     # TR
                px[qx, py + 1],     # BL
                px[qx + 1, py + 1], # BR
            ]
            mask, fg, bg = _split_2x2(quad)
            glyph = _QUADRANTS[mask]
            text.append(
                glyph,
                style=f"rgb({fg[0]},{fg[1]},{fg[2]}) on rgb({bg[0]},{bg[1]},{bg[2]})",
            )
        if cy < rows - 1:
            text.append("\n")
    return text


# Back-compat alias.
render_half_blocks = render_quadrants


def render_placeholder(cols: int, rows: int, color: str = "#222222") -> Text:
    text = Text(no_wrap=True)
    for r in range(rows):
        text.append(" " * cols, style=f"on {color}")
        if r < rows - 1:
            text.append("\n")
    return text


async def thumbnail_text(
    video_id: str,
    thumbnail_url: Optional[str],
    size: Tuple[int, int],
) -> Text:
    cols, rows = size
    if not thumbnail_url:
        return render_placeholder(cols, rows)
    path = await fetch_thumbnail(video_id, thumbnail_url)
    if path is None:
        return render_placeholder(cols, rows, color="#3a1f1f")
    return await asyncio.to_thread(render_quadrants, path, cols, rows)
