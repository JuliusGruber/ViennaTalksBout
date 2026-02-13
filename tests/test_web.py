"""Tests for viennatalksbout.web — FastAPI web UI and API endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from viennatalksbout.health import HealthMonitor, HealthStatus
from viennatalksbout.store import Topic, TopicState, TopicStore
from viennatalksbout.web import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
SOURCE = "mastodon:wien.rocks"


def _make_topic(
    name: str = "Donauinselfest",
    score: float = 0.8,
    state: TopicState = TopicState.GROWING,
) -> Topic:
    """Create a Topic with sensible defaults for testing."""
    return Topic(
        name=name,
        normalized_name=name.lower(),
        score=score,
        first_seen=NOW,
        last_seen=NOW,
        source=SOURCE,
        state=state,
    )


def _make_store_mock(topics: list[Topic] | None = None) -> MagicMock:
    """Create a MagicMock(spec=TopicStore) with pre-configured responses."""
    store = MagicMock(spec=TopicStore)
    store.get_current_topics.return_value = topics or []
    return store


def _make_health_mock(
    posts_received: int = 0,
    batches_processed: int = 0,
    batches_failed: int = 0,
    topics_extracted: int = 0,
    stream_stale: bool = False,
) -> MagicMock:
    """Create a MagicMock(spec=HealthMonitor) returning a HealthStatus."""
    health = MagicMock(spec=HealthMonitor)
    health.get_status.return_value = HealthStatus(
        last_post_time=None,
        posts_received=posts_received,
        batches_processed=batches_processed,
        batches_failed=batches_failed,
        topics_extracted=topics_extracted,
        stream_stale=stream_stale,
    )
    return health


def _make_client(
    store: MagicMock | None = None,
    health: MagicMock | None = None,
    snapshot_dir: Path | None = None,
) -> TestClient:
    """Create a TestClient for the web app with mocked dependencies."""
    app = create_app(
        store=store or _make_store_mock(),
        health=health or _make_health_mock(),
        snapshot_dir=snapshot_dir,
    )
    return TestClient(app)


# ===========================================================================
# GET /
# ===========================================================================


class TestIndexEndpoint:
    """Tests for the index page."""

    def test_returns_200(self):
        client = _make_client()
        resp = client.get("/")
        assert resp.status_code == 200

    def test_returns_html_content_type(self):
        client = _make_client()
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_contains_tag_cloud_element(self):
        client = _make_client()
        resp = client.get("/")
        assert "tag-cloud" in resp.text


# ===========================================================================
# GET /api/topics
# ===========================================================================


class TestTopicsEndpoint:
    """Tests for the live topics API."""

    def test_returns_topics_list(self):
        topics = [
            _make_topic("Donauinselfest", 0.9, TopicState.GROWING),
            _make_topic("U2 Störung", 0.5, TopicState.ENTERING),
        ]
        store = _make_store_mock(topics)
        client = _make_client(store=store)

        resp = client.get("/api/topics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Donauinselfest"
        assert data[0]["score"] == 0.9
        assert data[0]["state"] == "growing"

    def test_correct_fields(self):
        topics = [_make_topic()]
        store = _make_store_mock(topics)
        client = _make_client(store=store)

        resp = client.get("/api/topics")
        data = resp.json()
        entry = data[0]
        assert set(entry.keys()) == {
            "name", "score", "state", "first_seen", "last_seen", "source",
        }

    def test_empty_when_no_topics(self):
        client = _make_client()
        resp = client.get("/api/topics")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_historical_by_hour(self, tmp_path):
        """Historical query loads a snapshot file."""
        # Create a snapshot file for hour 14
        now = datetime.now(timezone.utc)
        filename = f"topics_{now.strftime('%Y%m%d')}_14.json"
        snapshot_data = {
            "timestamp": NOW.isoformat(),
            "topics": [
                {
                    "name": "Snapshot Topic",
                    "score": 0.7,
                    "first_seen": NOW.isoformat(),
                    "last_seen": NOW.isoformat(),
                    "source": SOURCE,
                    "state": "entering",
                    "batches_since_seen": 0,
                },
            ],
        }
        (tmp_path / filename).write_text(json.dumps(snapshot_data), encoding="utf-8")

        store = MagicMock(spec=TopicStore)
        # Delegate load_snapshot to the real store method
        real_store = TopicStore()
        store.load_snapshot.side_effect = real_store.load_snapshot

        client = _make_client(store=store, snapshot_dir=tmp_path)
        resp = client.get("/api/topics?hour=14")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Snapshot Topic"

    def test_404_for_missing_snapshot(self, tmp_path):
        store = _make_store_mock()
        store.load_snapshot.side_effect = FileNotFoundError("not found")
        client = _make_client(store=store, snapshot_dir=tmp_path)

        resp = client.get("/api/topics?hour=3")
        assert resp.status_code == 404

    def test_400_for_invalid_hour(self):
        client = _make_client()
        resp = client.get("/api/topics?hour=25")
        assert resp.status_code == 400

    def test_400_for_negative_hour(self):
        client = _make_client()
        resp = client.get("/api/topics?hour=-1")
        assert resp.status_code == 400

    def test_404_when_snapshots_not_configured(self):
        """hour param without snapshot_dir returns 404."""
        client = _make_client(snapshot_dir=None)
        resp = client.get("/api/topics?hour=14")
        assert resp.status_code == 404


# ===========================================================================
# GET /api/health
# ===========================================================================


class TestHealthEndpoint:
    """Tests for the health endpoint."""

    def test_returns_metrics(self):
        health = _make_health_mock(
            posts_received=42,
            batches_processed=5,
            batches_failed=1,
            topics_extracted=15,
            stream_stale=False,
        )
        client = _make_client(health=health)

        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["posts_received"] == 42
        assert data["batches_processed"] == 5
        assert data["batches_failed"] == 1
        assert data["topics_extracted"] == 15
        assert data["stream_stale"] is False
        assert data["llm_success_rate"] == pytest.approx(5 / 6)

    def test_initial_zero_state(self):
        client = _make_client()
        resp = client.get("/api/health")
        data = resp.json()
        assert data["posts_received"] == 0
        assert data["batches_processed"] == 0
        assert data["batches_failed"] == 0
        assert data["topics_extracted"] == 0
        assert data["stream_stale"] is False
        assert data["llm_success_rate"] == 1.0

    def test_excludes_last_post_time(self):
        """last_post_time is monotonic and should not be exposed."""
        client = _make_client()
        resp = client.get("/api/health")
        data = resp.json()
        assert "last_post_time" not in data


# ===========================================================================
# GET /api/snapshots
# ===========================================================================


class TestSnapshotsEndpoint:
    """Tests for the snapshots listing endpoint."""

    def test_lists_available_hours(self, tmp_path):
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y%m%d")
        for hour in [9, 10, 14]:
            (tmp_path / f"topics_{today}_{hour:02d}.json").write_text("{}")

        client = _make_client(snapshot_dir=tmp_path)
        resp = client.get("/api/snapshots")
        assert resp.status_code == 200
        data = resp.json()
        assert data == ["09", "10", "14"]

    def test_empty_when_no_files(self, tmp_path):
        client = _make_client(snapshot_dir=tmp_path)
        resp = client.get("/api/snapshots")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_empty_when_snapshot_dir_not_configured(self):
        client = _make_client(snapshot_dir=None)
        resp = client.get("/api/snapshots")
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# create_app factory
# ===========================================================================


class TestCreateApp:
    """Tests for the app factory."""

    def test_wires_store_on_state(self):
        store = _make_store_mock()
        health = _make_health_mock()
        app = create_app(store=store, health=health)
        assert app.state.store is store

    def test_wires_health_on_state(self):
        store = _make_store_mock()
        health = _make_health_mock()
        app = create_app(store=store, health=health)
        assert app.state.health is health

    def test_wires_snapshot_dir_on_state(self, tmp_path):
        store = _make_store_mock()
        health = _make_health_mock()
        app = create_app(store=store, health=health, snapshot_dir=tmp_path)
        assert app.state.snapshot_dir == tmp_path

    def test_snapshot_dir_none_when_not_provided(self):
        store = _make_store_mock()
        health = _make_health_mock()
        app = create_app(store=store, health=health)
        assert app.state.snapshot_dir is None
