from __future__ import annotations


def main() -> int:
    from .app import YouTubeTUI

    YouTubeTUI().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
