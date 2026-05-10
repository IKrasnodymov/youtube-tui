from __future__ import annotations

from typing import Iterable, Optional

from textual import events
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

from ..models import Video
from .video_card import VideoCard


class VideoList(VerticalScroll, can_focus=True):
    """Vim-navigable scrollable list of VideoCards."""

    CARD_HEIGHT = 11
    COMPACT_CARD_HEIGHT = 6
    THUMB_PRELOAD_RADIUS = 3
    OVERSCAN = 6
    MAX_WINDOW_CARDS = 48
    COMPACT_WIDTH = 72

    DEFAULT_CSS = """
    VideoList {
        height: 1fr;
        background: #0f0f0f;
    }
    VideoList .virtual-spacer {
        width: 100%;
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
        self._videos: list[Video] = []
        self._cards: dict[int, VideoCard] = {}
        self._top_spacer = Static(classes="virtual-spacer")
        self._bottom_spacer = Static(classes="virtual-spacer")
        self._g_pressed = False
        self._compact = False
        self._window_start = 0
        self._window_end = 0
        self._refreshing_window = False

    @property
    def videos(self) -> list[Video]:
        return list(self._videos)

    def set_videos(self, videos: Iterable[Video]) -> None:
        for child in list(self.children):
            child.remove()
        self._videos = list(videos)
        self._cards = {}
        self._window_start = 0
        self._window_end = 0
        self._top_spacer = Static(classes="virtual-spacer")
        self._bottom_spacer = Static(classes="virtual-spacer")
        self._apply_compact_mode()
        self.cursor = 0
        self.scroll_home(animate=False)
        self._render_window(force=True)
        self._load_visible_thumbnails()

    def current(self) -> Optional[Video]:
        if not self._videos:
            return None
        idx = max(0, min(self.cursor, len(self._videos) - 1))
        return self._videos[idx]

    def watch_cursor(self, old: int, new: int) -> None:
        if not self._videos:
            return
        n = len(self._videos)
        old_idx = max(0, min(old, n - 1))
        new_idx = max(0, min(new, n - 1))
        old_card = self._cards.get(old_idx)
        if old_idx != new_idx and old_card is not None:
            old_card.remove_class("-selected")
        self._scroll_cursor_into_view()
        self._render_window()
        new_card = self._cards.get(new_idx)
        if new_card is not None:
            new_card.add_class("-selected")
        self._load_visible_thumbnails()

    def _load_visible_thumbnails(self) -> None:
        if self._compact or not self._videos:
            return
        start, end = self._visible_range(extra=self.THUMB_PRELOAD_RADIUS)
        for idx in range(start, end):
            card = self._cards.get(idx)
            if card is None:
                continue
            card.ensure_thumbnail()

    def _apply_compact_mode(self) -> None:
        compact = self.size.width > 0 and self.size.width < self.COMPACT_WIDTH
        if compact == self._compact:
            return
        self._compact = compact
        for card in self._cards.values():
            card.set_compact(compact)
        self._render_window(force=True)
        self._load_visible_thumbnails()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_compact_mode()
        self._render_window()

    def watch_scroll_y(self, old: float, new: float) -> None:
        if self._refreshing_window:
            return
        self._render_window()
        self._load_visible_thumbnails()

    def _card_height(self) -> int:
        return self.COMPACT_CARD_HEIGHT if self._compact else self.CARD_HEIGHT

    def _visible_range(self, *, extra: int = 0) -> tuple[int, int]:
        if not self._videos:
            return (0, 0)
        card_height = self._card_height()
        visible_count = max(1, int(self.size.height // card_height) + 1)
        visible_count = min(visible_count, self.MAX_WINDOW_CARDS)
        start = max(0, int(self.scroll_y // card_height) - extra)
        window_size = min(self.MAX_WINDOW_CARDS, visible_count + (extra * 2))
        end = min(len(self._videos), start + window_size)
        return start, end

    def _window_range(self) -> tuple[int, int]:
        start, end = self._visible_range(extra=self.OVERSCAN)
        if self._videos:
            if self.cursor < start:
                start = max(0, self.cursor)
                end = min(len(self._videos), start + self.MAX_WINDOW_CARDS)
            elif self.cursor >= end:
                end = min(len(self._videos), self.cursor + 1)
                start = max(0, end - self.MAX_WINDOW_CARDS)
        return start, end

    def _set_spacer_heights(self, start: int, end: int) -> None:
        card_height = self._card_height()
        self._top_spacer.styles.height = start * card_height
        self._bottom_spacer.styles.height = max(0, len(self._videos) - end) * card_height

    def _make_card(self, index: int) -> VideoCard:
        card = VideoCard(self._videos[index])
        card.set_compact(self._compact)
        if index == self.cursor:
            card.add_class("-selected")
        return card

    def _render_window(self, *, force: bool = False) -> None:
        if self._refreshing_window:
            return
        start, end = self._window_range()
        if not force and start == self._window_start and end == self._window_end:
            self._update_selection_classes()
            self._set_spacer_heights(start, end)
            return

        self._refreshing_window = True
        try:
            for child in list(self.children):
                child.remove()
            self._cards = {i: self._make_card(i) for i in range(start, end)}
            self._set_spacer_heights(start, end)
            children = [self._top_spacer, *self._cards.values(), self._bottom_spacer]
            self.mount_all(children)
            self._window_start = start
            self._window_end = end
        finally:
            self._refreshing_window = False

    def _update_selection_classes(self) -> None:
        for idx, card in self._cards.items():
            card.set_class(idx == self.cursor, "-selected")

    def _scroll_cursor_into_view(self) -> None:
        card_height = self._card_height()
        top = self.cursor * card_height
        bottom = top + card_height
        viewport_top = self.scroll_y
        viewport_bottom = viewport_top + max(1, self.size.height)
        if top < viewport_top:
            self.scroll_to(y=top, animate=False)
        elif bottom > viewport_bottom:
            self.scroll_to(y=max(0, bottom - self.size.height), animate=False)

    def action_cursor_down(self) -> None:
        if not self._videos:
            return
        self.cursor = min(self.cursor + 1, len(self._videos) - 1)

    def action_cursor_up(self) -> None:
        if not self._videos:
            return
        self.cursor = max(self.cursor - 1, 0)

    def action_cursor_home(self) -> None:
        self.cursor = 0

    def action_cursor_end(self) -> None:
        if self._videos:
            self.cursor = len(self._videos) - 1

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

    def on_click(self, event: events.Click) -> None:
        for i, card in self._cards.items():
            if card.region.contains(event.screen_x, event.screen_y):
                self.cursor = i
                if event.button == 1:
                    self.post_message(self.Selected(self._videos[i]))
                break
