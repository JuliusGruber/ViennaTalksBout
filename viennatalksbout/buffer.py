"""Post buffer that batches incoming posts into timed windows.

Sits between a datasource (which emits individual Posts) and the topic
extractor (which processes batches). Thread-safe: the datasource may call
``add_post`` from any thread while the internal timer flushes from another.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from viennatalksbout.datasource import Post

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_WINDOW_SECONDS = 600  # 10 minutes
DEFAULT_MAX_BATCH_SIZE = 100


@dataclass(frozen=True)
class PostBatch:
    """An immutable batch of posts with window metadata.

    Attributes:
        posts: The posts collected during this window.
        window_start: When the collection window opened (UTC).
        window_end: When the collection window closed (UTC).
        post_count: Number of posts in the batch (== len(posts)).
        source: Datasource identifier (e.g. "mastodon:wien.rocks").
    """

    posts: tuple[Post, ...]
    window_start: datetime
    window_end: datetime
    post_count: int
    source: str


class PostBuffer:
    """Thread-safe buffer that accumulates posts and flushes them in timed batches.

    Usage::

        buffer = PostBuffer(
            window_seconds=600,
            source="mastodon:wien.rocks",
            on_batch=process_batch,
        )
        buffer.start()

        # From any thread:
        buffer.add_post(post)

        # Later:
        buffer.stop()  # flushes remaining posts

    Args:
        window_seconds: Duration of each collection window in seconds.
        source: Datasource identifier included in batch metadata.
        on_batch: Callback invoked with a PostBatch when a window expires.
            Not called for empty windows.
        max_batch_size: Maximum posts per batch. When the buffer reaches this
            limit, an early flush is triggered regardless of the timer.
    """

    def __init__(
        self,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        source: str = "",
        on_batch: Callable[[PostBatch], None] | None = None,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")
        if max_batch_size <= 0:
            raise ValueError(f"max_batch_size must be positive, got {max_batch_size}")

        self._window_seconds = window_seconds
        self._source = source
        self._on_batch = on_batch
        self._max_batch_size = max_batch_size

        self._lock = threading.Lock()
        self._posts: list[Post] = []
        self._window_start: datetime | None = None
        self._timer: threading.Timer | None = None
        self._running = False

    @property
    def window_seconds(self) -> int:
        """The configured window duration in seconds."""
        return self._window_seconds

    @property
    def source(self) -> str:
        """The datasource identifier included in batch metadata."""
        return self._source

    @property
    def max_batch_size(self) -> int:
        """The maximum number of posts per batch."""
        return self._max_batch_size

    def start(self) -> None:
        """Start the buffer and begin the first collection window."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._window_start = datetime.now(timezone.utc)
            self._posts = []
        self._schedule_flush()
        logger.info(
            "Post buffer started (window=%ds, max_batch=%d, source=%s)",
            self._window_seconds,
            self._max_batch_size,
            self._source,
        )

    def stop(self) -> None:
        """Stop the buffer, cancel the timer, and flush any remaining posts."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        # Flush outside the lock to avoid holding it during the callback
        self._flush()
        logger.info("Post buffer stopped (source=%s)", self._source)

    def add_post(self, post: Post) -> None:
        """Add a post to the current window's buffer.

        Thread-safe — may be called from the datasource's background thread.
        If the buffer is full (reached ``max_batch_size``), triggers an
        early flush.
        """
        should_flush = False
        with self._lock:
            if not self._running:
                return
            self._posts.append(post)
            if len(self._posts) >= self._max_batch_size:
                should_flush = True

        if should_flush:
            logger.info(
                "Batch size cap reached (%d posts), triggering early flush",
                self._max_batch_size,
            )
            self._flush()

    def _schedule_flush(self) -> None:
        """Schedule the next timer-based flush."""
        with self._lock:
            if not self._running:
                return
            self._timer = threading.Timer(self._window_seconds, self._on_timer)
            self._timer.daemon = True
            self._timer.start()

    def _on_timer(self) -> None:
        """Called by the timer thread when the window expires."""
        self._flush()
        self._schedule_flush()

    def _flush(self) -> None:
        """Flush the current buffer: build a batch and emit it via callback.

        Acquires the lock to swap out the post list, then calls the callback
        outside the lock. Skips empty batches (no callback invoked).
        """
        now = datetime.now(timezone.utc)

        with self._lock:
            posts = self._posts
            window_start = self._window_start
            self._posts = []
            self._window_start = now

        if not posts:
            logger.debug("Empty window, skipping batch emission")
            return

        batch = PostBatch(
            posts=tuple(posts),
            window_start=window_start or now,
            window_end=now,
            post_count=len(posts),
            source=self._source,
        )

        logger.info(
            "Flushing batch: %d posts, window %s -> %s",
            batch.post_count,
            batch.window_start.isoformat(),
            batch.window_end.isoformat(),
        )

        if self._on_batch is not None:
            try:
                self._on_batch(batch)
            except Exception:
                logger.exception("Error in on_batch callback")
