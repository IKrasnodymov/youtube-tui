CREATE TABLE IF NOT EXISTS videos (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  channel_name TEXT,
  channel_id TEXT,
  duration_s INTEGER,
  view_count INTEGER,
  published_at TEXT,
  thumbnail_url TEXT,
  is_live INTEGER NOT NULL DEFAULT 0,
  cached_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS history (
  video_id TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  watched_at INTEGER NOT NULL,
  position_s INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (video_id, watched_at)
);
CREATE INDEX IF NOT EXISTS idx_history_watched ON history(watched_at DESC);

CREATE TABLE IF NOT EXISTS favorites (
  video_id TEXT PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
  added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS search_history (
  query TEXT PRIMARY KEY,
  last_used INTEGER NOT NULL,
  hits INTEGER NOT NULL DEFAULT 1
);
