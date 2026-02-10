"""Tests for talkbout.ingest — ingestion pipeline orchestrator.

Integration tests with mocked external dependencies (Mastodon stream,
Claude API). Tests cover:
- Full pipeline wiring (stream → buffer → extractor → store)
- Configuration loading
- Health monitoring integration
- Graceful shutdown behavior
"""

from __future__ import annotations

import logging
import os
import signal
import textwrap
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from talkbout.buffer import PostBatch, PostBuffer
from talkbout.datasource import Post
from talkbout.extractor import ExtractedTopic, TopicExtractor
from talkbout.health import HealthMonitor
from talkbout.ingest import (
    DEFAULT_BUFFER_MAX_BATCH_SIZE,
    DEFAULT_BUFFER_WINDOW_SECONDS,
    DEFAULT_HEALTH_LOG_INTERVAL,
    DEFAULT_RETENTION_HOURS,
    DEFAULT_SNAPSHOT_DIR,
    DEFAULT_STALE_STREAM_SECONDS,
    IngestionPipeline,
    build_pipeline,
    load_pipeline_config,
    setup_logging,
)
from talkbout.mastodon.stream import MastodonDatasource
from talkbout.store import TopicStore


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


def _make_batch(posts=None, **overrides) -> PostBatch:
    """Create a PostBatch with sensible defaults."""
    if posts is None:
        posts = (_make_post(),)
    if not isinstance(posts, tuple):
        posts = tuple(posts)
    now = datetime.now(timezone.utc)
    defaults = {
        "posts": posts,
        "window_start": now,
        "window_end": now,
        "post_count": len(posts),
        "source": "mastodon:wien.rocks",
    }
    defaults.update(overrides)
    return PostBatch(**defaults)


# ===========================================================================
# setup_logging
# ===========================================================================


