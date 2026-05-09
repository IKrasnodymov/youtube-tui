# youtube_tui

Watch YouTube in the terminal. Textual-based TUI with real inline thumbnails (kitty graphics) and `mpv` playback (in-terminal video on Ghostty/kitty/WezTerm, external window or audio-only elsewhere).

## Quickstart

```bash
# macOS prerequisites
brew install python@3.11 mpv

# project setup
python3.11 -m venv .venv
.venv/bin/pip install -e .[dev]

# run
.venv/bin/ytui
```

## Architecture

```
youtube_tui/
├── __main__.py              # `python -m youtube_tui` entry → main()
├── app.py                   # YouTubeTUI(App) — global bindings, screen registry, play_video flow, file logger
├── config.py                # platformdirs paths (data/cache/log dirs)
├── models.py                # Video, Channel, SearchResult, PlaybackMode dataclasses
├── tui.tcss                 # global Textual CSS (red accent, dark)
├── data/
│   ├── ytdlp_client.py      # async wrappers around yt_dlp.YoutubeDL (search/trending/detail/stream_url)
│   ├── thumbnails.py        # shared httpx client + semaphore for thumbnail fetch
│   └── cache.py             # in-memory TTL+LRU cache for search/trending/detail JSON
├── storage/
│   ├── schema.sql           # CREATE TABLE IF NOT EXISTS — videos, history, favorites, search_history
│   └── db.py                # Library — sqlite3 wrapper (autocommit, WAL, FK on)
├── playback/
│   ├── mpv_process.py       # MpvProcess + _build_args + launch + supports_in_terminal_video
│   └── ipc.py               # JSON IPC over AF_UNIX — pause/seek/quit/observe_property
├── screens/
│   ├── home.py              # trending feed
│   ├── search.py            # input + results
│   ├── video_detail.py      # large thumbnail + play actions
│   ├── library.py           # TabbedContent: History / Favorites
│   ├── now_playing.py       # IPC overlay for external/audio playback
│   └── help.py              # ModalScreen cheatsheet
└── widgets/
    ├── _image.py            # Picks TGPImage in Ghostty/kitty/WezTerm, AutoImage elsewhere — at IMPORT time, before Textual takes the screen
    ├── video_card.py        # thumbnail + title + meta
    ├── video_list.py        # vim-nav (j/k/gg/G) ListView
    └── status_bar.py        # footer status / busy spinner
```

## Keybindings

| Where | Key | Action |
|---|---|---|
| Global | `q` / `ctrl+c` | Quit |
| Global | `?` | Help |
| Global | `/` | Search |
| Global | `1` | Home (trending) |
| Global | `2` | Library |
| Global | `Esc` | Back |
| Video list | `j`/`k`, `gg`/`G` | Navigate |
| Video list | `Enter` | Open detail |
| Video list | `p` / `f` / `o` | Play / Favorite / Browser |
| Video detail | `Enter` | Auto-play (in-terminal) |
| Video detail | `t` / `w` / `a` | In-terminal / Window / Audio-only |
| Video detail | `f` / `o` | Favorite / Browser |
| In mpv (inline) | `q` / `Esc` | Stop (custom input.conf overrides default ESC=fullscreen) |
| In mpv (inline) | `Space`, `←/→`, `↑/↓` | Pause, seek 5s, seek 60s |

## Gotchas (DO read before editing)

