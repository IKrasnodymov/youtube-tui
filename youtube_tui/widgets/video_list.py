from __future__ import annotations

from typing import Iterable, Optional

from textual import events
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive

from ..models import Video
from .video_card import VideoCard


class VideoList(VerticalScroll, can_focus=True):
    """Vim-navigable scrollable list of VideoCards."""

    DEFAULT_CSS = """
    VideoList {
        height: 1fr;
        background: #0f0f0f;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("g,g", "cursor_home", "Top", show=False),
        Binding("G", "cursor_end", "Bottom", show=False),
        Binding("home", "cursor_home", "Top", show=False),
        Binding("end", "cursor_end", "Bottom", show=False),
        Binding("enter", "select", "Open", show=True),
        Binding("p", "play", "Play", show=True),
        Binding("f", "favorite", "Favorite", show=True),
        Binding("o", "open_browser", "Browser", show=True),
    ]

    cursor: reactive[int] = reactive(0)

    class Selected(Message):
        def __init__(self, video: Video) -> None:
            super().__init__()
            self.video = video

    class PlayRequested(Message):
        def __init__(self, video: Video) -> None:
            super().__init__()
            self.video = video

    class FavoriteToggled(Message):
        def __init__(self, video: Video) -> None:
            super().__init__()
            self.video = video

    class OpenInBrowserRequested(Message):
        def __init__(self, video: Video) -> None:
            super().__init__()
            self.video = video

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cards: list[VideoCard] = []
        self._g_pressed = False

    @property
    def videos(self) -> list[Video]:
        return [c.video for c in self._cards]

    def set_videos(self, videos: Iterable[Video]) -> None:
        for child in list(self.children):
            child.remove()
        self._cards = [VideoCard(v) for v in videos]
        if self._cards:
            self.mount_all(self._cards)
        self.cursor = 0
        self._update_selection()
        self.scroll_home(animate=False)

    def current(self) -> Optional[Video]:
        if not self._cards:
            return None
        idx = max(0, min(self.cursor, len(self._cards) - 1))
        return self._cards[idx].video

    def watch_cursor(self, _old: int, _new: int) -> None:
        self._update_selection()

    def _update_selection(self) -> None:
        if not self._cards:
            return
        idx = max(0, min(self.cursor, len(self._cards) - 1))
        for i, card in enumerate(self._cards):
            if i == idx:
                card.add_class("-selected")
            else:
                card.remove_class("-selected")
        self.scroll_to_widget(self._cards[idx], animate=False)

    def action_cursor_down(self) -> None:
        if not self._cards:
            return
        self.cursor = min(self.cursor + 1, len(self._cards) - 1)

    def action_cursor_up(self) -> None:
        if not self._cards:
            return
        self.cursor = max(self.cursor - 1, 0)

    def action_cursor_home(self) -> None:
        self.cursor = 0

    def action_cursor_end(self) -> None:
        if self._cards:
            self.cursor = len(self._cards) - 1

    def action_select(self) -> None:
        v = self.current()
        if v is not None:
            self.post_message(self.Selected(v))

    def action_play(self) -> None:
        v = self.current()
        if v is not None:
            self.post_message(self.PlayRequested(v))

    def action_favorite(self) -> None:
        v = self.current()
        if v is not None:
            self.post_message(self.FavoriteToggled(v))

    def action_open_browser(self) -> None:
        v = self.current()
        if v is not None:
            self.post_message(self.OpenInBrowserRequested(v))

    async def on_click(self, event: events.Click) -> None:
        for i, card in enumerate(self._cards):
            if card.region.contains(event.screen_x, event.screen_y):
                self.cursor = i
                if event.button == 1:
                    self.post_message(self.Selected(card.video))
                break
