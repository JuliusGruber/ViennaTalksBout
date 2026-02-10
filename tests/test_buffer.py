"""Tests for viennatalksbout.buffer — PostBatch, PostBuffer, thread safety, and edge cases."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from viennatalksbout.buffer import (
    DEFAULT_MAX_BATCH_SIZE,
    DEFAULT_WINDOW_SECONDS,
    PostBatch,
    PostBuffer,
)
from viennatalksbout.datasource import Post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post(id: str = "1", text: str = "Hello Wien!", **overrides) -> Post:
    """Create a Post with sensible defaults."""
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
# PostBatch dataclass
# ===========================================================================


class TestPostBatch:
    """Tests for the PostBatch frozen dataclass."""

    def test_create_batch(self):
        posts = (_make_post(id="1"), _make_post(id="2"))
        now = datetime.now(timezone.utc)
        batch = PostBatch(
            posts=posts,
            window_start=now,
            window_end=now,
            post_count=2,
            source="mastodon:wien.rocks",
        )
        assert batch.posts == posts
        assert batch.post_count == 2
        assert batch.source == "mastodon:wien.rocks"

    def test_batch_is_frozen(self):
        batch = PostBatch(
            posts=(),
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            post_count=0,
            source="test",
        )
        with pytest.raises(AttributeError):
            batch.post_count = 5  # type: ignore[misc]

    def test_posts_stored_as_tuple(self):
        posts = (_make_post(),)
        batch = PostBatch(
            posts=posts,
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            post_count=1,
            source="test",
        )
        assert isinstance(batch.posts, tuple)


# ===========================================================================
# PostBuffer — construction and configuration
# ===========================================================================


class TestPostBufferConfig:
    """Tests for PostBuffer constructor and configuration."""

    def test_default_window_seconds(self):
        buf = PostBuffer(source="test")
        assert buf.window_seconds == DEFAULT_WINDOW_SECONDS

    def test_custom_window_seconds(self):
        buf = PostBuffer(window_seconds=300, source="test")
        assert buf.window_seconds == 300

    def test_default_max_batch_size(self):
        buf = PostBuffer(source="test")
        assert buf.max_batch_size == DEFAULT_MAX_BATCH_SIZE

    def test_custom_max_batch_size(self):
        buf = PostBuffer(max_batch_size=50, source="test")
        assert buf.max_batch_size == 50

    def test_source_stored(self):
        buf = PostBuffer(source="mastodon:wien.rocks")
        assert buf.source == "mastodon:wien.rocks"

    def test_zero_window_raises(self):
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            PostBuffer(window_seconds=0, source="test")

    def test_negative_window_raises(self):
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            PostBuffer(window_seconds=-1, source="test")

    def test_zero_max_batch_raises(self):
        with pytest.raises(ValueError, match="max_batch_size must be positive"):
            PostBuffer(max_batch_size=0, source="test")

    def test_negative_max_batch_raises(self):
        with pytest.raises(ValueError, match="max_batch_size must be positive"):
            PostBuffer(max_batch_size=-5, source="test")


# ===========================================================================
# PostBuffer — accumulation and basic operation
# ===========================================================================


class TestPostBufferAccumulation:
    """Tests for adding posts and basic buffer behavior."""

    def test_add_post_before_start_is_ignored(self):
        callback = MagicMock()
        buf = PostBuffer(window_seconds=60, source="test", on_batch=callback)
        buf.add_post(_make_post())
        # Not started, so the post should be silently dropped
        # Force a flush to verify nothing accumulated
        buf._flush()
        callback.assert_not_called()

    def test_add_post_after_stop_is_ignored(self):
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()
        buf.stop()
        callback.reset_mock()
        buf.add_post(_make_post())
        buf._flush()
        callback.assert_not_called()

    def test_posts_accumulate_in_buffer(self):
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()

        buf.add_post(_make_post(id="1"))
        buf.add_post(_make_post(id="2"))
        buf.add_post(_make_post(id="3"))

        # Manually flush to check accumulation
        buf._flush()
        buf.stop()

        callback.assert_called_once()
        batch = callback.call_args[0][0]
        assert batch.post_count == 3
        assert len(batch.posts) == 3

    def test_start_is_idempotent(self):
        buf = PostBuffer(window_seconds=600, source="test")
        buf.start()
        buf.start()  # Should not raise or double-schedule
        buf.stop()

    def test_stop_is_idempotent(self):
        buf = PostBuffer(window_seconds=600, source="test")
        buf.start()
        buf.stop()
        buf.stop()  # Should not raise


# ===========================================================================
# PostBuffer — window expiry (timer-based flush)
# ===========================================================================


class TestPostBufferWindowExpiry:
    """Tests for timer-based window expiry and batch emission."""

    def test_timer_triggers_flush(self):
        """Buffer should flush after window_seconds elapse."""
        callback = MagicMock()
        # Use a very short window for testing
        buf = PostBuffer(window_seconds=1, source="test", on_batch=callback)
        buf.start()

        buf.add_post(_make_post(id="1"))

        # Wait for the timer to fire (1 second + margin)
        time.sleep(1.5)

        buf.stop()

        # Should have been called by the timer
        assert callback.call_count >= 1
        batch = callback.call_args_list[0][0][0]
        assert batch.post_count == 1
        assert batch.posts[0].id == "1"

    def test_multiple_windows(self):
        """Posts in different windows should produce separate batches."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=1, source="test", on_batch=callback)
        buf.start()

        buf.add_post(_make_post(id="1"))
        time.sleep(1.5)

        buf.add_post(_make_post(id="2"))
        time.sleep(1.5)

        buf.stop()

        # At least 2 batches from the 2 timer fires (plus possibly one from stop)
        assert callback.call_count >= 2


