from __future__ import annotations

import sys


_HELP = """youtube_tui

Usage:
  ytui
  youtube-tui

Keyboard shortcuts are shown in the TUI footer. Install mpv for playback.
"""


def main() -> int:
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(_HELP, end="")
        return 0

    from .app import YouTubeTUI

    YouTubeTUI().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
