"""Health monitoring for the ViennaTalksBout ingestion pipeline.

Tracks pipeline health metrics including:
- Time since last received post (stale connection detection)
- LLM extraction success/failure rates
- Overall pipeline state
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_STALE_STREAM_SECONDS = 1800  # 30 minutes without a post = stale


@dataclass
class HealthStatus:
    """Snapshot of pipeline health metrics.

    Attributes:
        last_post_time: Monotonic time of last received post (None if no posts yet).
        posts_received: Total number of posts received.
        batches_processed: Total number of batches processed by the extractor.
        batches_failed: Total number of batches that failed extraction.
        topics_extracted: Total number of topics extracted across all batches.
        stream_stale: True if no post received within the stale threshold.
    """

    last_post_time: float | None
    posts_received: int
    batches_processed: int
    batches_failed: int
    topics_extracted: int
    stream_stale: bool

    @property
    def llm_success_rate(self) -> float:
        """LLM success rate as a fraction (0.0 to 1.0). Returns 1.0 if no batches."""
        total = self.batches_processed + self.batches_failed
        if total == 0:
            return 1.0
        return self.batches_processed / total


class HealthMonitor:
    """Thread-safe health monitor for the ingestion pipeline.

    Records events from the pipeline components and provides a snapshot
    of current health metrics on demand.

    Args:
        stale_stream_seconds: Seconds without a post before the stream is
            considered stale.
    """

    def __init__(
        self,
        stale_stream_seconds: float = DEFAULT_STALE_STREAM_SECONDS,
    ) -> None:
        if stale_stream_seconds <= 0:
            raise ValueError(
                f"stale_stream_seconds must be positive, got {stale_stream_seconds}"
            )

        self._stale_stream_seconds = stale_stream_seconds
        self._lock = threading.Lock()

        self._last_post_time: float | None = None
        self._posts_received: int = 0
        self._batches_processed: int = 0
        self._batches_failed: int = 0
        self._topics_extracted: int = 0

    @property
    def stale_stream_seconds(self) -> float:
        """Threshold in seconds before stream is considered stale."""
        return self._stale_stream_seconds

    def record_post(self) -> None:
        """Record that a post was received from the stream."""
        with self._lock:
            self._last_post_time = time.monotonic()
            self._posts_received += 1

    def record_batch_success(self, topic_count: int) -> None:
        """Record a successful batch extraction.

        Args:
            topic_count: Number of topics extracted from the batch.
        """
        with self._lock:
            self._batches_processed += 1
            self._topics_extracted += topic_count

    def record_batch_failure(self) -> None:
        """Record a failed batch extraction (all retries exhausted)."""
        with self._lock:
            self._batches_failed += 1

    def get_status(self) -> HealthStatus:
        """Return a snapshot of current health metrics."""
        now = time.monotonic()
        with self._lock:
            stream_stale = False
            if self._last_post_time is not None:
                elapsed = now - self._last_post_time
                stream_stale = elapsed > self._stale_stream_seconds
            elif self._posts_received == 0:
                # No posts ever received — not stale yet (just started)
                stream_stale = False

            return HealthStatus(
                last_post_time=self._last_post_time,
                posts_received=self._posts_received,
                batches_processed=self._batches_processed,
                batches_failed=self._batches_failed,
                topics_extracted=self._topics_extracted,
                stream_stale=stream_stale,
            )

    def check_and_log(self) -> HealthStatus:
        """Check health status and log a summary."""
        status = self.get_status()
        logger.info(
            "Health: posts=%d, batches_ok=%d, batches_fail=%d, "
            "topics=%d, llm_success=%.0f%%, stale=%s",
            status.posts_received,
            status.batches_processed,
            status.batches_failed,
            status.topics_extracted,
            status.llm_success_rate * 100,
            status.stream_stale,
        )
        if status.stream_stale:
            logger.warning(
                "Stream appears stale — no posts received for >%.0f seconds",
                self._stale_stream_seconds,
            )
        return status
