from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..data import ytdlp_client
from ..widgets.status_bar import StatusBar
from ..widgets.video_list import VideoList


class HomeScreen(Screen):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__(name="home")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("🔥 Trending on YouTube", id="home-title")
        self.video_list = VideoList(id="home-list")
        yield self.video_list
        self.status = StatusBar()
        yield self.status
        yield Footer()

    DEFAULT_CSS = """
    HomeScreen {
        layout: vertical;
    }
    HomeScreen #home-title {
        height: 1;
        padding: 0 1;
        background: #1a1a1a;
        color: #ff0033;
        text-style: bold;
    }
    """

    def on_mount(self) -> None:
        self.video_list.focus()
        self.refresh_trending()

    def action_refresh(self) -> None:
        self.refresh_trending()

    def refresh_trending(self) -> None:
        self.status.show("Loading trending…", busy=True)
        self.run_worker(self._load_trending(), exclusive=True, group="trending")

    async def _load_trending(self) -> None:
        try:
            videos = await ytdlp_client.trending(n=25)
        except ytdlp_client.YTDLPError as e:
            self.status.show(f"Couldn't load trending: {e}")
            self.app.notify(f"Trending failed: {e}", severity="error")
            return
        except Exception as e:
            self.status.show(f"Network error: {e}")
            self.app.notify(f"Trending error: {e}", severity="error")
            return
        if not videos:
            self.status.show("No trending videos returned.")
            return
        self.video_list.set_videos(videos)
        self.status.show(f"{len(videos)} trending videos.")

    def on_video_list_selected(self, message: VideoList.Selected) -> None:
        self.app.open_detail(message.video)

    def on_video_list_play_requested(self, message: VideoList.PlayRequested) -> None:
        self.app.play_video(message.video)

    def on_video_list_favorite_toggled(self, message: VideoList.FavoriteToggled) -> None:
        self.app.toggle_favorite(message.video)

    def on_video_list_open_in_browser_requested(
        self, message: VideoList.OpenInBrowserRequested
    ) -> None:
        self.app.open_in_browser(message.video)
