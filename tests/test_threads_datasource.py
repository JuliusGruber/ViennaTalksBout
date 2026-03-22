"""Tests for viennatalksbout.threads.datasource — Threads keyword search datasource.

Unit tests covering:
- BaseDatasource interface compliance
- source_id property
- strip_html helper
- validate_thread filter
- parse_thread converter
- _parse_threads_datetime helper
- start() delivering posts via on_post callback
- Deduplication across poll cycles
- Error handling
- stop() terminating the poll thread
- ThreadsConfig loading and validation
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from viennatalksbout.config import ThreadsConfig, load_threads_config
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.threads.datasource import (
    ThreadsDatasource,
    _parse_threads_datetime,
    parse_thread,
    strip_html,
    validate_thread,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> ThreadsConfig:
    """Create a ThreadsConfig with test defaults."""
    defaults = dict(
        access_token="test-token-123",
        keywords=("wien", "vienna"),
        poll_interval=300,
        user_agent="ViennaTalksBout/1.0 (test)",
        enabled=True,
    )
    defaults.update(overrides)
    return ThreadsConfig(**defaults)


def _make_thread_data(
    id: str = "12345678901234567",
    text: str = "A great post about Wien and its culture",
    timestamp: str = "2024-06-15T12:00:00+0000",
) -> dict:
    """Create a mock Threads API post object."""
    return {
        "id": id,
        "text": text,
        "timestamp": timestamp,
    }


# ===========================================================================
# Interface
# ===========================================================================


class TestInterface:
    """Test that ThreadsDatasource satisfies BaseDatasource."""

    def test_is_subclass(self):
        assert issubclass(ThreadsDatasource, BaseDatasource)

    def test_instance(self):
        ds = ThreadsDatasource(config=_make_config())
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    def test_default_keywords(self):
        ds = ThreadsDatasource(config=_make_config())
        assert ds.source_id == "threads:wien+vienna"

    def test_custom_keywords(self):
        ds = ThreadsDatasource(config=_make_config(keywords=("graz",)))
        assert ds.source_id == "threads:graz"

    def test_multiple_keywords(self):
        ds = ThreadsDatasource(
            config=_make_config(keywords=("wien", "vienna", "austria"))
        )
        assert ds.source_id == "threads:wien+vienna+austria"


# ===========================================================================
# strip_html
# ===========================================================================


class TestStripHtml:
    def test_removes_tags(self):
        assert strip_html("<b>bold</b> text") == "bold text"

    def test_removes_links(self):
        assert strip_html('<a href="url">click</a>') == "click"

    def test_normalizes_whitespace(self):
        assert strip_html("  multiple   spaces  ") == "multiple spaces"

    def test_empty(self):
        assert strip_html("") == ""

    def test_plain_text_unchanged(self):
        assert strip_html("plain text") == "plain text"

    def test_nested_tags(self):
        assert strip_html("<div><p>nested</p></div>") == "nested"


# ===========================================================================
# _parse_threads_datetime
# ===========================================================================


class TestParseThreadsDatetime:
    def test_iso_format(self):
        dt = _parse_threads_datetime("2024-06-15T12:00:00")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_with_z_suffix(self):
        dt = _parse_threads_datetime("2024-06-15T12:00:00Z")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_with_fractional_seconds(self):
        dt = _parse_threads_datetime("2024-06-15T12:00:00.123456")
        assert dt.tzinfo == timezone.utc

    def test_short_fractional_seconds(self):
        dt = _parse_threads_datetime("2024-06-15T12:00:00.123")
        assert dt.tzinfo == timezone.utc

    def test_empty_string_returns_now(self):
        dt = _parse_threads_datetime("")
        assert dt.tzinfo == timezone.utc


# ===========================================================================
# validate_thread
# ===========================================================================


class TestValidateThread:
    def test_valid_post(self):
        thread_data = _make_thread_data()
        assert validate_thread(thread_data) is True

    def test_empty_text(self):
        thread_data = _make_thread_data(text="")
        assert validate_thread(thread_data) is False

    def test_whitespace_only(self):
        thread_data = _make_thread_data(text="   ")
        assert validate_thread(thread_data) is False

    def test_too_short(self):
        thread_data = _make_thread_data(text="Hi")
        assert validate_thread(thread_data) is False

    def test_minimum_length(self):
        thread_data = _make_thread_data(text="1234567890")
        assert validate_thread(thread_data) is True


# ===========================================================================
# parse_thread
# ===========================================================================


class TestParseThread:
    def test_text(self):
        thread_data = _make_thread_data(text="Wien is beautiful")
        post = parse_thread(thread_data, "threads:wien+vienna")
        assert post.text == "Wien is beautiful"

    def test_id_format(self):
        thread_data = _make_thread_data(id="12345678901234567")
        post = parse_thread(thread_data, "threads:wien+vienna")
        assert post.id == "threads:12345678901234567"

    def test_timestamp(self):
        thread_data = _make_thread_data(timestamp="2024-06-15T12:00:00Z")
        post = parse_thread(thread_data, "threads:wien+vienna")
        assert post.created_at.tzinfo == timezone.utc
        assert post.created_at == datetime(
            2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc
        )

    def test_language_is_none(self):
        thread_data = _make_thread_data()
        post = parse_thread(thread_data, "threads:wien+vienna")
        assert post.language is None

    def test_source(self):
        thread_data = _make_thread_data()
        post = parse_thread(thread_data, "threads:wien+vienna")
        assert post.source == "threads:wien+vienna"

    def test_html_stripped(self):
        thread_data = _make_thread_data(text="Check <b>this</b> out in Wien")
        post = parse_thread(thread_data, "threads:wien+vienna")
        assert post.text == "Check this out in Wien"


# ===========================================================================
# start delivers posts
# ===========================================================================


class TestStartDeliversPosts:
    """Test that start() polls keywords and calls on_post."""

    @patch("viennatalksbout.threads.datasource.requests.Session")
    def test_delivers_posts(self, mock_session_cls):
        thread_data = _make_thread_data(text="Wien Discussion about culture")
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [thread_data]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = ThreadsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert "Wien Discussion" in post.text

    @patch("viennatalksbout.threads.datasource.requests.Session")
    def test_polls_all_keywords(self, mock_session_cls):
        """Should search each keyword separately."""
        thread1 = _make_thread_data(id="1", text="Post about Wien today")
        thread2 = _make_thread_data(id="2", text="Post about Vienna today")

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"data": [thread1]}
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"data": [thread2]}
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = ThreadsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        ds.start(on_post)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 2


# ===========================================================================
# Deduplication
# ===========================================================================


class TestDeduplication:
    """Test that second poll cycle skips already-seen items."""

    @patch("viennatalksbout.threads.datasource.requests.Session")
    def test_posts_not_re_emitted(self, mock_session_cls):
        thread_data = _make_thread_data(id="100")

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [thread_data]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = ThreadsDatasource(
            config=_make_config(keywords=("wien",), poll_interval=9999)
        )
        on_post = MagicMock()

        # First poll
        ds._poll_keywords(on_post)
        assert on_post.call_count == 1

        # Second poll with same post
        ds._poll_keywords(on_post)
        assert on_post.call_count == 1  # Still 1 — dedup

    @patch("viennatalksbout.threads.datasource.requests.Session")
    def test_new_posts_emitted(self, mock_session_cls):
        thread1 = _make_thread_data(id="100", text="First post about Wien")
        thread2 = _make_thread_data(id="101", text="Second post about Wien")

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"data": [thread1]}
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"data": [thread2, thread1]}
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = ThreadsDatasource(
            config=_make_config(keywords=("wien",), poll_interval=9999)
        )
        on_post = MagicMock()

        # First poll
        ds._poll_keywords(on_post)
        assert on_post.call_count == 1

        # Second poll with new + old post
        ds._poll_keywords(on_post)
        assert on_post.call_count == 2


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Test error resilience."""

    @patch("viennatalksbout.threads.datasource.requests.Session")
    def test_api_error_calls_on_error(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = Exception("API error")

        ds = ThreadsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1

    @patch("viennatalksbout.threads.datasource.requests.Session")
    def test_error_continues_polling(self, mock_session_cls):
        """After an error, the next poll cycle should still run."""
        thread_data = _make_thread_data()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [thread_data]}
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First keyword poll errors
                raise Exception("API error")
            return mock_response

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = get_side_effect

        ds = ThreadsDatasource(config=_make_config(poll_interval=0.05))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.5)
        ds.stop()

        assert on_error.call_count >= 1
        assert on_post.call_count >= 1