# ===========================================================================
# PostBuffer — empty window handling
# ===========================================================================


class TestPostBufferEmptyWindows:
    """Tests for behavior when no posts arrive during a window."""

    def test_empty_window_skips_callback(self):
        """No callback should be invoked for an empty window."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=1, source="test", on_batch=callback)
        buf.start()

        # Don't add any posts, wait for window to expire
        time.sleep(1.5)

        buf.stop()

        # Callback should not have been called (empty batches are skipped)
        callback.assert_not_called()

    def test_flush_with_no_posts_no_callback(self):
        """Direct _flush on empty buffer should not invoke callback."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()
        buf._flush()
        callback.assert_not_called()
        buf.stop()

    def test_stop_with_no_posts_no_callback(self):
        """Stopping a buffer with no posts should not invoke callback."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()
        buf.stop()
        callback.assert_not_called()


# ===========================================================================
# PostBuffer — max batch size (early flush on cap)
# ===========================================================================


class TestPostBufferMaxBatchSize:
    """Tests for batch size capping and early flush."""

    def test_early_flush_on_max_batch_size(self):
        """Adding posts up to max_batch_size should trigger an early flush."""
        callback = MagicMock()
        buf = PostBuffer(
            window_seconds=600,
            source="test",
            on_batch=callback,
            max_batch_size=3,
        )
        buf.start()

        buf.add_post(_make_post(id="1"))
        buf.add_post(_make_post(id="2"))
        # No flush yet
        assert callback.call_count == 0

        buf.add_post(_make_post(id="3"))
        # Should have triggered an early flush
        assert callback.call_count == 1
        batch = callback.call_args[0][0]
        assert batch.post_count == 3

        buf.stop()

    def test_posts_after_early_flush_go_to_next_batch(self):
        """Posts added after an early flush go into the next window."""
        callback = MagicMock()
        buf = PostBuffer(
            window_seconds=600,
            source="test",
            on_batch=callback,
            max_batch_size=2,
        )
        buf.start()

        buf.add_post(_make_post(id="1"))
        buf.add_post(_make_post(id="2"))
        # First batch flushed
        assert callback.call_count == 1

        buf.add_post(_make_post(id="3"))
        buf.stop()

        # Stop should flush the remaining post
        assert callback.call_count == 2
        second_batch = callback.call_args_list[1][0][0]
        assert second_batch.post_count == 1
        assert second_batch.posts[0].id == "3"


# ===========================================================================
# PostBuffer — batch metadata correctness
# ===========================================================================


class TestPostBufferMetadata:
    """Tests for batch metadata (timestamps, counts, source)."""

    def test_batch_source_matches_buffer(self):
        callback = MagicMock()
        buf = PostBuffer(
            window_seconds=600,
            source="mastodon:wien.rocks",
            on_batch=callback,
        )
        buf.start()
        buf.add_post(_make_post())
        buf._flush()
        buf.stop()

        batch = callback.call_args[0][0]
        assert batch.source == "mastodon:wien.rocks"

    def test_post_count_matches_len_posts(self):
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()

        for i in range(5):
            buf.add_post(_make_post(id=str(i)))

        buf._flush()
        buf.stop()

        batch = callback.call_args[0][0]
        assert batch.post_count == len(batch.posts) == 5

    def test_window_start_before_window_end(self):
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()
        buf.add_post(_make_post())

        # Small delay so start != end
        time.sleep(0.05)
        buf._flush()
        buf.stop()

        batch = callback.call_args[0][0]
        assert batch.window_start <= batch.window_end

    def test_window_timestamps_are_utc(self):
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()
        buf.add_post(_make_post())
        buf._flush()
        buf.stop()

        batch = callback.call_args[0][0]
        assert batch.window_start.tzinfo == timezone.utc
        assert batch.window_end.tzinfo == timezone.utc

    def test_posts_in_batch_are_the_same_objects(self):
        """The posts in the batch should be the exact Post objects that were added."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()

        p1 = _make_post(id="1")
        p2 = _make_post(id="2")
        buf.add_post(p1)
        buf.add_post(p2)
        buf._flush()
        buf.stop()

        batch = callback.call_args[0][0]
        assert batch.posts[0] is p1
        assert batch.posts[1] is p2

    def test_batch_posts_are_tuple(self):
        """PostBatch.posts should be a tuple (immutable)."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()
        buf.add_post(_make_post())
        buf._flush()
        buf.stop()

        batch = callback.call_args[0][0]
        assert isinstance(batch.posts, tuple)

    def test_consecutive_flushes_have_non_overlapping_windows(self):
        """Each batch's window_start should be >= previous batch's window_end."""
        callback = MagicMock()
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()

        buf.add_post(_make_post(id="1"))
        buf._flush()
        buf.add_post(_make_post(id="2"))
        buf._flush()
        buf.stop()

        batches = [call[0][0] for call in callback.call_args_list]
        assert len(batches) == 2
        assert batches[1].window_start >= batches[0].window_end


# ===========================================================================
# PostBuffer — thread safety
# ===========================================================================


class TestPostBufferThreadSafety:
    """Tests for concurrent access from multiple threads."""

    def test_concurrent_writes(self):
        """Multiple threads writing simultaneously should not lose posts."""
        callback = MagicMock()
        buf = PostBuffer(
            window_seconds=600,
            source="test",
            on_batch=callback,
            max_batch_size=10000,  # High cap so no early flushes
        )
        buf.start()

        num_threads = 10
        posts_per_thread = 100
        barrier = threading.Barrier(num_threads)

        def writer(thread_id: int):
            barrier.wait()  # Synchronize all threads to start together
            for i in range(posts_per_thread):
                buf.add_post(_make_post(id=f"{thread_id}-{i}"))

        threads = [
            threading.Thread(target=writer, args=(t,))
            for t in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        buf._flush()
        buf.stop()

        total_expected = num_threads * posts_per_thread
        batch = callback.call_args[0][0]
        assert batch.post_count == total_expected

    def test_concurrent_writes_during_flush(self):
        """Writing to the buffer while a flush is in progress should not lose posts."""
        batches: list[PostBatch] = []

        def record_batch(batch: PostBatch):
            batches.append(batch)

        buf = PostBuffer(
            window_seconds=600,
            source="test",
            on_batch=record_batch,
            max_batch_size=10000,
        )
        buf.start()

        # Add some posts, then flush and write concurrently
        for i in range(50):
            buf.add_post(_make_post(id=f"pre-{i}"))

        flush_done = threading.Event()
        writer_done = threading.Event()

        def flusher():
            buf._flush()
            flush_done.set()

        def writer():
            for i in range(50):
                buf.add_post(_make_post(id=f"during-{i}"))
            writer_done.set()

        t_flush = threading.Thread(target=flusher)
        t_write = threading.Thread(target=writer)
        t_flush.start()
        t_write.start()
        t_flush.join()
        t_write.join()

        # Flush any remaining
        buf._flush()
        buf.stop()

        total_posts = sum(b.post_count for b in batches)
        assert total_posts == 100  # 50 pre + 50 during

    def test_start_stop_from_different_threads(self):
        """Starting and stopping from different threads should not raise."""
        buf = PostBuffer(window_seconds=600, source="test")

        def start_buf():
            buf.start()

        def stop_buf():
            time.sleep(0.1)
            buf.stop()

        t1 = threading.Thread(target=start_buf)
        t2 = threading.Thread(target=stop_buf)
        t1.start()
        t1.join()
        t2.start()
        t2.join()


# ===========================================================================
# PostBuffer — callback error handling
# ===========================================================================


class TestPostBufferCallbackErrors:
    """Tests for graceful handling when the on_batch callback raises."""

    def test_callback_exception_does_not_crash_buffer(self):
        """If on_batch raises, the buffer should log and continue."""
        callback = MagicMock(side_effect=RuntimeError("callback failed"))
        buf = PostBuffer(window_seconds=600, source="test", on_batch=callback)
        buf.start()

        buf.add_post(_make_post())
        buf._flush()  # Should not raise

        # Buffer should still accept posts after the error
        buf.add_post(_make_post(id="2"))
        buf.stop()

    def test_no_callback_set(self):
        """Buffer with no on_batch callback should not raise on flush."""
        buf = PostBuffer(window_seconds=600, source="test", on_batch=None)
        buf.start()
        buf.add_post(_make_post())
        buf._flush()  # Should not raise
        buf.stop()
