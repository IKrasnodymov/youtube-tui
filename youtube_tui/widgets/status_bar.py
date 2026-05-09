from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static


class StatusBar(Horizontal):
    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #1a1a1a;
        color: #aaaaaa;
        dock: bottom;
    }
    StatusBar > #status-left {
        width: 1fr;
        padding-left: 1;
    }
    StatusBar > #status-right {
        width: auto;
        padding-right: 1;
    }
    StatusBar.busy > #status-left {
        color: #ff0033;
    }
    """

    message: reactive[str] = reactive("")
    busy: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        self._left = Static("", id="status-left")
        self._right = Static("youtube_tui", id="status-right")
        yield self._left
        yield self._right

    def watch_message(self, _old: str, new: str) -> None:
        self._left.update(new)

    def watch_busy(self, _old: bool, new: bool) -> None:
        if new:
            self.add_class("busy")
        else:
            self.remove_class("busy")

    def show(self, text: str, *, busy: bool = False) -> None:
        self.message = text
        self.busy = busy

    def clear(self) -> None:
        self.message = ""
        self.busy = False
