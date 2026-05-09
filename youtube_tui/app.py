from __future__ import annotations

import asyncio
import logging
import webbrowser
from pathlib import Path
from typing import Optional

from textual.app import App
from textual.binding import Binding

from .config import LOG_DIR, ensure_dirs
from .data import ytdlp_client
from .models import PlaybackMode, Video
from .playback import mpv_process
from .storage.db import Library


def _setup_logger() -> logging.Logger:
    ensure_dirs()
    log = logging.getLogger("youtube_tui")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_DIR / "app.log", mode="a")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    log.addHandler(handler)
    return log


_log = _setup_logger()


class YouTubeTUI(App[None]):
    CSS_PATH = Path(__file__).parent / "tui.tcss"
    TITLE = "youtube_tui"
    SUB_TITLE = "watch YouTube in your terminal"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("question_mark", "help", "Help", show=True),
        Binding("slash", "go_search", "Search", show=True),
        Binding("1", "go_home", "Home", show=True),
        Binding("2", "go_library", "Library", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.library: Library = None  # type: ignore[assignment]
        self._inline_proc: Optional[asyncio.subprocess.Process] = None
        self._mpv_processes: list[mpv_process.MpvProcess] = []

    def on_mount(self) -> None:
        ensure_dirs()
        self.library = Library()
        from .widgets._image import ImageWidget

        _log.info(
            "app mounted; mpv=%s ghostty=%s can_suspend=%s image_widget=%s",
            mpv_process.is_mpv_available(),
            mpv_process.supports_in_terminal_video(),
            getattr(self._driver, "can_suspend", None) if self._driver else None,
            ImageWidget.__name__,
        )
        if not mpv_process.is_mpv_available():
            self.notify(
                "mpv is not installed — playback disabled.\nRun: brew install mpv",
                severity="warning",
                timeout=10,
            )
        from .screens.home import HomeScreen

        self.push_screen(HomeScreen())

    def on_unmount(self) -> None:
        # Kill any mpv we still own — terminals don't always SIGHUP children
        # cleanly when closed, so we explicitly clean up.
        if self._inline_proc is not None and self._inline_proc.returncode is None:
            try:
                self._inline_proc.kill()
            except Exception:
                pass
        for mp in list(self._mpv_processes):
            if mp.is_running():
                try:
                    mp.proc.kill()
                except Exception:
                    pass
        try:
            if self.library is not None:
                self.library.close()
        except Exception:
            pass

    # ---- navigation actions -----------------------------------------------

    def _pop_to(self, cls: type) -> bool:
        """Pop screens until an instance of `cls` is on top. Returns True if found."""
        idx = None
        for i, scr in enumerate(self.screen_stack):
            if isinstance(scr, cls):
                idx = i
        if idx is None:
            return False
        while len(self.screen_stack) - 1 > idx:
            self.pop_screen()
        return True

    def action_go_home(self) -> None:
        from .screens.home import HomeScreen

        if isinstance(self.screen, HomeScreen):
            return
        if not self._pop_to(HomeScreen):
            self.push_screen(HomeScreen())

    def action_go_search(self) -> None:
        from .screens.search import SearchScreen

        if isinstance(self.screen, SearchScreen):
            return
        self.push_screen(SearchScreen())

    def action_go_library(self) -> None:
        from .screens.library import LibraryScreen

        if isinstance(self.screen, LibraryScreen):
            return
        if not self._pop_to(LibraryScreen):
            self.push_screen(LibraryScreen())

    def action_help(self) -> None:
        from .screens.help import HelpScreen

        self.push_screen(HelpScreen())

    # ---- public handlers used by screens ---------------------------------

    def open_detail(self, video: Video) -> None:
        from .screens.video_detail import VideoDetailScreen

        self.push_screen(VideoDetailScreen(video))

    def play_video(
        self, video: Video, mode: Optional[PlaybackMode] = None
    ) -> None:
        if not mpv_process.is_mpv_available():
            self.notify(
                "mpv not installed. Run: brew install mpv",
                severity="error",
            )
            return
        # Auto-pick = always in-terminal. mpv VO is selected per-terminal
        # inside _play_inline (kitty graphics → tct block-art fallback).
        if mode is None:
            mode = PlaybackMode.IN_TERMINAL
        self.run_worker(
            self._play_async(video, mode),
            exclusive=True,
            group="player",
        )

    async def _play_async(self, video: Video, mode: PlaybackMode) -> None:
        # Pass the YouTube watch URL directly to mpv — mpv invokes yt-dlp itself
        # so it gets fresh URLs with proper headers (avoids 403s from stripped pre-resolved URLs).
        if mode is PlaybackMode.IN_TERMINAL:
            await self._play_inline(video)
            return

        try:
            self.notify(f"Loading: {video.title}", timeout=3)
            proc = await mpv_process.launch(video.url, mode)
        except mpv_process.MpvNotFoundError:
            self.notify("mpv not found.", severity="error")
            return
        except Exception as e:
            self.notify(f"mpv failed: {e}", severity="error")
            return

        self._mpv_processes.append(proc)
        from .screens.now_playing import NowPlayingScreen

        self.push_screen(NowPlayingScreen(video, proc, mode))

    async def _play_inline(self, video: Video) -> None:
        """In-terminal playback: suspend the TUI so mpv owns the terminal,
        wait until mpv exits, then resume."""
        import sys

        from .config import CACHE_DIR

        _log.info("inline play start: %s", video.id)
        # Pick the right VO for the current terminal:
        # - kitty graphics protocol → real images (Ghostty, kitty, WezTerm)
        # - tct (true-color blocks) → fallback for everything else
        # Note: --vo-kitty-use-shm is Linux-only, do not pass it on macOS.
        if mpv_process.supports_in_terminal_video():
            vo_args = ["--vo=kitty"]
            vo_label = "kitty graphics"
        else:
            vo_args = ["--vo=tct"]
            vo_label = "block art (no kitty graphics in this terminal)"
        self.notify(
            f"Playing — {vo_label}. Press q or ESC to exit.",
            timeout=5,
        )

        # Custom input bindings — mpv's defaults bind ESC to fullscreen-toggle,
        # but here we want it to quit. Also bind some friendly seek keys.
        input_conf = CACHE_DIR / "ytui-mpv-input.conf"
        input_conf.write_text(
            "\n".join(
                [
                    "ESC quit",
                    "q quit",
                    "SPACE cycle pause",
                    "LEFT seek -5",
                    "RIGHT seek 5",
                    "UP seek 60",
                    "DOWN seek -60",
                ]
            )
            + "\n"
        )

        log_path = CACHE_DIR / "mpv.log"
        # --really-quiet kills status / warnings printed to the terminal so
        # they don't smear the video. Detailed diagnostics go to log file.
        # Lower res + cache + sw-fast keeps kitty-graphics smooth — every
        # frame is base64-encoded over the terminal pipe, so 480p is the
        # sweet spot on macOS.
        args = [
            "mpv",
            *vo_args,
            "--hwdec=no",
            "--profile=sw-fast",
            "--ytdl-format=best[height<=480]/best",
            "--cache=yes",
            "--cache-secs=20",
            "--demuxer-readahead-secs=20",
            f"--input-conf={input_conf}",
            f"--log-file={log_path}",
            "--msg-level=all=error",
            "--really-quiet",
            "--no-osc",
            "--osd-level=0",
            video.url,
        ]
        _log.info("mpv args: %s", args)

        driver = getattr(self, "_driver", None)
        can_suspend = bool(driver and getattr(driver, "can_suspend", False))
        _log.info("driver=%r can_suspend=%s", driver, can_suspend)
        if not can_suspend:
            self.notify(
                "Terminal driver does not support suspend; opening in window.",
                severity="warning",
            )
            await self._play_async(video, PlaybackMode.EXTERNAL)
            return

        rc: int = -1
        # Sink mpv's stderr to the log file so its diagnostics don't paint
        # over the video frame in the terminal.
        stderr_fh = open(log_path, "ab")
        try:
            with self.suspend():
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    stdin=None,
                    stdout=None,
                    stderr=stderr_fh,
                )
                self._inline_proc = proc
                rc = await proc.wait()
                self._inline_proc = None
                # Reset terminal before Textual resumes, so leftover kitty
                # graphics ids and any stray escape state are cleared.
                try:
                    sys.stdout.write("\x1b[?25h\x1b[2J\x1b[H")
                    sys.stdout.flush()
                except Exception:
                    pass
            _log.info("mpv inline exit rc=%s", rc)
        except FileNotFoundError:
            _log.exception("mpv not found")
            self.notify("mpv not found on PATH.", severity="error")
            return
        except Exception as e:
            _log.exception("inline playback failed")
            self.notify(f"Playback failed: {e!r}", severity="error")
            return
        finally:
            try:
                stderr_fh.close()
            except Exception:
                pass
            try:
                self.refresh(layout=True)
            except Exception:
                pass

        if rc == 0:
            try:
                self.library.record_watch(video, position_s=0)
            except Exception:
                _log.exception("record_watch failed")
            self.notify("Saved to history.", timeout=2)
        else:
            self.notify(
                f"mpv exited with code {rc}. Logs: ~/Library/Caches/youtube_tui/mpv.log",
                severity="warning",
                timeout=8,
            )

    def toggle_favorite(self, video: Video) -> None:
        try:
            now = self.library.toggle_favorite(video)
            if now:
                self.notify(f"★ Favorited: {video.title}", timeout=2)
            else:
                self.notify(f"☆ Unfavorited: {video.title}", timeout=2)
        except Exception as e:
            self.notify(f"Favorite failed: {e}", severity="error")

    def open_in_browser(self, video: Video) -> None:
        try:
            webbrowser.open(video.url)
            self.notify("Opened in browser.")
        except Exception as e:
            self.notify(f"Couldn't open browser: {e}", severity="error")

    def record_watch(self, video: Video, position_s: int = 0) -> None:
        try:
            self.library.record_watch(video, position_s=position_s)
        except Exception:
            pass