class TestSetupLogging:
    """Tests for structured logging setup."""

    def test_default_log_level_is_info(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TALKBOUT_LOG_LEVEL", raising=False)
        root = logging.getLogger()
        old_level = root.level
        try:
            setup_logging()
            assert root.level == logging.INFO
        finally:
            root.setLevel(old_level)

    def test_custom_log_level(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TALKBOUT_LOG_LEVEL", "DEBUG")
        root = logging.getLogger()
        old_level = root.level
        try:
            setup_logging()
            assert root.level == logging.DEBUG
        finally:
            root.setLevel(old_level)

    def test_invalid_log_level_falls_back_to_info(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("TALKBOUT_LOG_LEVEL", "INVALID")
        root = logging.getLogger()
        old_level = root.level
        try:
            setup_logging()
            assert root.level == logging.INFO
        finally:
            root.setLevel(old_level)


# ===========================================================================
# load_pipeline_config
# ===========================================================================


class TestLoadPipelineConfig:
    """Tests for pipeline-level configuration loading."""

    def test_defaults(self, monkeypatch: pytest.MonkeyPatch):
        for key in [
            "TALKBOUT_BUFFER_WINDOW_SECONDS",
            "TALKBOUT_BUFFER_MAX_BATCH_SIZE",
            "TALKBOUT_SNAPSHOT_DIR",
            "TALKBOUT_RETENTION_HOURS",
            "TALKBOUT_STALE_STREAM_SECONDS",
            "TALKBOUT_HEALTH_LOG_INTERVAL",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = load_pipeline_config()
        assert config["buffer_window_seconds"] == DEFAULT_BUFFER_WINDOW_SECONDS
        assert config["buffer_max_batch_size"] == DEFAULT_BUFFER_MAX_BATCH_SIZE
        assert config["snapshot_dir"] == DEFAULT_SNAPSHOT_DIR
        assert config["retention_hours"] == DEFAULT_RETENTION_HOURS
        assert config["stale_stream_seconds"] == DEFAULT_STALE_STREAM_SECONDS
        assert config["health_log_interval"] == DEFAULT_HEALTH_LOG_INTERVAL

    def test_custom_values(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TALKBOUT_BUFFER_WINDOW_SECONDS", "300")
        monkeypatch.setenv("TALKBOUT_BUFFER_MAX_BATCH_SIZE", "50")
        monkeypatch.setenv("TALKBOUT_SNAPSHOT_DIR", "/tmp/snapshots")
        monkeypatch.setenv("TALKBOUT_RETENTION_HOURS", "48")
        monkeypatch.setenv("TALKBOUT_STALE_STREAM_SECONDS", "900")
        monkeypatch.setenv("TALKBOUT_HEALTH_LOG_INTERVAL", "120")

        config = load_pipeline_config()
        assert config["buffer_window_seconds"] == 300
        assert config["buffer_max_batch_size"] == 50
        assert config["snapshot_dir"] == "/tmp/snapshots"
        assert config["retention_hours"] == 48
        assert config["stale_stream_seconds"] == 900.0
        assert config["health_log_interval"] == 120.0


# ===========================================================================
# IngestionPipeline — on_post callback
# ===========================================================================


class TestPipelineOnPost:
    """Tests for the _on_post callback wiring."""

    def _make_pipeline(self, tmp_path: Path) -> IngestionPipeline:
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"
        buffer = MagicMock(spec=PostBuffer)
        extractor = MagicMock(spec=TopicExtractor)
        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()
        return IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
        )

    def test_on_post_adds_to_buffer(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        post = _make_post()
        pipeline._on_post(post)
        pipeline._buffer.add_post.assert_called_once_with(post)

    def test_on_post_records_health(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        post = _make_post()
        pipeline._on_post(post)
        status = pipeline.health.get_status()
        assert status.posts_received == 1


# ===========================================================================
# IngestionPipeline — on_batch callback
# ===========================================================================


class TestPipelineOnBatch:
    """Tests for the _on_batch callback (extractor → store)."""

    def _make_pipeline(
        self, tmp_path: Path, extracted_topics=None
    ) -> IngestionPipeline:
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"
        buffer = MagicMock(spec=PostBuffer)
        extractor = MagicMock(spec=TopicExtractor)
        if extracted_topics is not None:
            extractor.extract.return_value = extracted_topics
        else:
            extractor.extract.return_value = []
        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()
        return IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
        )

    def test_on_batch_calls_extractor(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        batch = _make_batch()
        pipeline._on_batch(batch)
        pipeline._extractor.extract.assert_called_once_with(batch)

    def test_on_batch_merges_topics_into_store(self, tmp_path: Path):
        topics = [
            ExtractedTopic(topic="Donauinselfest", score=0.9, count=3),
            ExtractedTopic(topic="U2 Störung", score=0.6, count=2),
        ]
        pipeline = self._make_pipeline(tmp_path, extracted_topics=topics)
        batch = _make_batch()
        pipeline._on_batch(batch)
        assert pipeline.store.get_topic_count() == 2

    def test_on_batch_records_success_health(self, tmp_path: Path):
        topics = [
            ExtractedTopic(topic="Test", score=0.5, count=1),
        ]
        pipeline = self._make_pipeline(tmp_path, extracted_topics=topics)
        batch = _make_batch()
        pipeline._on_batch(batch)
        status = pipeline.health.get_status()
        assert status.batches_processed == 1
        assert status.topics_extracted == 1

    def test_on_batch_records_failure_health(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path, extracted_topics=[])
        batch = _make_batch()  # non-empty batch but extractor returns []
        pipeline._on_batch(batch)
        status = pipeline.health.get_status()
        assert status.batches_failed == 1

    def test_on_batch_saves_snapshot(self, tmp_path: Path):
        topics = [ExtractedTopic(topic="Test", score=0.5, count=1)]
        pipeline = self._make_pipeline(tmp_path, extracted_topics=topics)
        batch = _make_batch()
        pipeline._on_batch(batch)
        snapshot_dir = tmp_path / "snapshots"
        assert snapshot_dir.exists()
        snapshots = list(snapshot_dir.glob("topics_*.json"))
        assert len(snapshots) >= 1

    def test_on_batch_empty_batch_no_failure(self, tmp_path: Path):
        """Empty batch (0 posts) should not be recorded as a failure."""
        pipeline = self._make_pipeline(tmp_path, extracted_topics=[])
        batch = _make_batch(posts=(), post_count=0)
        pipeline._on_batch(batch)
        status = pipeline.health.get_status()
        assert status.batches_failed == 0
        assert status.batches_processed == 1


# ===========================================================================
# IngestionPipeline — graceful shutdown
# ===========================================================================


class TestPipelineShutdown:
    """Tests for graceful shutdown behavior."""

    def _make_pipeline(self, tmp_path: Path) -> IngestionPipeline:
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"
        buffer = MagicMock(spec=PostBuffer)
        extractor = MagicMock(spec=TopicExtractor)
        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()
        return IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
        )

    def test_stop_stops_datasource(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline.stop()
        pipeline._datasource.stop.assert_called_once()

    def test_stop_stops_buffer(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline.stop()
        pipeline._buffer.stop.assert_called_once()

    def test_stop_saves_final_snapshot(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline.stop()
        snapshot_dir = tmp_path / "snapshots"
        # Even with no topics, the snapshot should be attempted
        # (TopicStore.save_snapshot creates the dir)
        assert snapshot_dir.exists()

    def test_stop_cancels_health_timer(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        # Simulate a running health timer
        timer = MagicMock()
        pipeline._health_timer = timer
        pipeline.stop()
        timer.cancel.assert_called_once()
        assert pipeline._health_timer is None

    def test_stop_order_datasource_before_buffer(self, tmp_path: Path):
        """Datasource should stop before buffer to avoid new posts during flush."""
        pipeline = self._make_pipeline(tmp_path)
        call_order = []
        pipeline._datasource.stop.side_effect = lambda: call_order.append(
            "datasource"
        )
        pipeline._buffer.stop.side_effect = lambda: call_order.append("buffer")
        pipeline.stop()
        assert call_order == ["datasource", "buffer"]

    def test_stop_handles_datasource_error(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline._datasource.stop.side_effect = RuntimeError("Stream error")
        # Should not raise
        pipeline.stop()
        # Buffer should still be stopped
        pipeline._buffer.stop.assert_called_once()

    def test_stop_handles_buffer_error(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline._buffer.stop.side_effect = RuntimeError("Buffer error")
        # Should not raise
        pipeline.stop()

    def test_signal_handler_sets_stop_event(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline._on_signal(signal.SIGINT, None)
        assert pipeline._stop_event.is_set()

    def test_signal_handler_sigterm(self, tmp_path: Path):
        pipeline = self._make_pipeline(tmp_path)
        pipeline._on_signal(signal.SIGTERM, None)
        assert pipeline._stop_event.is_set()


# ===========================================================================
# IngestionPipeline — start/stop lifecycle
# ===========================================================================


class TestPipelineLifecycle:
    """Tests for the full start/stop lifecycle."""

    def _make_pipeline(self, tmp_path: Path) -> IngestionPipeline:
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"
        buffer = MagicMock(spec=PostBuffer)
        extractor = MagicMock(spec=TopicExtractor)
        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()
        return IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
            health_log_interval=9999,  # Don't fire during test
        )

    def test_start_and_signal_shutdown(self, tmp_path: Path):
        """Pipeline should start and stop cleanly on signal."""
        pipeline = self._make_pipeline(tmp_path)

        def send_stop():
            time.sleep(0.1)
            pipeline._stop_event.set()

        stop_thread = threading.Thread(target=send_stop)
        stop_thread.start()

        pipeline.start()
        stop_thread.join(timeout=2)

        pipeline._datasource.start.assert_called_once()
        pipeline._buffer.start.assert_called_once()
        pipeline._datasource.stop.assert_called_once()
        pipeline._buffer.stop.assert_called_once()

    def test_start_wires_callbacks(self, tmp_path: Path):
        """The datasource should be started with on_post and on_error callbacks."""
        pipeline = self._make_pipeline(tmp_path)

        def send_stop():
            time.sleep(0.1)
            pipeline._stop_event.set()

        stop_thread = threading.Thread(target=send_stop)
        stop_thread.start()
        pipeline.start()
        stop_thread.join(timeout=2)

        call_args = pipeline._datasource.start.call_args
        assert call_args[0][0] == pipeline._on_post
        assert call_args[1]["on_error"] == pipeline._on_stream_error


# ===========================================================================
# Full pipeline integration: stream → buffer → extractor → store
# ===========================================================================


class TestPipelineIntegration:
    """End-to-end integration tests with real buffer and store, mocked externals."""

    def test_full_pipeline_post_to_topic(self, tmp_path: Path):
        """Post ingested by stream → buffered → extracted → merged into store."""
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"

        # Use a real buffer with tiny window so it flushes quickly
        # We'll manually trigger the callback instead
        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()

        extractor = MagicMock(spec=TopicExtractor)
        extractor.extract.return_value = [
            ExtractedTopic(topic="Donauinselfest", score=0.9, count=3),
            ExtractedTopic(topic="U2 Störung", score=0.6, count=2),
        ]

        # Create a real buffer that calls the pipeline's on_batch
        buffer = PostBuffer(
            window_seconds=1,
            source="mastodon:wien.rocks",
            max_batch_size=2,  # Will flush after 2 posts
        )

        pipeline = IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
        )

        # Wire buffer callback
        buffer._on_batch = pipeline._on_batch

        # Simulate pipeline: start buffer, add posts
        buffer.start()

        post1 = _make_post(id="1", text="Donauinselfest ist toll!")
        post2 = _make_post(id="2", text="U2 Störung nervt.")

        pipeline._on_post(post1)
        pipeline._on_post(post2)

        # Buffer should have flushed (max_batch_size=2)
        # Give it a moment
        time.sleep(0.2)

        buffer.stop()

        # Verify topics landed in store
        topics = store.get_current_topics()
        assert len(topics) == 2
        topic_names = {t.name for t in topics}
        assert "Donauinselfest" in topic_names
        assert "U2 Störung" in topic_names

        # Verify health recorded correctly
        status = health.get_status()
        assert status.posts_received == 2
        assert status.batches_processed >= 1
        assert status.topics_extracted >= 2

    def test_full_pipeline_extraction_failure(self, tmp_path: Path):
        """When extraction fails, batch is dropped but pipeline continues."""
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"

        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()

        extractor = MagicMock(spec=TopicExtractor)
        extractor.extract.return_value = []  # Simulates extraction failure

        buffer = PostBuffer(
            window_seconds=1,
            source="mastodon:wien.rocks",
            max_batch_size=1,  # Flush after each post
        )

        pipeline = IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
        )
        buffer._on_batch = pipeline._on_batch

        buffer.start()
        pipeline._on_post(_make_post())
        time.sleep(0.2)
        buffer.stop()

        assert store.get_topic_count() == 0
        status = health.get_status()
        assert status.batches_failed >= 1

    def test_full_pipeline_multiple_batches(self, tmp_path: Path):
        """Multiple batches accumulate topics in the store."""
        ds = MagicMock(spec=MastodonDatasource)
        ds.source_id = "mastodon:wien.rocks"

        store = TopicStore(snapshot_dir=tmp_path / "snapshots")
        health = HealthMonitor()

        call_count = 0

        def extract_side_effect(batch):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [ExtractedTopic(topic="Topic A", score=0.8, count=1)]
            else:
                return [ExtractedTopic(topic="Topic B", score=0.7, count=1)]

        extractor = MagicMock(spec=TopicExtractor)
        extractor.extract.side_effect = extract_side_effect

        buffer = PostBuffer(
            window_seconds=1,
            source="mastodon:wien.rocks",
            max_batch_size=1,
        )

        pipeline = IngestionPipeline(
            datasource=ds,
            buffer=buffer,
            extractor=extractor,
            store=store,
            health=health,
        )
        buffer._on_batch = pipeline._on_batch

        buffer.start()
        pipeline._on_post(_make_post(id="1", text="First"))
        time.sleep(0.2)
        pipeline._on_post(_make_post(id="2", text="Second"))
        time.sleep(0.2)
        buffer.stop()

        topics = store.get_current_topics()
        topic_names = {t.name for t in topics}
        assert "Topic A" in topic_names
        assert "Topic B" in topic_names

        status = health.get_status()
        assert status.batches_processed >= 2


# ===========================================================================
# build_pipeline
# ===========================================================================


class TestBuildPipeline:
    """Tests for the build_pipeline factory function."""

    def test_build_pipeline_with_valid_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        env_file = tmp_path / ".env"
        env_file.write_text(
            textwrap.dedent("""\
                MASTODON_INSTANCE_URL=https://wien.rocks
                MASTODON_CLIENT_ID=test_client_id
                MASTODON_CLIENT_SECRET=test_client_secret
                MASTODON_ACCESS_TOKEN=test_access_token
                ANTHROPIC_API_KEY=sk-ant-test-key
            """)
        )

        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://wien.rocks")
        monkeypatch.setenv("MASTODON_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("MASTODON_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test_access_token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        monkeypatch.setenv("TALKBOUT_SNAPSHOT_DIR", str(tmp_path / "snapshots"))

        with patch("talkbout.extractor.anthropic.Anthropic"):
            pipeline = build_pipeline()

        assert pipeline is not None
        assert isinstance(pipeline, IngestionPipeline)

    def test_build_pipeline_raises_on_missing_mastodon_config(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("MASTODON_INSTANCE_URL", raising=False)
        monkeypatch.delenv("MASTODON_CLIENT_ID", raising=False)
        monkeypatch.delenv("MASTODON_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("MASTODON_ACCESS_TOKEN", raising=False)
        # Provide a nonexistent .env so no file is loaded
        monkeypatch.setenv("DOTENV_PATH", "/nonexistent/.env")

        with pytest.raises(ValueError, match="Invalid Mastodon configuration"):
            build_pipeline()

    def test_build_pipeline_raises_on_missing_extractor_config(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://wien.rocks")
        monkeypatch.setenv("MASTODON_CLIENT_ID", "test_client_id")
        monkeypatch.setenv("MASTODON_CLIENT_SECRET", "test_client_secret")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "test_access_token")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError, match="Invalid extractor configuration"):
            build_pipeline()
