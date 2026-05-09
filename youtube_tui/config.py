from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir, user_data_dir, user_log_dir

APP_NAME = "youtube_tui"

DATA_DIR = Path(user_data_dir(APP_NAME))
CACHE_DIR = Path(user_cache_dir(APP_NAME))
LOG_DIR = Path(user_log_dir(APP_NAME))

DB_PATH = DATA_DIR / "library.db"
THUMB_CACHE_DIR = CACHE_DIR / "thumbs"


def ensure_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, LOG_DIR, THUMB_CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
