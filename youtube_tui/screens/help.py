from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


_ROWS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Global",
        [
            ("q", "Quit"),
            ("?", "This help"),
            ("/", "Search"),
            ("1", "Home (trending)"),
            ("2", "Library (history + favorites)"),
            ("Esc", "Back"),
        ],
    ),
    (
        "Video list",
        [
            ("j / ↓", "Down"),
            ("k / ↑", "Up"),
            ("g g", "Top"),
            ("G", "Bottom"),
            ("Enter", "Open detail"),
            ("p", "Play"),
            ("f", "Toggle favorite"),
            ("o", "Open in browser"),
        ],
    ),
    (
        "Video detail",
        [
            ("Enter", "Play (external mpv window)"),
            ("a", "Audio-only"),
            ("t", "In-terminal (kitty graphics)"),
            ("f", "Toggle favorite"),
            ("o", "Open in browser"),
            ("Esc", "Back"),
        ],
    ),
    (
        "Now playing",
        [
            ("Space", "Toggle pause"),
            ("← / →", "Seek -/+ 10s"),
            ("Shift+← / →", "Seek -/+ 60s"),
            ("q / Esc", "Stop and close"),
        ],
    ),
]


def _build_help_text() -> Text:
    t = Text()
    for group, rows in _ROWS:
        t.append(group + "\n", style="bold #ff0033")
        for key, desc in rows:
            t.append("  ")
            t.append(f"{key:<14}", style="bold #f1f1f1")
            t.append(desc, style="#aaaaaa")
            t.append("\n")
        t.append("\n")
    return t


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_help", "Close"),
        Binding("question_mark", "dismiss_help", "Close"),
        Binding("q", "dismiss_help", "Close"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen #help-box {
        width: 70;
        height: auto;
        padding: 1 2;
        background: #1a1a1a;
        border: double #ff0033;
    }
    HelpScreen #help-title {
        color: #ff0033;
        text-style: bold;
        height: 1;
        margin-bottom: 1;
    }
    HelpScreen #help-body {
        height: auto;
    }
    HelpScreen #help-foot {
        color: #888888;
        height: 1;
        margin-top: 1;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static("youtube_tui — keybindings", id="help-title")
            yield Static(_build_help_text(), id="help-body")
            yield Static("Press Esc to close", id="help-foot")

    def action_dismiss_help(self) -> None:
        self.dismiss()
