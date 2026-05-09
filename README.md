# youtube_tui

Watch YouTube in your terminal. Textual UI, real inline thumbnails via kitty graphics protocol, `mpv` playback — including video rendered **inside the terminal** on Ghostty / kitty / WezTerm.

```
┌─ 🔥 Trending on YouTube ────────────────────────────────────────────────────┐
│                                                                             │
│  ┌─────┐  Title of the video                                                │
│  │ 🖼  │  Channel name                                                      │
│  └─────┘  ⏱ 12:34  · 1.2M views  · 2026-04-21                               │
│                                                                             │
│  ┌─────┐  Another video                                                     │
│  │ 🖼  │  …                                                                 │
│  └─────┘                                                                    │
│                                                                             │
│  Loading trending…                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **Trending feed** on launch + **YouTube search** with vim navigation
- **Real inline thumbnails** via kitty graphics protocol (Ghostty, kitty, WezTerm)
- **Three playback modes**:
  - **In-terminal** — video renders directly inside the terminal (kitty graphics; `tct` block-art fallback for terminals without kitty support)
  - **External window** — standard mpv window
  - **Audio-only**
- **Library**: history + favorites, persisted in SQLite
- Browser open, search history, custom mpv keybindings (ESC/q quit, Space pause, ←/→ seek)

## Requirements

- macOS (Linux untested but should work; Windows requires manual mpv install)
- Python **3.10+** (`textual-image` requires modern syntax)
- `mpv` on PATH
- A truecolor terminal — Ghostty / kitty / WezTerm for **real images**, anything else falls back to half-block art

## Install

```bash
brew install python@3.11 mpv
git clone https://github.com/IKrasnodymov/youtube-tui.git
cd youtube-tui
python3.11 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ytui
```

## Keybindings

| Key | Action |
|---|---|
| `q` / `ctrl+c` | Quit |
| `?` | Help |
| `/` | Search |
| `1` / `2` | Home / Library |
| `Esc` | Back |
| `j` / `k`, `gg` / `G` | List navigation |
| `Enter` | Open detail (or play in detail) |
| `p` | Play |
| `t` / `w` / `a` | In-terminal / Window / Audio-only |
| `f` | Toggle favorite |
| `o` | Open in browser |
| In mpv: `q` / `Esc` | Stop |
| In mpv: `Space`, `←/→`, `↑/↓` | Pause, seek 5s, seek 60s |

## State location

| Path | Contents |
|---|---|
| `~/Library/Application Support/youtube_tui/library.db` | History, favorites, search history (SQLite) |
| `~/Library/Caches/youtube_tui/thumbs/` | Thumbnail PNGs |
| `~/Library/Caches/youtube_tui/mpv.log` | mpv diagnostics |
| `~/Library/Logs/youtube_tui/app.log` | App log |

(Linux/Windows paths handled automatically by `platformdirs`.)

## Architecture

`youtube_tui/` Python package:
- `app.py` — Textual `App`, navigation, play flow
- `data/` — yt-dlp wrappers, thumbnail fetcher, in-memory cache
- `storage/` — SQLite layer
- `playback/` — mpv subprocess + JSON IPC client
- `screens/` — Home, Search, VideoDetail, Library, NowPlaying, Help
- `widgets/` — VideoCard, VideoList, StatusBar, image widget selector

See [CLAUDE.md](CLAUDE.md) for the architectural map and known gotchas.

## Acknowledgements

Built on:
- [Textual](https://github.com/Textualize/textual) — the TUI framework
- [textual-image](https://github.com/lnqs/textual-image) — kitty graphics widget
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — YouTube extraction
- [mpv](https://mpv.io) — playback

## License

MIT — see [LICENSE](LICENSE).
