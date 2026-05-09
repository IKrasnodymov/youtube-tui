from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from ..widgets.status_bar import StatusBar
from ..widgets.video_list import VideoList


class LibraryScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    DEFAULT_CSS = """
    LibraryScreen {
        layout: vertical;
    }
    LibraryScreen #library-title {
        height: 1;
        padding: 0 1;
        background: #1a1a1a;
        color: #ff0033;
        text-style: bold;
    }
    LibraryScreen TabbedContent {
        height: 1fr;
    }
    LibraryScreen Tabs {
        background: #1a1a1a;
    }
    LibraryScreen Tab {
        color: #aaaaaa;
    }
    LibraryScreen Tab.-active {
        color: #ff0033;
        text-style: bold;
    }
    LibraryScreen .empty {
        height: 1fr;
        content-align: center middle;
        color: #888888;
    }
    """

    def __init__(self) -> None:
        super().__init__(name="library")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("📚 Your Library", id="library-title")
        with TabbedContent(initial="tab-history"):
            with TabPane("History", id="tab-history"):
                self.history_list = VideoList(id="history-list")
                yield self.history_list
            with TabPane("Favorites", id="tab-favorites"):
                self.fav_list = VideoList(id="fav-list")
                yield self.fav_list
        self.status = StatusBar()
        yield self.status
        yield Footer()

    def on_mount(self) -> None:
        self._reload()
        self.history_list.focus()

    def _reload(self) -> None:
        try:
            history = self.app.library.recent_history(limit=100)
            favs = self.app.library.list_favorites(limit=200)
        except Exception as e:
            self.app.notify(f"Couldn't load library: {e}", severity="error")
            return
        self.history_list.set_videos(history)
        self.fav_list.set_videos(favs)
        self.status.show(f"{len(history)} watched · {len(favs)} favorited")

    def action_back(self) -> None:
        self.app.pop_screen()

    # Forward list events from whichever tab is active.
    def on_video_list_selected(self, message: VideoList.Selected) -> None:
        self.app.open_detail(message.video)

    def on_video_list_play_requested(self, message: VideoList.PlayRequested) -> None:
        self.app.play_video(message.video)

    def on_video_list_favorite_toggled(self, message: VideoList.FavoriteToggled) -> None:
        self.app.toggle_favorite(message.video)
        self._reload()

    def on_video_list_open_in_browser_requested(
        self, message: VideoList.OpenInBrowserRequested
    ) -> None:
        self.app.open_in_browser(message.video)
