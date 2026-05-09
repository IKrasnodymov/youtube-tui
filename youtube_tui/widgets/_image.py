"""Pick the best textual-image widget class for the active terminal.

textual-image's `AutoImage` probes the terminal at import time, but Textual
has already entered alt-screen mode by then on macOS, so the probe
silently times out and the library falls back to `HalfcellImage` — much
worse than the kitty-graphics path Ghostty/kitty/WezTerm actually support.
We force `TGPImage` whenever the terminal is kitty-class, otherwise let
`AutoImage` (Image) try to do the right thing."""
from __future__ import annotations

from textual_image.widget import Image as AutoImage
from textual_image.widget import TGPImage

from ..playback.mpv_process import supports_in_terminal_video

ImageWidget = TGPImage if supports_in_terminal_video() else AutoImage
