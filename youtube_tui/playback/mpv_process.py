from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..config import CACHE_DIR, ensure_dirs
from ..models import PlaybackMode


_KITTY_TERMS = ("kitty", "ghostty", "wezterm")


class MpvNotFoundError(RuntimeError):
    pass


def is_mpv_available() -> bool:
    return shutil.which("mpv") is not None


def supports_in_terminal_video() -> bool:
    """True iff TERM or TERM_PROGRAM names a terminal that speaks the kitty
    graphics protocol. Ghostty under tmux sets TERM=screen, so checking
    both env vars matters."""
    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    return any(n in term or n in term_program for n in _KITTY_TERMS)


@dataclass
class MpvProcess:
    proc: asyncio.subprocess.Process
    ipc_path: Path

    def cleanup_socket(self) -> None:
        try:
            self.ipc_path.unlink(missing_ok=True)
        except Exception:
            pass

    async def wait(self) -> int:
        try:
            return await self.proc.wait()
        finally:
            self.cleanup_socket()

    def is_running(self) -> bool:
        return self.proc.returncode is None

    async def terminate(self) -> None:
        if self.proc.returncode is not None:
            self.cleanup_socket()
            return
        try:
            self.proc.terminate()
        except ProcessLookupError:
            self.cleanup_socket()
            return
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            try:
                self.proc.kill()
            except ProcessLookupError:
                self.cleanup_socket()
                return
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
        finally:
            self.cleanup_socket()


def _build_args(stream_url: str, mode: PlaybackMode, ipc_path: Path) -> list[str]:
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
        args.append(
            "--ytdl-format=bv*[height<=720][vcodec^=avc1]+ba/bv*[height<=720]+ba/b[height<=720]/best[height<=720]/best"
        )
    else:
        args.append(
            "--ytdl-format=bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080]+ba/b[height<=1080]/best[height<=1080]/best"
        )

    args.append(f"--input-ipc-server={ipc_path}")
    args.append("--really-quiet")
    args.append("--idle=no")
    if mode is PlaybackMode.EXTERNAL:
        args.append("--force-window=immediate")

    args.append(stream_url)
    return [a for a in args if a is not None]


async def launch(stream_url: str, mode: PlaybackMode) -> MpvProcess:
    if not is_mpv_available():
        raise MpvNotFoundError("mpv executable not found on PATH")

    ensure_dirs()
    ipc_dir = CACHE_DIR / "mpv_ipc"
    ipc_dir.mkdir(parents=True, exist_ok=True)
    ipc_path = ipc_dir / f"{uuid4().hex[:12]}.sock"

    log_path = CACHE_DIR / "mpv.log"
    log_fh = open(log_path, "ab")
    try:
        args = _build_args(stream_url, mode, ipc_path)
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=log_fh,
        )
    except Exception:
        try:
            ipc_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    finally:
        log_fh.close()

    return MpvProcess(proc=proc, ipc_path=ipc_path)
