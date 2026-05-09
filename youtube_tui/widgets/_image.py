"""Pick the best textual-image widget class for the active terminal.

textual-image's `AutoImage` probes the terminal at import time, but Textual
has already entered alt-screen mode by then on macOS, so the probe
silently times out and the library falls back to `HalfcellImage` — much
worse than the kitty-graphics path Ghostty/kitty/WezTerm actually support.
We force `TGPImage` whenever TERM looks kitty-class, otherwise let
`AutoImage` (Image) try to do the right thing."""
from __future__ import annotations

import os

from textual_image.widget import Image as AutoImage
from textual_image.widget import TGPImage

_TERM = os.environ.get("TERM", "").lower()
_TERM_PROGRAM = os.environ.get("TERM_PROGRAM", "").lower()

_KITTY_CLASS = ("kitty", "ghostty", "wezterm")


def _kitty_capable() -> bool:
    return any(n in _TERM for n in _KITTY_CLASS) or any(
        n in _TERM_PROGRAM for n in _KITTY_CLASS
    )


# Final class chosen at import time, before Textual takes over the terminal.
ImageWidget = TGPImage if _kitty_capable() else AutoImage
