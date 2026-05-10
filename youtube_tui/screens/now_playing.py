from __future__ import annotations

import asyncio
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import ProgressBar, Static

from ..models import PlaybackMode, Video
from ..playback import mpv_process
from ..playback.ipc import MpvIPC, MpvIPCError


def _fmt_time(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "—:—"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{ss:02d}"
    return f"{m}:{ss:02d}"


class NowPlayingScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("space", "toggle_pause", "Pause/Play"),
        Binding("escape", "stop", "Stop"),
        Binding("q", "stop", "Stop"),
        Binding("left", "seek_back", "-10s"),
        Binding("right", "seek_forward", "+10s"),
        Binding("shift+left", "seek_back_long", "-60s"),
        Binding("shift+right", "seek_forward_long", "+60s"),
    ]

    DEFAULT_CSS = """
    NowPlayingScreen {
        align: center middle;
    }
    NowPlayingScreen #np-box {
        width: 90%;
        max-width: 78;
        height: auto;
        padding: 1 2;
        background: #1a1a1a;
        border: double #ff0033;
    }
    NowPlayingScreen #np-title {
        color: #f1f1f1;
        text-style: bold;
        height: 2;
    }
    NowPlayingScreen #np-channel {
        color: #ff0033;
        height: 1;
        margin-bottom: 1;
    }
    NowPlayingScreen #np-status {
        color: #aaaaaa;
        height: 1;
    }
    NowPlayingScreen ProgressBar {
        margin-top: 1;
        margin-bottom: 1;
    }
    NowPlayingScreen #np-bar Bar {
        color: #ff0033;
    }
    NowPlayingScreen #np-help {
        color: #888888;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(self, video: Video, proc: mpv_process.MpvProcess, mode: PlaybackMode) -> None:
        super().__init__(name="now-playing")
        self.video = video
        self.proc = proc
        self.mode = mode
        self.ipc: Optional[MpvIPC] = None
        self._duration: Optional[float] = None
        self._position: float = 0.0
        self._paused: bool = False
        self._closed: bool = False
        self._started: bool = False

    def compose(self) -> ComposeResult:
        with Vertical(id="np-box"):
            self._title = Static(f"▶ {self.video.title}", id="np-title", markup=False)
            yield self._title
            self._channel = Static(self.video.channel_name, id="np-channel", markup=False)
            yield self._channel
            self._status = Static(self._build_status(), id="np-status")
            yield self._status
            self._bar = ProgressBar(total=100, show_eta=False, show_percentage=False, id="np-bar")
            yield self._bar
            yield Static(self._help_text(), id="np-help")

    def _help_text(self) -> Text:
        t = Text()
        items = [
            ("Space", "Pause"),
            ("← →", "Seek 10s"),
            ("⇧ ← →", "Seek 60s"),
            ("q / Esc", "Stop"),
        ]
        for i, (k, label) in enumerate(items):
            t.append(k, style="bold #ff0033")
            t.append(f" {label}", style="#aaaaaa")
            if i < len(items) - 1:
                t.append("   ")
        return t

    def _build_status(self) -> Text:
        t = Text()
        if self._paused:
            t.append("⏸  PAUSED  ", style="bold #ff0033")
        else:
            t.append("▶  PLAYING ", style="bold #00cc66")
        t.append(_fmt_time(self._position), style="#f1f1f1")
        t.append(" / ", style="#666666")
        t.append(_fmt_time(self._duration), style="#aaaaaa")
        if self.mode is PlaybackMode.AUDIO_ONLY:
            t.append("   [audio-only]", style="#888888")
        elif self.mode is PlaybackMode.IN_TERMINAL:
            t.append("   [in-terminal]", style="#888888")
        return t

    async def on_mount(self) -> None:
        self.ipc = MpvIPC(self.proc.ipc_path)
        try:
            await self._connect_ipc()
        except Exception as e:
            self.app.notify(f"Couldn't connect to mpv: {e}", severity="error")
            try:
                await self.proc.terminate()
            except Exception:
                pass
            await self._finish(record=False)
            return

        self.run_worker(self._observe(), exclusive=True, group="np-observe")
        self.run_worker(self._wait_exit(), exclusive=True, group="np-wait")

    async def _connect_ipc(self) -> None:
        assert self.ipc is not None
        last_error: Exception | None = None
        for _ in range(50):
            if self.proc.proc.returncode is not None:
                raise MpvIPCError(
                    f"mpv exited with code {self.proc.proc.returncode}; see mpv.log"
                )
            try:
                await self.ipc.connect(retries=1, delay_s=0)
                return
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.1)
        raise MpvIPCError(f"could not connect to mpv ipc: {last_error!r}")

    async def _observe(self) -> None:
        assert self.ipc is not None
        try:
            async for name, data in self.ipc.observe("time-pos", "duration", "pause"):
                if name == "time-pos" and isinstance(data, (int, float)):
                    self._position = float(data)
                elif name == "duration" and isinstance(data, (int, float)):
                    self._duration = float(data)
                elif name == "pause":
                    self._paused = bool(data)
                if self._position > 0 or self._duration is not None:
                    self._started = True
                self._refresh_ui()
        except (MpvIPCError, asyncio.CancelledError):
            return
        except Exception:
            return

    def _refresh_ui(self) -> None:
        self._status.update(self._build_status())
        if self._duration and self._duration > 0:
            pct = max(0.0, min(100.0, (self._position / self._duration) * 100.0))
            self._bar.update(total=100, progress=pct)
        else:
            self._bar.update(total=100, progress=0)

    async def _wait_exit(self) -> None:
        rc: int | None = None
        try:
            rc = await self.proc.wait()
        except Exception:
            pass
        if rc not in (None, 0):
            self.app.notify(
                f"mpv exited with code {rc}. See mpv.log", severity="warning", timeout=6
            )
        await self._finish(record=(rc == 0 or self._started))

    async def _finish(self, *, record: bool) -> None:
        if self._closed:
            return
        self._closed = True
        if record:
            try:
                self.app.record_watch(self.video, position_s=int(self._position))
                self.app.notify("Saved to history.", timeout=2)
            except Exception:
                pass
        if self.ipc is not None:
            try:
                await self.ipc.close()
            except Exception:
                pass
        self.proc.cleanup_socket()
        self.dismiss()

    # ---- key actions ------------------------------------------------------

    def action_toggle_pause(self) -> None:
        if self.ipc is None:
            return
        self.run_worker(self._toggle(), group="np-cmd")

    async def _toggle(self) -> None:
        try:
            await self.ipc.toggle_pause()  # type: ignore[union-attr]
        except Exception:
            pass

    def action_seek_back(self) -> None:
        self._seek(-10)

    def action_seek_forward(self) -> None:
        self._seek(10)

    def action_seek_back_long(self) -> None:
        self._seek(-60)

    def action_seek_forward_long(self) -> None:
        self._seek(60)

    def _seek(self, delta: float) -> None:
        if self.ipc is None:
            return
        self.run_worker(self._do_seek(delta), group="np-cmd")

    async def _do_seek(self, delta: float) -> None:
        try:
            await self.ipc.seek(delta, mode="relative")  # type: ignore[union-attr]
        except Exception:
            pass

    def action_stop(self) -> None:
        self.run_worker(self._stop(), group="np-cmd")

    async def _stop(self) -> None:
        if self.ipc is not None:
            try:
                await self.ipc.quit()
            except Exception:
                pass
        try:
            await self.proc.terminate()
        except Exception:
            pass
        await self._finish(record=True)