# ===========================================================================
# Stop
# ===========================================================================


class TestStop:
    """Test stop behavior."""

    def test_thread_terminates(self):
        ds = ThreadsDatasource(config=_make_config(poll_interval=9999))

        with patch("viennatalksbout.threads.datasource.requests.Session"):
            ds.start(MagicMock())
            assert ds._thread is not None
            assert ds._thread.is_alive()

            ds.stop()
            assert ds._thread is None

    def test_stop_idempotent(self):
        ds = ThreadsDatasource(config=_make_config())
        ds.stop()  # Should not raise even without start
        ds.stop()


# ===========================================================================
# Config
# ===========================================================================


class TestThreadsConfig:
    """Test ThreadsConfig loading and validation."""

    def test_load_defaults(self):
        import os

        env_vars = [
            "THREADS_ENABLED", "THREADS_ACCESS_TOKEN", "THREADS_KEYWORDS",
            "THREADS_POLL_INTERVAL", "THREADS_USER_AGENT",
        ]
        old_vals = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            config = load_threads_config()
            assert config.enabled is False
            assert config.keywords == ("wien", "vienna")
            assert config.poll_interval == 300
        finally:
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_load_custom(self):
        import os

        env = {
            "THREADS_ENABLED": "true",
            "THREADS_ACCESS_TOKEN": "my-secret-token",
            "THREADS_KEYWORDS": "wien,vienna,graz",
            "THREADS_POLL_INTERVAL": "120",
            "THREADS_USER_AGENT": "TestBot/1.0",
        }
        old_vals = {k: os.environ.pop(k, None) for k in env}
        os.environ.update(env)
        try:
            config = load_threads_config()
            assert config.enabled is True
            assert config.access_token == "my-secret-token"
            assert config.keywords == ("wien", "vienna", "graz")
            assert config.poll_interval == 120
            assert config.user_agent == "TestBot/1.0"
        finally:
            for k in env:
                os.environ.pop(k, None)
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_validation_missing_token(self):
        config = ThreadsConfig(access_token="", enabled=True)
        errors = config.validate()
        assert any("THREADS_ACCESS_TOKEN" in e for e in errors)

    def test_validation_empty_keywords(self):
        config = ThreadsConfig(
            access_token="token", keywords=(), enabled=True
        )
        errors = config.validate()
        assert any("THREADS_KEYWORDS" in e for e in errors)

    def test_validation_negative_interval(self):
        config = ThreadsConfig(
            access_token="token", poll_interval=-1, enabled=True
        )
        errors = config.validate()
        assert any("THREADS_POLL_INTERVAL" in e for e in errors)

    def test_validation_disabled_skips(self):
        config = ThreadsConfig(access_token="", keywords=(), enabled=False)
        errors = config.validate()
        assert errors == []
