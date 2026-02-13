"""Ingestion pipeline orchestrator for ViennaTalksBout.

Wires all components into a running pipeline:

    Datasources (Mastodon, RSS, ...) → PostBuffer → TopicExtractor → TopicStore

Run with ``python -m viennatalksbout.ingest``.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from pathlib import Path
from types import FrameType

from viennatalksbout.buffer import PostBatch, PostBuffer
from viennatalksbout.config import load_config, load_extractor_config, load_rss_config
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.extractor import TopicExtractor
from viennatalksbout.health import HealthMonitor
from viennatalksbout.mastodon.polling import MastodonPollingDatasource
from viennatalksbout.mastodon.stream import MastodonDatasource
from viennatalksbout.news.rss import RssDatasource
from viennatalksbout.persistence import PostDatabase
from viennatalksbout.store import TopicStore

logger = logging.getLogger(__name__)

# Defaults for pipeline-level settings (read from environment)
DEFAULT_BUFFER_WINDOW_SECONDS = 600  # 10 minutes
DEFAULT_BUFFER_MAX_BATCH_SIZE = 100
DEFAULT_SNAPSHOT_DIR = "data/snapshots"
DEFAULT_RETENTION_HOURS = 24
DEFAULT_STALE_STREAM_SECONDS = 1800  # 30 minutes
DEFAULT_HEALTH_LOG_INTERVAL = 300  # 5 minutes
DEFAULT_DATASOURCE_MODE = "stream"
DEFAULT_POLL_INTERVAL_SECONDS = 30


def setup_logging() -> None:
    """Configure structured logging for the pipeline."""
    log_level = os.environ.get("VIENNATALKSBOUT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(handler)


def load_pipeline_config() -> dict:
    """Load pipeline-level configuration from environment variables.

    Returns a dict with pipeline settings (buffer window, snapshot dir, etc.).
    Mastodon and extractor configs are loaded separately.
    """
    return {
        "buffer_window_seconds": int(
            os.environ.get(
                "VIENNATALKSBOUT_BUFFER_WINDOW_SECONDS",
                str(DEFAULT_BUFFER_WINDOW_SECONDS),
            )
        ),
        "buffer_max_batch_size": int(
            os.environ.get(
                "VIENNATALKSBOUT_BUFFER_MAX_BATCH_SIZE",
                str(DEFAULT_BUFFER_MAX_BATCH_SIZE),
            )
        ),
        "snapshot_dir": os.environ.get(
            "VIENNATALKSBOUT_SNAPSHOT_DIR", DEFAULT_SNAPSHOT_DIR
        ),
        "retention_hours": int(
            os.environ.get(
                "VIENNATALKSBOUT_RETENTION_HOURS",
                str(DEFAULT_RETENTION_HOURS),
            )
        ),
        "stale_stream_seconds": float(
            os.environ.get(
                "VIENNATALKSBOUT_STALE_STREAM_SECONDS",
                str(DEFAULT_STALE_STREAM_SECONDS),
            )
        ),
        "health_log_interval": float(
            os.environ.get(
                "VIENNATALKSBOUT_HEALTH_LOG_INTERVAL",
                str(DEFAULT_HEALTH_LOG_INTERVAL),
            )
        ),
        "datasource_mode": os.environ.get(
            "MASTODON_DATASOURCE_MODE", DEFAULT_DATASOURCE_MODE
        ),
        "poll_interval_seconds": int(
            os.environ.get(
                "MASTODON_POLL_INTERVAL_SECONDS",
                str(DEFAULT_POLL_INTERVAL_SECONDS),
            )
        ),
        "db_path": os.environ.get(
            "VIENNATALKSBOUT_DB_PATH", "data/viennatalksbout.db"
        ),
    }


class IngestionPipeline:
    """Orchestrates the full ingestion pipeline.

    Wires: Datasources → PostBuffer → TopicExtractor → TopicStore

    Handles signal-based graceful shutdown, periodic health logging,
    and periodic snapshot saving.

    Args:
        datasources: One or more datasources feeding the pipeline.
        buffer: The post buffer for batching.
        extractor: The Claude-powered topic extractor.
        store: The topic store with lifecycle management.
        health: The health monitor.
        health_log_interval: Seconds between health log entries.
        db: Optional SQLite post database for persistence.
    """

    def __init__(
        self,
        datasources: list[BaseDatasource],
        buffer: PostBuffer,
        extractor: TopicExtractor,
        store: TopicStore,
        health: HealthMonitor,
        health_log_interval: float = DEFAULT_HEALTH_LOG_INTERVAL,
        db: PostDatabase | None = None,
    ) -> None:
        self._datasources = datasources
        self._buffer = buffer
        self._extractor = extractor
        self._store = store
        self._health = health
        self._health_log_interval = health_log_interval
        self._db = db

        self._stop_event = threading.Event()
        self._health_timer: threading.Timer | None = None
        self._original_sigint: signal.Handlers | None = None
        self._original_sigterm: signal.Handlers | None = None

    @property
    def health(self) -> HealthMonitor:
        """The health monitor instance."""
        return self._health

    @property
    def store(self) -> TopicStore:
        """The topic store instance."""
        return self._store

    def _on_post(self, post: Post) -> None:
        """Callback: datasource received a post → add to buffer."""
        self._health.record_post()
        if self._db is not None:
            is_new = self._db.save_post(post)
            if not is_new:
                logger.info("Duplicate post skipped: %s", post.id)
                return
        self._buffer.add_post(post)
        logger.debug("Post received: %s (source=%s)", post.id, post.source)

    def _on_batch(self, batch: PostBatch) -> None:
        """Callback: buffer flushed a batch → extract topics → merge into store."""
        logger.info(
            "Processing batch: %d posts (window %s → %s)",
            batch.post_count,
            batch.window_start.strftime("%H:%M:%S"),
            batch.window_end.strftime("%H:%M:%S"),
        )

        topics = self._extractor.extract(batch)

        if topics:
            self._health.record_batch_success(len(topics))
            self._store.merge(topics, batch.source)
            logger.info(
                "Merged %d topics into store (active: %d)",
                len(topics),
                self._store.get_topic_count(),
            )
        else:
            if batch.post_count > 0:
                self._health.record_batch_failure()
                logger.warning(
                    "No topics extracted from batch of %d posts",
                    batch.post_count,
                )
            else:
                self._health.record_batch_success(0)

        # Save snapshot and clean up old ones
        self._store.save_snapshot()
        self._store.cleanup_snapshots()

        # Mark posts as processed in the database
        if self._db is not None:
            post_ids = [p.id for p in batch.posts]
            self._db.mark_batch_processed(post_ids)

    def _on_stream_error(self, err: Exception) -> None:
        """Callback: stream encountered an error."""
        logger.error("Stream error: %s", err)

    def _recover_unprocessed_posts(self) -> None:
        """Re-inject unprocessed posts from a previous run into the buffer."""
        assert self._db is not None
        posts = self._db.get_unprocessed_posts()
        if posts:
            for post in posts:
                self._buffer.add_post(post)
            logger.info("Recovered %d unprocessed posts from database", len(posts))

    def _on_signal(self, signum: int, frame: FrameType | None) -> None:
        """Signal handler for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — initiating graceful shutdown", sig_name)
        self._stop_event.set()

    def _schedule_health_log(self) -> None:
        """Schedule the next periodic health log."""
        if self._stop_event.is_set():
            return
        self._health_timer = threading.Timer(
            self._health_log_interval, self._health_log_tick
        )
        self._health_timer.daemon = True
        self._health_timer.start()

    def _health_log_tick(self) -> None:
        """Periodic health log callback."""
        self._health.check_and_log()
        self._schedule_health_log()

    def start(self, install_signal_handlers: bool = True) -> None:
        """Start the pipeline and block until shutdown is requested.

        Installs signal handlers for SIGINT and SIGTERM (unless disabled),
        starts the datasource, buffer, and health logging, then waits for
        the stop event.

        Args:
            install_signal_handlers: If False, skip signal handler
                installation. Set to False when running in a non-main
                thread (e.g. behind a web server).
        """
        logger.info("Starting ViennaTalksBout ingestion pipeline")

        # Install signal handlers (only from the main thread)
        if install_signal_handlers:
            self._original_sigint = signal.getsignal(signal.SIGINT)
            self._original_sigterm = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGINT, self._on_signal)
            signal.signal(signal.SIGTERM, self._on_signal)

        # Start components
        self._buffer.start()
        logger.info("Post buffer started")

        # Recover unprocessed posts from previous runs
        if self._db is not None:
            self._recover_unprocessed_posts()

        for ds in self._datasources:
            ds.start(self._on_post, on_error=self._on_stream_error)
            logger.info("Started datasource: %s", ds.source_id)

        # Start periodic health logging
        self._schedule_health_log()

        logger.info("Pipeline running — press Ctrl+C to stop")

        # Block until shutdown
        self._stop_event.wait()

        # Graceful shutdown
        self.stop()

    def stop(self) -> None:
        """Stop all pipeline components gracefully.

        1. Stop the datasource (close SSE connection)
        2. Stop the buffer (flushes pending posts)
        3. Cancel health timer
        4. Save a final snapshot
        5. Restore original signal handlers
        """
        logger.info("Shutting down pipeline...")

        # Stop all datasources first (no more incoming posts)
        for ds in self._datasources:
            try:
                ds.stop()
                logger.info("Datasource stopped: %s", ds.source_id)
            except Exception:
                logger.exception("Error stopping datasource %s", ds.source_id)

        # Stop buffer (triggers final flush → extractor → store)
        try:
            self._buffer.stop()
            logger.info("Buffer stopped (final flush complete)")
        except Exception:
            logger.exception("Error stopping buffer")

        # Cancel health timer
        if self._health_timer is not None:
            self._health_timer.cancel()
            self._health_timer = None

        # Final snapshot
        try:
            self._store.save_snapshot()
            logger.info("Final snapshot saved")
        except Exception:
            logger.exception("Error saving final snapshot")

        # Final health report
        self._health.check_and_log()

        # Cleanup and close database
        if self._db is not None:
            try:
                self._db.cleanup_old_posts()
                self._db.close()
                logger.info("Database cleaned up and closed")
            except Exception:
                logger.exception("Error closing database")

        # Restore original signal handlers (may fail from non-main thread)
        try:
            if self._original_sigint is not None:
                signal.signal(signal.SIGINT, self._original_sigint)
            if self._original_sigterm is not None:
                signal.signal(signal.SIGTERM, self._original_sigterm)
        except ValueError:
            pass  # Not in main thread — signal restoration not possible

        logger.info("Pipeline shutdown complete")


