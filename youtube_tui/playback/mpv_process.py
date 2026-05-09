from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..config import CACHE_DIR, ensure_dirs
from ..models import PlaybackMode


class MpvNotFoundError(RuntimeError):
    pass


def is_mpv_available() -> bool:
    return shutil.which("mpv") is not None


def supports_in_terminal_video() -> bool:
    term = os.environ.get("TERM", "").lower()
    return any(n in term for n in ("kitty", "ghostty", "wezterm"))


@dataclass
class MpvProcess:
    proc: asyncio.subprocess.Process
    ipc_path: Path
    started_at: float

    async def wait(self) -> int:
        return await self.proc.wait()

    def is_running(self) -> bool:
        return self.proc.returncode is None

    async def terminate(self) -> None:
        if self.proc.returncode is not None:
            return
        try:
            self.proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            try:
                self.proc.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass


def _build_args(
    stream_url: str,
    mode: PlaybackMode,
    ipc_path: Path,
    *,
    force_window: bool = False,
) -> list[str]:
    args: list[Optional[str]] = ["mpv"]

    # Format selection — mpv runs yt-dlp itself so it can refresh URLs and
    # carry the right headers (passing pre-resolved URLs causes 403s).
    if mode is PlaybackMode.AUDIO_ONLY:
        args.append("--no-video")
        args.append("--ytdl-format=bestaudio/best")
    elif mode is PlaybackMode.IN_TERMINAL:
        # --vo-kitty-use-shm is Linux-only — passing it on macOS breaks kitty VO.
        args.append("--vo=kitty")
        args.append("--hwdec=no")
        args.append("--ytdl-format=best[height<=720]/best")
    else:
        args.append("--ytdl-format=best[height<=1080]/best")

    args.append(f"--input-ipc-server={ipc_path}")
    args.append("--really-quiet")
    args.append("--idle=no")

    want_force_window = (
        mode is PlaybackMode.EXTERNAL or (force_window and mode is not PlaybackMode.IN_TERMINAL)
    )
    args.append("--force-window=immediate" if want_force_window else None)

    args.append(stream_url)
    return [a for a in args if a is not None]


async def launch(
    stream_url: str,
    mode: PlaybackMode,
    *,
    force_window: bool = False,
) -> MpvProcess:
    if not is_mpv_available():
        raise MpvNotFoundError("mpv executable not found on PATH")

    ensure_dirs()
    ipc_dir = CACHE_DIR / "mpv_ipc"
    ipc_dir.mkdir(parents=True, exist_ok=True)
    ipc_path = ipc_dir / f"{uuid4().hex[:12]}.sock"

    log_path = CACHE_DIR / "mpv.log"
    log_fh = open(log_path, "ab")
    try:
        args = _build_args(stream_url, mode, ipc_path, force_window=force_window)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=log_fh,
        )
    finally:
        log_fh.close()

    return MpvProcess(proc=proc, ipc_path=ipc_path, started_at=time.time())
