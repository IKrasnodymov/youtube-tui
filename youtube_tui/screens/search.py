from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from ..data import ytdlp_client
from ..widgets.status_bar import StatusBar
from ..widgets.video_list import VideoList


class SearchScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("ctrl+l", "focus_input", "Focus input"),
    ]

    def __init__(self) -> None:
        super().__init__(name="search")
        self._last_query: str = ""

    DEFAULT_CSS = """
    SearchScreen {
        layout: vertical;
    }
    SearchScreen #search-bar {
        height: 3;
        padding: 0 1;
        background: #1a1a1a;
    }
    SearchScreen #search-bar > Static {
        width: auto;
        padding: 1 1 0 0;
        color: #ff0033;
        text-style: bold;
    }
    SearchScreen #search-input {
        width: 1fr;
        background: #0f0f0f;
        border: solid #303030;
    }
    SearchScreen #search-input:focus {
        border: solid #ff0033;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="search-bar"):
            yield Static("🔍")
            self.input = Input(
                placeholder="Search YouTube…  (Enter to search, Esc to go back)",
                id="search-input",
            )
            yield self.input
        self.video_list = VideoList(id="search-list")
        yield self.video_list
        self.status = StatusBar()
        yield self.status
        yield Footer()

    def on_mount(self) -> None:
        self.input.focus()

    def action_focus_input(self) -> None:
        self.input.focus()

    def action_back(self) -> None:
        if self.app.screen_stack and len(self.app.screen_stack) > 1:
            self.app.pop_screen()

    @on(Input.Submitted, "#search-input")
    def on_query_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self._last_query = query
        self.run_worker(
            self._do_search(query), exclusive=True, group="search"
        )

    async def _do_search(self, query: str) -> None:
        self.status.show(f"Searching: {query}…", busy=True)
        try:
            videos = await ytdlp_client.search(query, n=25)
        except ytdlp_client.YTDLPError as e:
            self.status.show(f"Search failed: {e}")
            self.app.notify(f"Search failed: {e}", severity="error")
            return
        except Exception as e:
            self.status.show(f"Network error: {e}")
            self.app.notify(f"Search error: {e}", severity="error")
            return
        if not videos:
            self.status.show(f"No results for '{query}'.")
            self.video_list.set_videos([])
            return
        self.video_list.set_videos(videos)
        self.video_list.focus()
        self.status.show(f"{len(videos)} results for '{query}'")
        try:
            self.app.library.record_search(query)
        except Exception:
            pass

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
