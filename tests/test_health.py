"""Tests for talkbout.health — health monitoring."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from talkbout.health import (
    DEFAULT_STALE_STREAM_SECONDS,
    HealthMonitor,
    HealthStatus,
)


# ===========================================================================
# HealthStatus dataclass
# ===========================================================================


class TestHealthStatus:
    """Tests for the HealthStatus dataclass."""

    def test_llm_success_rate_no_batches(self):
        status = HealthStatus(
            last_post_time=None,
            posts_received=0,
            batches_processed=0,
            batches_failed=0,
            topics_extracted=0,
            stream_stale=False,
        )
        assert status.llm_success_rate == 1.0

    def test_llm_success_rate_all_success(self):
        status = HealthStatus(
            last_post_time=1.0,
            posts_received=10,
            batches_processed=5,
            batches_failed=0,
            topics_extracted=15,
            stream_stale=False,
        )
        assert status.llm_success_rate == 1.0

    def test_llm_success_rate_all_failures(self):
        status = HealthStatus(
            last_post_time=1.0,
            posts_received=10,
            batches_processed=0,
            batches_failed=5,
            topics_extracted=0,
            stream_stale=False,
        )
        assert status.llm_success_rate == 0.0

    def test_llm_success_rate_mixed(self):
        status = HealthStatus(
            last_post_time=1.0,
            posts_received=10,
            batches_processed=3,
            batches_failed=1,
            topics_extracted=9,
            stream_stale=False,
        )
        assert status.llm_success_rate == 0.75


# ===========================================================================
# HealthMonitor construction
# ===========================================================================


class TestHealthMonitorConstruction:
    """Tests for HealthMonitor constructor."""

    def test_default_stale_threshold(self):
        monitor = HealthMonitor()
        assert monitor.stale_stream_seconds == DEFAULT_STALE_STREAM_SECONDS

    def test_custom_stale_threshold(self):
        monitor = HealthMonitor(stale_stream_seconds=60.0)
        assert monitor.stale_stream_seconds == 60.0

    def test_zero_stale_threshold_raises(self):
        with pytest.raises(ValueError, match="stale_stream_seconds must be positive"):
            HealthMonitor(stale_stream_seconds=0)

    def test_negative_stale_threshold_raises(self):
        with pytest.raises(ValueError, match="stale_stream_seconds must be positive"):
            HealthMonitor(stale_stream_seconds=-1)


# ===========================================================================
# HealthMonitor — recording events
# ===========================================================================


class TestHealthMonitorRecording:
    """Tests for recording pipeline events."""

    def test_initial_state(self):
        monitor = HealthMonitor()
        status = monitor.get_status()
        assert status.posts_received == 0
        assert status.batches_processed == 0
        assert status.batches_failed == 0
        assert status.topics_extracted == 0
        assert status.last_post_time is None
        assert status.stream_stale is False

    def test_record_post(self):
        monitor = HealthMonitor()
        monitor.record_post()
        status = monitor.get_status()
        assert status.posts_received == 1
        assert status.last_post_time is not None

    def test_record_multiple_posts(self):
        monitor = HealthMonitor()
        monitor.record_post()
        monitor.record_post()
        monitor.record_post()
        status = monitor.get_status()
        assert status.posts_received == 3

    def test_record_batch_success(self):
        monitor = HealthMonitor()
        monitor.record_batch_success(5)
        status = monitor.get_status()
        assert status.batches_processed == 1
        assert status.topics_extracted == 5

    def test_record_multiple_batch_successes(self):
        monitor = HealthMonitor()
        monitor.record_batch_success(3)
        monitor.record_batch_success(2)
        status = monitor.get_status()
        assert status.batches_processed == 2
        assert status.topics_extracted == 5

    def test_record_batch_failure(self):
        monitor = HealthMonitor()
        monitor.record_batch_failure()
        status = monitor.get_status()
        assert status.batches_failed == 1

    def test_record_mixed_events(self):
        monitor = HealthMonitor()
        monitor.record_post()
        monitor.record_post()
        monitor.record_batch_success(3)
        monitor.record_batch_failure()
        monitor.record_batch_success(2)
        status = monitor.get_status()
        assert status.posts_received == 2
        assert status.batches_processed == 2
        assert status.batches_failed == 1
        assert status.topics_extracted == 5
        assert status.llm_success_rate == pytest.approx(2 / 3)


# ===========================================================================
# HealthMonitor — stale stream detection
# ===========================================================================


class TestHealthMonitorStaleDetection:
    """Tests for stale stream detection."""

    def test_not_stale_when_no_posts_yet(self):
        """No posts ever received should not be considered stale (just started)."""
        monitor = HealthMonitor(stale_stream_seconds=1.0)
        status = monitor.get_status()
        assert status.stream_stale is False

    def test_not_stale_when_recent_post(self):
        monitor = HealthMonitor(stale_stream_seconds=10.0)
        monitor.record_post()
        status = monitor.get_status()
        assert status.stream_stale is False

    def test_stale_when_post_too_old(self):
        monitor = HealthMonitor(stale_stream_seconds=0.1)
        # Manually set last_post_time to a known value far in the past
        base = time.monotonic()
        with monitor._lock:
            monitor._last_post_time = base - 1.0
            monitor._posts_received = 1
        status = monitor.get_status()
        assert status.stream_stale is True

    def test_stale_recovers_after_new_post(self):
        monitor = HealthMonitor(stale_stream_seconds=0.1)
        # Set last_post_time far in the past so it's stale
        with monitor._lock:
            monitor._last_post_time = time.monotonic() - 1.0
            monitor._posts_received = 1
        status = monitor.get_status()
        assert status.stream_stale is True

        # Record a new post — should recover
        monitor.record_post()
        status = monitor.get_status()
        assert status.stream_stale is False


# ===========================================================================
# HealthMonitor — check_and_log
# ===========================================================================


class TestHealthMonitorCheckAndLog:
    """Tests for the check_and_log convenience method."""

    def test_check_and_log_returns_status(self):
        monitor = HealthMonitor()
        monitor.record_post()
        monitor.record_batch_success(3)
        status = monitor.check_and_log()
        assert isinstance(status, HealthStatus)
        assert status.posts_received == 1
        assert status.batches_processed == 1

    def test_check_and_log_warns_on_stale(self, caplog):
        monitor = HealthMonitor(stale_stream_seconds=0.1)
        with monitor._lock:
            monitor._last_post_time = time.monotonic() - 1.0
            monitor._posts_received = 1
        import logging
        with caplog.at_level(logging.WARNING, logger="talkbout.health"):
            status = monitor.check_and_log()
        assert status.stream_stale is True
        assert "stale" in caplog.text.lower()