def build_pipeline() -> IngestionPipeline:
    """Build the ingestion pipeline from environment configuration.

    Loads all configuration, creates components, and wires them together.

    Returns:
        A configured IngestionPipeline ready to start.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    mastodon_config = load_config()
    extractor_config = load_extractor_config()
    pipeline_config = load_pipeline_config()

    logger.info(
        "Configuration loaded: instance=%s, model=%s, "
        "buffer_window=%ds, snapshot_dir=%s",
        mastodon_config.instance_url,
        extractor_config.model,
        pipeline_config["buffer_window_seconds"],
        pipeline_config["snapshot_dir"],
    )

    db_path = pipeline_config["db_path"]
    db = PostDatabase(db_path) if db_path else None

    # Build datasource list
    datasources: list[BaseDatasource] = []

    datasource_mode = pipeline_config["datasource_mode"]
    if datasource_mode == "polling":
        # Recover since_id from database so restarts skip already-seen posts
        initial_since_id = db.get_max_post_id() if db is not None else None
        if initial_since_id:
            logger.info("Resuming polling from since_id=%s", initial_since_id)
        mastodon_ds: BaseDatasource = MastodonPollingDatasource(
            instance_url=mastodon_config.instance_url,
            access_token=mastodon_config.access_token,
            poll_interval=pipeline_config["poll_interval_seconds"],
            initial_since_id=initial_since_id,
        )
    else:
        mastodon_ds = MastodonDatasource(
            instance_url=mastodon_config.instance_url,
            access_token=mastodon_config.access_token,
        )
    datasources.append(mastodon_ds)

    # Optionally add RSS datasource
    rss_config = load_rss_config()
    if rss_config.enabled:
        rss_ds = RssDatasource(
            feeds=list(rss_config.feeds),
            poll_interval=rss_config.poll_interval,
            user_agent=rss_config.user_agent,
        )
        datasources.append(rss_ds)
        logger.info("RSS datasource enabled with %d feeds", len(rss_config.feeds))

    extractor = TopicExtractor(
        api_key=extractor_config.api_key,
        model=extractor_config.model,
    )

    store = TopicStore(
        snapshot_dir=pipeline_config["snapshot_dir"],
        retention_hours=pipeline_config["retention_hours"],
    )

    health = HealthMonitor(
        stale_stream_seconds=pipeline_config["stale_stream_seconds"],
    )

    buffer_source = (
        datasources[0].source_id if len(datasources) == 1 else "multi"
    )
    buffer = PostBuffer(
        window_seconds=pipeline_config["buffer_window_seconds"],
        source=buffer_source,
        on_batch=None,  # Will be set after pipeline creation
        max_batch_size=pipeline_config["buffer_max_batch_size"],
    )

    pipeline = IngestionPipeline(
        datasources=datasources,
        buffer=buffer,
        extractor=extractor,
        store=store,
        health=health,
        health_log_interval=pipeline_config["health_log_interval"],
        db=db,
    )

    # Wire the buffer's on_batch callback to the pipeline
    buffer._on_batch = pipeline._on_batch

    return pipeline


def main() -> None:
    """Entry point for ``python -m viennatalksbout.ingest``."""
    setup_logging()

    try:
        pipeline = build_pipeline()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    pipeline.start()
