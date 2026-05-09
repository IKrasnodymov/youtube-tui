from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

from youtube_tui import config
from youtube_tui.models import Video

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000

_VIDEO_COLUMNS = (
    "id, title, channel_name, channel_id, duration_s, view_count, "
    "published_at, thumbnail_url, is_live"
)


def _row_to_video(row: sqlite3.Row) -> Video:
    return Video(
        id=row["id"],
        title=row["title"],
        channel_name=row["channel_name"] or "",
        channel_id=row["channel_id"],
        duration_s=row["duration_s"],
        view_count=row["view_count"],
        published_at=row["published_at"],
        thumbnail_url=row["thumbnail_url"],
        is_live=bool(row["is_live"]),
    )


class Library:
    def __init__(self, path: Optional[Path] = None) -> None:
        config.ensure_dirs()
        self._path = Path(path) if path is not None else config.DB_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            self._conn.executescript(f.read())

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Library":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def upsert_video(self, video: Video) -> None:
        now = _now_ms()
        self._conn.execute(
            """
            INSERT INTO videos (
                id, title, channel_name, channel_id, duration_s, view_count,
                published_at, thumbnail_url, is_live, cached_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                channel_name=excluded.channel_name,
                channel_id=excluded.channel_id,
                duration_s=excluded.duration_s,
                view_count=excluded.view_count,
                published_at=excluded.published_at,
                thumbnail_url=excluded.thumbnail_url,
                is_live=excluded.is_live,
                cached_at=excluded.cached_at
            """,
            (
                video.id,
                video.title,
                video.channel_name,
                video.channel_id,
                video.duration_s,
                video.view_count,
                video.published_at,
                video.thumbnail_url,
                1 if video.is_live else 0,
                now,
            ),
        )

    def record_watch(self, video: Video, position_s: int = 0) -> None:
        self.upsert_video(video)
        self._conn.execute(
            "INSERT INTO history(video_id, watched_at, position_s) VALUES (?, ?, ?)",
            (video.id, _now_ms(), int(position_s)),
        )

    def toggle_favorite(self, video: Video) -> bool:
        self.upsert_video(video)
        try:
            self._conn.execute("BEGIN")
            cur = self._conn.execute(
                "SELECT 1 FROM favorites WHERE video_id = ?", (video.id,)
            )
            exists = cur.fetchone() is not None
            if exists:
                self._conn.execute(
                    "DELETE FROM favorites WHERE video_id = ?", (video.id,)
                )
                new_state = False
            else:
                self._conn.execute(
                    "INSERT INTO favorites(video_id, added_at) VALUES (?, ?)",
                    (video.id, _now_ms()),
                )
                new_state = True
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return new_state

    def record_search(self, query: str) -> None:
        now = _now_ms()
        self._conn.execute(
            """
            INSERT INTO search_history(query, last_used, hits)
            VALUES (?, ?, 1)
            ON CONFLICT(query) DO UPDATE SET
                last_used=excluded.last_used,
                hits=search_history.hits + 1
            """,
            (query, now),
        )

    def is_favorited(self, video_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM favorites WHERE video_id = ?", (video_id,)
        )
        return cur.fetchone() is not None

    def recent_history(self, limit: int = 50) -> list[Video]:
        cur = self._conn.execute(
            f"""
            SELECT v.{_VIDEO_COLUMNS}, MAX(h.watched_at) AS last_watched
            FROM history h
            JOIN videos v ON v.id = h.video_id
            GROUP BY h.video_id
            ORDER BY last_watched DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [_row_to_video(r) for r in cur.fetchall()]

    def list_favorites(self, limit: int = 200) -> list[Video]:
        cur = self._conn.execute(
            f"""
            SELECT v.{_VIDEO_COLUMNS}
            FROM favorites f
            JOIN videos v ON v.id = f.video_id
            ORDER BY f.added_at DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        return [_row_to_video(r) for r in cur.fetchall()]

    def recent_searches(self, limit: int = 20) -> list[str]:
        cur = self._conn.execute(
            "SELECT query FROM search_history ORDER BY last_used DESC LIMIT ?",
            (int(limit),),
        )
        return [r["query"] for r in cur.fetchall()]
