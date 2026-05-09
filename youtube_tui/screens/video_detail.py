from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..data import ytdlp_client
from ..data.thumbnails import fetch_thumbnail
from ..models import PlaybackMode, Video
from ..playback import mpv_process
from ..widgets.status_bar import StatusBar
from ..widgets._image import ImageWidget as Image


class VideoDetailScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("enter", "play_auto", "Play"),
        Binding("a", "play_audio", "Audio"),
        Binding("t", "play_terminal", "In-terminal"),
        Binding("w", "play_external", "Window"),
        Binding("f", "favorite", "Favorite"),
        Binding("o", "browser", "Browser"),
    ]

    DEFAULT_CSS = """
    VideoDetailScreen {
        layout: vertical;
    }
    VideoDetailScreen #detail-body {
        height: 1fr;
        padding: 1 2;
    }
    VideoDetailScreen #detail-top {
        height: auto;
    }
    VideoDetailScreen #detail-thumb {
        width: 60;
        height: 17;
        margin-right: 2;
        background: #1a1a1a;
    }
    VideoDetailScreen #detail-thumb Image {
        width: 100%;
        height: 100%;
    }
    VideoDetailScreen #detail-info {
        width: 1fr;
        height: auto;
    }
    VideoDetailScreen .title {
        color: #f1f1f1;
        text-style: bold;
        height: auto;
    }
    VideoDetailScreen .channel {
        color: #ff0033;
        text-style: bold;
        height: 1;
        margin-top: 1;
    }
    VideoDetailScreen .meta {
        color: #aaaaaa;
        height: 1;
        margin-top: 1;
    }
    VideoDetailScreen .actions {
        color: #888888;
        height: auto;
        margin-top: 1;
    }
    VideoDetailScreen #detail-desc {
        margin-top: 2;
        color: #aaaaaa;
        height: auto;
    }
    """

    def __init__(self, video: Video) -> None:
        super().__init__(name="detail")
        self.video = video

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with VerticalScroll(id="detail-body"):
            with Horizontal(id="detail-top"):
                self._thumb_wrap = Container(id="detail-thumb")
                yield self._thumb_wrap
                with Vertical(id="detail-info"):
                    yield Static(self.video.title, classes="title", markup=False)
                    yield Static(f"📺 {self.video.channel_name}", classes="channel", markup=False)
                    yield Static(self._meta_text(), classes="meta")
                    yield Static(self._actions_text(), classes="actions")
            self._desc = Static(self.video.description or "(no description)", id="detail-desc", markup=False)
            yield self._desc
        self.status = StatusBar()
        yield self.status
        yield Footer()

    def _meta_text(self) -> Text:
        v = self.video
        text = Text()
        if v.is_live:
            text.append(" LIVE ", style="bold white on #ff0033")
            text.append("  ")
        else:
            text.append("⏱ " + v.duration_human, style="bold #f1f1f1")
            text.append("  ")
        if v.views_human:
            text.append("👁 " + v.views_human + "  ", style="#aaaaaa")
        if v.published_at:
            text.append("📅 " + v.published_at, style="#888888")
        return text

    def _actions_text(self) -> Text:
        text = Text()
        if mpv_process.supports_in_terminal_video():
            play_label = "Play (in-terminal)"
        else:
            play_label = "Play (window)"
        items = [
            ("[Enter]", play_label),
            ("[t]", "In-terminal"),
            ("[w]", "Window"),
            ("[a]", "Audio"),
            ("[f]", "Favorite"),
            ("[o]", "Browser"),
        ]
        for i, (k, label) in enumerate(items):
            text.append(k, style="bold #ff0033")
            text.append(f" {label}", style="#f1f1f1")
            if i < len(items) - 1:
                text.append("   ")
        return text

    def on_mount(self) -> None:
        self.run_worker(self._load_thumb(), exclusive=True, group="detail-thumb")
        self.run_worker(self._enrich_detail(), exclusive=True, group="detail-info")
        self._refresh_fav_status()

    async def _load_thumb(self) -> None:
        if not self.video.thumbnail_url:
            return
        path = await fetch_thumbnail(self.video.id, self.video.thumbnail_url)
        if path is None:
            return
        try:
            await self._thumb_wrap.mount(Image(str(path)))
        except Exception:
            pass

    async def _enrich_detail(self) -> None:
        if self.video.description:
            return
        try:
            full = await ytdlp_client.detail(self.video.id)
        except Exception:
            return
        self.video = full
        self._desc.update(full.description or "(no description)")

    def _refresh_fav_status(self) -> None:
        try:
            if self.app.library.is_favorited(self.video.id):
                self.status.show("★ Favorited")
            else:
                self.status.clear()
        except Exception:
            pass

    # ---- bindings ---------------------------------------------------------

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_play_auto(self) -> None:
        # None mode = auto: in-terminal for Ghostty/kitty, window otherwise.
        self.app.play_video(self.video, None)

    def action_play_external(self) -> None:
        self.app.play_video(self.video, PlaybackMode.EXTERNAL)

    def action_play_audio(self) -> None:
        self.app.play_video(self.video, PlaybackMode.AUDIO_ONLY)

    def action_play_terminal(self) -> None:
        self.app.play_video(self.video, PlaybackMode.IN_TERMINAL)

    def action_favorite(self) -> None:
        self.app.toggle_favorite(self.video)
        self._refresh_fav_status()

    def action_browser(self) -> None:
        self.app.open_in_browser(self.video)
