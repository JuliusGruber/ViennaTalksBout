"""Web UI for ViennaTalksBout — serves a live tag cloud via FastAPI.

Routes:
    GET /              → index.html (static frontend)
    GET /api/topics    → current live topics as JSON
    GET /api/topics?hour=14 → historical snapshot for the given hour
    GET /api/health    → pipeline health metrics
    GET /api/snapshots → list of available snapshot hours for today

Run with ``python -m viennatalksbout`` (default mode).
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query, Response
from fastapi.responses import FileResponse

from viennatalksbout.health import HealthMonitor
from viennatalksbout.store import TopicStore

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8000


def create_app(
    store: TopicStore,
    health: HealthMonitor,
    snapshot_dir: str | Path | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        store: The topic store to read live topics from.
        health: The health monitor for pipeline metrics.
        snapshot_dir: Directory containing hourly snapshot JSON files.

    Returns:
        A configured FastAPI instance.
    """
    app = FastAPI(title="ViennaTalksBout")
    app.state.store = store
    app.state.health = health
    app.state.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @app.get("/api/topics")
    async def topics(hour: int | None = Query(default=None)) -> Response:
        if hour is not None:
            if not (0 <= hour <= 23):
                return Response(
                    content='{"error": "hour must be 0-23"}',
                    status_code=400,
                    media_type="application/json",
                )
            if app.state.snapshot_dir is None:
                return Response(
                    content='{"error": "snapshots not configured"}',
                    status_code=404,
                    media_type="application/json",
                )
            now = datetime.now(timezone.utc)
            filename = f"topics_{now.strftime('%Y%m%d')}_{hour:02d}.json"
            path = app.state.snapshot_dir / filename
            try:
                snapshot_topics = app.state.store.load_snapshot(path)
            except FileNotFoundError:
                return Response(
                    content='{"error": "snapshot not found"}',
                    status_code=404,
                    media_type="application/json",
                )
            return _topics_to_json(snapshot_topics)

        live_topics = app.state.store.get_current_topics()
        return _topics_to_json(live_topics)

    @app.get("/api/health")
    async def health_endpoint():
        status = app.state.health.get_status()
        return {
            "posts_received": status.posts_received,
            "batches_processed": status.batches_processed,
            "batches_failed": status.batches_failed,
            "topics_extracted": status.topics_extracted,
            "stream_stale": status.stream_stale,
            "llm_success_rate": status.llm_success_rate,
        }

    @app.get("/api/snapshots")
    async def snapshots():
        if app.state.snapshot_dir is None or not app.state.snapshot_dir.exists():
            return []
        now = datetime.now(timezone.utc)
        today_prefix = f"topics_{now.strftime('%Y%m%d')}_"
        hours: list[str] = []
        for path in sorted(app.state.snapshot_dir.glob(f"{today_prefix}*.json")):
            stem = path.stem
            hour_str = stem[len(today_prefix):]
            hours.append(hour_str)
        return hours

    return app


def _topics_to_json(topics) -> Response:
    """Serialize a list of Topic objects to a JSON response."""
    import json

    data = [
        {
            "name": t.name,
            "score": t.score,
            "state": t.state.value,
            "first_seen": t.first_seen.isoformat(),
            "last_seen": t.last_seen.isoformat(),
            "source": t.source,
        }
        for t in topics
    ]
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        media_type="application/json",
    )


def _run_pipeline_in_background(pipeline) -> threading.Thread:
    """Start the ingestion pipeline in a daemon thread.

    Args:
        pipeline: An IngestionPipeline instance.

    Returns:
        The daemon thread running the pipeline.
    """
    def target():
        pipeline.start(install_signal_handlers=False)

    thread = threading.Thread(target=target, name="pipeline", daemon=True)
    thread.start()
    logger.info("Pipeline started in background thread")
    return thread


def main() -> None:
    """Entry point for web mode: ``python -m viennatalksbout``."""
    from viennatalksbout.ingest import build_pipeline, setup_logging

    setup_logging()

    try:
        pipeline = build_pipeline()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    thread = _run_pipeline_in_background(pipeline)

    host = os.environ.get("VIENNATALKSBOUT_WEB_HOST", DEFAULT_WEB_HOST)
    port = int(os.environ.get("VIENNATALKSBOUT_WEB_PORT", str(DEFAULT_WEB_PORT)))

    app = create_app(
        store=pipeline.store,
        health=pipeline.health,
        snapshot_dir=pipeline.store._snapshot_dir,
    )

    logger.info("Starting web server on %s:%d", host, port)
    uvicorn.run(app, host=host, port=port)
