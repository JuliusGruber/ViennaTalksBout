"""Tests for viennatalksbout.persistence — SQLite post storage."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from viennatalksbout.datasource import Post
from viennatalksbout.persistence import PostDatabase, post_to_row, row_to_post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_post(id: str = "1", text: str = "Hello Wien!", **overrides) -> Post:
    defaults = {
        "id": id,
        "text": text,
        "created_at": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "language": "de",
        "source": "mastodon:wien.rocks",
    }
    defaults.update(overrides)
    return Post(**defaults)


# ===========================================================================
# PostDatabase — init
# ===========================================================================


class TestPostDatabaseInit:
    def test_creates_db_file(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = PostDatabase(db_path)
        assert db_path.exists()
        db.close()

    def test_creates_parent_directories(self, tmp_path: Path):
        db_path = tmp_path / "sub" / "dir" / "test.db"
        db = PostDatabase(db_path)
        assert db_path.exists()
        db.close()

    def test_idempotent_schema(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db1 = PostDatabase(db_path)
        db1.close()
        # Re-open same DB — should not fail
        db2 = PostDatabase(db_path)
        db2.close()

    def test_posts_table_exists(self, tmp_path: Path):
        db_path = tmp_path / "test.db"
        db = PostDatabase(db_path)
        rows = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='posts'"
        ).fetchall()
        assert len(rows) == 1
        db.close()


# ===========================================================================
# save_post
# ===========================================================================


class TestSavePost:
    def test_insert_returns_true(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        assert db.save_post(_make_post()) is True
        db.close()

    def test_duplicate_returns_false(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="dup"))
        assert db.save_post(_make_post(id="dup")) is False
        db.close()

    def test_fields_roundtrip(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        post = _make_post(
            id="rt",
            text="Roundtrip test",
            created_at=datetime(2025, 7, 1, 8, 30, 0, tzinfo=timezone.utc),
            language="en",
            source="mastodon:test.social",
        )
        db.save_post(post)
        posts = db.get_unprocessed_posts()
        assert len(posts) == 1
        p = posts[0]
        assert p.id == "rt"
        assert p.text == "Roundtrip test"
        assert p.created_at == datetime(2025, 7, 1, 8, 30, 0, tzinfo=timezone.utc)
        assert p.language == "en"
        assert p.source == "mastodon:test.social"
        db.close()

    def test_null_language(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        post = _make_post(language=None)
        db.save_post(post)
        posts = db.get_unprocessed_posts()
        assert posts[0].language is None
        db.close()


# ===========================================================================
# get_unprocessed_posts
# ===========================================================================


class TestGetUnprocessed:
    def test_empty_db(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        assert db.get_unprocessed_posts() == []
        db.close()

    def test_filters_processed(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="a"))
        db.save_post(_make_post(id="b"))
        db.mark_batch_processed(["a"])
        posts = db.get_unprocessed_posts()
        assert len(posts) == 1
        assert posts[0].id == "b"
        db.close()

    def test_chronological_order(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(
            _make_post(
                id="late",
                created_at=datetime(2025, 6, 15, 14, 0, 0, tzinfo=timezone.utc),
            )
        )
        db.save_post(
            _make_post(
                id="early",
                created_at=datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            )
        )
        posts = db.get_unprocessed_posts()
        assert [p.id for p in posts] == ["early", "late"]
        db.close()


# ===========================================================================
# mark_batch_processed
# ===========================================================================


class TestMarkProcessed:
    def test_marks_correctly(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="x"))
        db.save_post(_make_post(id="y"))
        db.mark_batch_processed(["x"])
        unprocessed = db.get_unprocessed_posts()
        assert [p.id for p in unprocessed] == ["y"]
        db.close()

    def test_idempotent(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="x"))
        db.mark_batch_processed(["x"])
        db.mark_batch_processed(["x"])  # should not raise
        assert db.get_unprocessed_posts() == []
        db.close()

    def test_nonexistent_ids_ignored(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.mark_batch_processed(["nonexistent"])  # should not raise
        db.close()

    def test_empty_list(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.mark_batch_processed([])  # should not raise
        db.close()


# ===========================================================================
# cleanup_old_posts
# ===========================================================================


class TestCleanup:
    def test_removes_old_processed(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="old"))
        # Manually backdate received_at
        old_time = (
            datetime.now(timezone.utc) - timedelta(hours=100)
        ).isoformat()
        db._conn.execute(
            "UPDATE posts SET received_at = ?, processed = 1 WHERE id = ?",
            (old_time, "old"),
        )
        db._conn.commit()
        deleted = db.cleanup_old_posts(retention_hours=48)
        assert deleted == 1
        assert db.get_unprocessed_posts() == []
        db.close()

    def test_keeps_recent_processed(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="recent"))
        db.mark_batch_processed(["recent"])
        deleted = db.cleanup_old_posts(retention_hours=48)
        assert deleted == 0
        db.close()

    def test_keeps_unprocessed(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        db.save_post(_make_post(id="pending"))
        # Manually backdate
        old_time = (
            datetime.now(timezone.utc) - timedelta(hours=100)
        ).isoformat()
        db._conn.execute(
            "UPDATE posts SET received_at = ? WHERE id = ?",
            (old_time, "pending"),
        )
        db._conn.commit()
        deleted = db.cleanup_old_posts(retention_hours=48)
        assert deleted == 0
        posts = db.get_unprocessed_posts()
        assert len(posts) == 1
        db.close()


# ===========================================================================
# Thread safety
# ===========================================================================


class TestThreadSafety:
    def test_concurrent_saves(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        errors: list[Exception] = []

        def save_range(start: int, count: int):
            try:
                for i in range(start, start + count):
                    db.save_post(_make_post(id=str(i)))
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=save_range, args=(0, 50)),
            threading.Thread(target=save_range, args=(50, 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        posts = db.get_unprocessed_posts()
        assert len(posts) == 100
        db.close()

    def test_concurrent_save_and_read(self, tmp_path: Path):
        db = PostDatabase(tmp_path / "test.db")
        errors: list[Exception] = []

        def save_posts():
            try:
                for i in range(50):
                    db.save_post(_make_post(id=str(i)))
            except Exception as e:
                errors.append(e)

        def read_posts():
            try:
                for _ in range(50):
                    db.get_unprocessed_posts()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=save_posts)
        t2 = threading.Thread(target=read_posts)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == []
        db.close()
