"""SQLite persistence layer for ViennaTalksBout posts.

Stores posts durably so they survive restarts. Unprocessed posts are
automatically recovered on startup and fed back into the buffer.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from viennatalksbout.datasource import Post

logger = logging.getLogger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS posts (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    language    TEXT,
    source      TEXT NOT NULL,
    received_at TEXT NOT NULL,
    processed   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_posts_unprocessed
    ON posts (processed) WHERE processed = 0;
CREATE INDEX IF NOT EXISTS idx_posts_created_at
    ON posts (created_at);
"""


def post_to_row(post: Post) -> tuple:
    """Convert a Post to a tuple suitable for INSERT."""
    return (
        post.id,
        post.text,
        post.created_at.isoformat(),
        post.language,
        post.source,
        datetime.now(timezone.utc).isoformat(),
    )


def row_to_post(row: sqlite3.Row) -> Post:
    """Convert a database row back to a Post."""
    return Post(
        id=row["id"],
        text=row["text"],
        created_at=datetime.fromisoformat(row["created_at"]),
        language=row["language"],
        source=row["source"],
    )


class PostDatabase:
    """SQLite-backed post persistence.

    Args:
        db_path: Path to the SQLite database file. Parent directories
            are created automatically.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        logger.info("PostDatabase opened: %s", self._db_path)

    def save_post(self, post: Post) -> bool:
        """Persist a post. Returns True if the post was new (inserted)."""
        row = post_to_row(post)
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO posts "
                "(id, text, created_at, language, source, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def get_unprocessed_posts(self) -> list[Post]:
        """Return all unprocessed posts, ordered by created_at."""
        rows = self._conn.execute(
            "SELECT * FROM posts WHERE processed = 0 ORDER BY created_at"
        ).fetchall()
        return [row_to_post(r) for r in rows]

    def mark_batch_processed(self, post_ids: list[str]) -> None:
        """Mark the given post IDs as processed."""
        if not post_ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE posts SET processed = 1 WHERE id = ?",
                [(pid,) for pid in post_ids],
            )
            self._conn.commit()

    def cleanup_old_posts(self, retention_hours: int = 48) -> int:
        """Delete processed posts older than *retention_hours*.

        Returns the number of deleted rows.
        """
        cutoff = datetime.now(timezone.utc).isoformat()
        # Build the cutoff by subtracting hours — ISO 8601 strings compare
        # lexicographically so we can compute the threshold directly.
        from datetime import timedelta

        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=retention_hours)
        ).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM posts WHERE processed = 1 AND received_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            deleted = cursor.rowcount
        if deleted:
            logger.info("Cleaned up %d old processed posts", deleted)
        return deleted

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.info("PostDatabase closed")