1. **`--vo-kitty-use-shm` is Linux-only.** Passing it on macOS breaks mpv's kitty VO silently (audio plays, no video). Both `mpv_process.py` and `app.py:_play_inline` were bitten by this — don't add it back.
2. **mpv playback URL must be the YouTube watch URL, not a pre-resolved stream URL.** Pre-resolving via `yt_dlp.YoutubeDL` strips the headers/cookies that the streaming CDN requires, leading to `HTTP 403 Forbidden`. We pass `https://youtube.com/watch?v=…` directly so mpv runs yt-dlp itself with proper context.
3. **`textual-image.AutoImage` probes the terminal for kitty/sixel support at module-import time.** If the import happens *after* Textual enters alt-screen, the probe times out and the library silently falls back to `HalfcellImage` (visibly low quality). `widgets/_image.py` works around this by selecting `TGPImage` whenever TERM looks kitty-class. Don't move the import into a `def`.
4. **YouTube retired `/feed/trending`.** `data/ytdlp_client.py:trending` falls back through a chain: `results?search_query=trending+today&sp=…` first, then `ytsearchdate50:trending today`. If the first one ever breaks, just reorder.
5. **mpv inline playback must use `App.suspend()` from the main coroutine, not `asyncio.to_thread`.** The Textual driver is bound to the main thread; suspending from a worker thread silently no-ops and mpv ends up drawing over a still-active TUI.
6. **`--no-terminal-osd` is not a real mpv option.** Earlier versions of `_play_inline` had it and mpv exited rc=1 on argument parsing before video opened. Use `--no-osc --osd-level=0` for the same effect.
7. **mpv default ESC = fullscreen-toggle.** We ship a custom `input.conf` (written to `~/Library/Caches/youtube_tui/ytui-mpv-input.conf` on first play) that rebinds ESC and q to `quit`.
8. **In-terminal video resolution capped at 480p.** Every frame is base64-encoded over the terminal pipe; 720p+ tanks framerate even on Apple Silicon. `--profile=sw-fast`, `--cache=yes`, `--demuxer-readahead-secs=20` were dialed for that environment.
9. **Python 3.10 minimum.** `textual-image` uses `match` syntax. We started on 3.9 (system Python) and had to upgrade. Don't downgrade `requires-python`.
10. **Screen IDs collide on `push_screen`.** `action_go_home/search/library` use `_pop_to(cls)` to walk back to an existing instance instead of pushing a duplicate. Don't pass `id=` to Screen subclasses' `__init__`.

## Where state lives

| Path | What |
|---|---|
| `~/Library/Application Support/youtube_tui/library.db` | SQLite — history, favorites, search history, video cache |
| `~/Library/Caches/youtube_tui/thumbs/<id>.jpg` | thumbnail PNGs (immutable per video) |
| `~/Library/Caches/youtube_tui/mpv.log` | mpv stderr + log-file output |
| `~/Library/Caches/youtube_tui/mpv_ipc/<uuid>.sock` | per-launch IPC socket for external/audio mode |
| `~/Library/Caches/youtube_tui/ytui-mpv-input.conf` | mpv keybinding overrides (ESC/q = quit) |
| `~/Library/Logs/youtube_tui/app.log` | TUI app logger — boot, suspend state, mpv args, exit codes |

Paths come from `platformdirs.user_*_dir("youtube_tui")` — Linux/Windows are handled automatically via `youtube_tui/config.py`.

## Testing

```bash
.venv/bin/pytest -q                   # full suite (23 tests)
YTUI_NO_NET=1 .venv/bin/pytest -q     # offline only — skips the live yt-dlp search smoke test
```

Tests live in `tests/`. The yt-dlp client and storage layer have unit coverage; the playback module has argument-builder tests but no live mpv test (it requires a TTY).

## Coding conventions

- `from __future__ import annotations` at top of every module.
- No comments unless the **why** is non-obvious (workaround, hidden invariant, surprising behavior). Identifier names carry the **what**.
- Errors at module boundaries → `app.notify(..., severity="error")` toasts. Don't crash the UI.
- yt-dlp / sqlite3 / Pillow calls run via `asyncio.to_thread` (or `@work(thread=True)`). Never block the Textual event loop.
- All UI mutation from worker threads must use `app.call_from_thread` or `@work(exclusive=True)`.

## Common dev tasks

- **Add a new screen**: subclass `Screen`, drop in `youtube_tui/screens/`, push from a binding action. Don't pass `id=`.
- **Add a yt-dlp call**: wrap in `asyncio.to_thread` inside `data/ytdlp_client.py`, cache via `_cache.put(key, value, ttl_s)`.
- **Tweak mpv args**: edit `_play_inline` in `app.py` (in-terminal) or `playback/mpv_process.py:_build_args` (external/audio). Test with `mpv ... &; sleep 4; kill -INT $!` and check `mpv.log`.
- **Change the theme**: `youtube_tui/tui.tcss` (root vars) or per-widget `DEFAULT_CSS`.
