"""Tests for viennatalksbout.bluesky.datasource — Bluesky polling datasource.

Unit tests covering:
- BaseDatasource interface compliance
- source_id property
- strip_facets helper
- validate_post filter
- parse_post converter
- _parse_bluesky_datetime helper
- start() delivering posts via on_post callback
- Deduplication across poll cycles
- Error handling
- stop() terminating the poll thread
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from viennatalksbout.config import BlueskyConfig, load_bluesky_config
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.bluesky.datasource import (
    BlueskyDatasource,
    _parse_bluesky_datetime,
    parse_post,
    strip_facets,
    validate_post,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> BlueskyConfig:
    """Create a BlueskyConfig with test defaults."""
    defaults = dict(
        search_queries=("wien", "vienna"),
        lang="de",
        poll_interval=120,
        limit=25,
        user_agent="ViennaTalksBout/1.0 (test)",
        enabled=True,
    )
    defaults.update(overrides)
    return BlueskyConfig(**defaults)


def _make_post_view(
    uri: str = "at://did:plc:abc123/app.bsky.feed.post/xyz789",
    text: str = "Schöner Tag in Wien heute!",
    created_at: str = "2024-06-15T12:00:00.000Z",
    langs: list[str] | None = None,
) -> dict:
    """Create a mock Bluesky postView object."""
    record: dict = {
        "text": text,
        "createdAt": created_at,
    }
    if langs is not None:
        record["langs"] = langs
    else:
        record["langs"] = ["de"]
    return {
        "uri": uri,
        "cid": "bafyreifake",
        "record": record,
        "author": {
            "did": "did:plc:abc123",
            "handle": "testuser.bsky.social",
        },
    }


# ===========================================================================
# Interface
# ===========================================================================


class TestInterface:
    """Test that BlueskyDatasource satisfies BaseDatasource."""

    def test_is_subclass(self):
        assert issubclass(BlueskyDatasource, BaseDatasource)

    def test_instance(self):
        ds = BlueskyDatasource(config=_make_config())
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    def test_source_id(self):
        ds = BlueskyDatasource(config=_make_config())
        assert ds.source_id == "bluesky:search"


# ===========================================================================
# strip_facets
# ===========================================================================


class TestStripFacets:
    def test_removes_urls(self):
        assert strip_facets("check https://example.com out") == "check out"

    def test_removes_multiple_urls(self):
        text = "link1 https://a.com link2 http://b.com end"
        assert strip_facets(text) == "link1 link2 end"

    def test_normalizes_whitespace(self):
        assert strip_facets("too   many    spaces") == "too many spaces"

    def test_strips_leading_trailing(self):
        assert strip_facets("  hello  ") == "hello"

    def test_empty(self):
        assert strip_facets("") == ""

    def test_plain_text_unchanged(self):
        assert strip_facets("plain text here") == "plain text here"

    def test_url_only(self):
        assert strip_facets("https://example.com") == ""


# ===========================================================================
# _parse_bluesky_datetime
# ===========================================================================


class TestParseBlueskyDatetime:
    def test_with_z_suffix(self):
        dt = _parse_bluesky_datetime("2024-06-15T12:00:00Z")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_with_offset(self):
        dt = _parse_bluesky_datetime("2024-06-15T12:00:00+00:00")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_with_fractional_seconds(self):
        dt = _parse_bluesky_datetime("2024-06-15T12:00:00.123Z")
        assert dt.tzinfo == timezone.utc

    def test_empty_string_returns_now(self):
        dt = _parse_bluesky_datetime("")
        assert dt.tzinfo == timezone.utc

    def test_invalid_string_returns_now(self):
        dt = _parse_bluesky_datetime("not-a-date")
        assert dt.tzinfo == timezone.utc


# ===========================================================================
# validate_post
# ===========================================================================


class TestValidatePost:
    def test_valid_post(self):
        post_view = _make_post_view()
        assert validate_post(post_view) is True

    def test_empty_text(self):
        post_view = _make_post_view(text="")
        assert validate_post(post_view) is False

    def test_whitespace_only_text(self):
        post_view = _make_post_view(text="   ")
        assert validate_post(post_view) is False

    def test_missing_record(self):
        post_view = {"uri": "at://test", "author": {}}
        assert validate_post(post_view) is False


# ===========================================================================
# parse_post
# ===========================================================================


class TestParsePost:
    def test_basic_fields(self):
        post_view = _make_post_view(text="Wien ist toll")
        post = parse_post(post_view, "bluesky:search")
        assert post.text == "Wien ist toll"
        assert post.source == "bluesky:search"

    def test_id_format(self):
        uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
        post_view = _make_post_view(uri=uri)
        post = parse_post(post_view, "bluesky:search")
        assert post.id == f"bluesky:{uri}"

    def test_timestamp(self):
        post_view = _make_post_view(created_at="2024-06-15T12:00:00Z")
        post = parse_post(post_view, "bluesky:search")
        assert post.created_at == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_language_from_langs(self):
        post_view = _make_post_view(langs=["de"])
        post = parse_post(post_view, "bluesky:search")
        assert post.language == "de"

    def test_language_multiple_takes_first(self):
        post_view = _make_post_view(langs=["en", "de"])
        post = parse_post(post_view, "bluesky:search")
        assert post.language == "en"

    def test_language_empty_langs(self):
        post_view = _make_post_view(langs=[])
        post = parse_post(post_view, "bluesky:search")
        assert post.language is None

    def test_urls_stripped(self):
        post_view = _make_post_view(text="check https://example.com out")
        post = parse_post(post_view, "bluesky:search")
        assert "https://" not in post.text
        assert post.text == "check out"

    def test_returns_post_instance(self):
        post_view = _make_post_view()
        post = parse_post(post_view, "bluesky:search")
        assert isinstance(post, Post)


# ===========================================================================
# start delivers posts
# ===========================================================================


class TestStartDeliversPosts:
    """Test that start() polls search API and calls on_post."""

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_delivers_posts(self, mock_session_cls):
        post_view = _make_post_view(text="Wien Discussion")
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [post_view]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = BlueskyDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert "Wien Discussion" in post.text

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_polls_all_queries(self, mock_session_cls):
        """Should poll each search query separately."""
        post1 = _make_post_view(
            uri="at://did:plc:a/app.bsky.feed.post/1", text="Wien post"
        )
        post2 = _make_post_view(
            uri="at://did:plc:b/app.bsky.feed.post/2", text="Vienna post"
        )

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"posts": [post1]}
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"posts": [post2]}
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = BlueskyDatasource(config=_make_config(poll_interval=9999))
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

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_posts_not_re_emitted(self, mock_session_cls):
        post_view = _make_post_view()

        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [post_view]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = BlueskyDatasource(
            config=_make_config(search_queries=("wien",), poll_interval=9999)
        )
        on_post = MagicMock()

        # First poll
        ds._poll_queries(on_post)
        assert on_post.call_count == 1

        # Second poll with same post
        ds._poll_queries(on_post)
        assert on_post.call_count == 1  # Still 1 — dedup

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_new_posts_emitted(self, mock_session_cls):
        post1 = _make_post_view(
            uri="at://did:plc:a/app.bsky.feed.post/1", text="First"
        )
        post2 = _make_post_view(
            uri="at://did:plc:a/app.bsky.feed.post/2", text="Second"
        )

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"posts": [post1]}
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"posts": [post2, post1]}
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = BlueskyDatasource(
            config=_make_config(search_queries=("wien",), poll_interval=9999)
        )
        on_post = MagicMock()

        # First poll
        ds._poll_queries(on_post)
        assert on_post.call_count == 1

        # Second poll with new + old
        ds._poll_queries(on_post)
        assert on_post.call_count == 2

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_invalid_posts_still_tracked(self, mock_session_cls):
        """Posts that fail validation should still be added to seen set."""
        empty_post = _make_post_view(
            uri="at://did:plc:a/app.bsky.feed.post/empty", text=""
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [empty_post]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = BlueskyDatasource(
            config=_make_config(search_queries=("wien",), poll_interval=9999)
        )
        on_post = MagicMock()

        ds._poll_queries(on_post)
        assert on_post.call_count == 0  # Empty text filtered

        # URI should still be in seen set
        assert "at://did:plc:a/app.bsky.feed.post/empty" in ds._seen_uris


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Test error resilience."""

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_api_error_calls_on_error(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = Exception("API error")

        ds = BlueskyDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1

    @patch("viennatalksbout.bluesky.datasource.requests.Session")
    def test_error_continues_polling(self, mock_session_cls):
        """After an error, the next poll cycle should still run."""
        post_view = _make_post_view()
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [post_view]}
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First 2 calls error (2 queries)
                raise Exception("API error")
            return mock_response

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = get_side_effect

        ds = BlueskyDatasource(config=_make_config(poll_interval=0.05))
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
        ds = BlueskyDatasource(config=_make_config(poll_interval=9999))

        with patch("viennatalksbout.bluesky.datasource.requests.Session"):
            ds.start(MagicMock())
            assert ds._thread is not None
            assert ds._thread.is_alive()

            ds.stop()
            assert ds._thread is None

    def test_stop_idempotent(self):
        ds = BlueskyDatasource(config=_make_config())
        ds.stop()  # Should not raise even without start
        ds.stop()


# ===========================================================================
# Config
# ===========================================================================


class TestBlueskyConfig:
    """Test BlueskyConfig loading and validation."""

    def test_load_defaults(self):
        env_vars = [
            "BLUESKY_ENABLED", "BLUESKY_SEARCH_QUERIES", "BLUESKY_LANG",
            "BLUESKY_POLL_INTERVAL", "BLUESKY_LIMIT", "BLUESKY_USER_AGENT",
        ]
        old_vals = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            config = load_bluesky_config()
            assert config.enabled is False
            assert config.search_queries == ("wien", "vienna")
            assert config.lang == "de"
            assert config.poll_interval == 120
            assert config.limit == 25
        finally:
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_load_custom(self):
        env = {
            "BLUESKY_ENABLED": "true",
            "BLUESKY_SEARCH_QUERIES": "wien,graz,linz",
            "BLUESKY_LANG": "en",
            "BLUESKY_POLL_INTERVAL": "60",
            "BLUESKY_LIMIT": "50",
            "BLUESKY_USER_AGENT": "TestBot/1.0",
        }
        old_vals = {k: os.environ.pop(k, None) for k in env}
        os.environ.update(env)
        try:
            config = load_bluesky_config()
            assert config.enabled is True
            assert config.search_queries == ("wien", "graz", "linz")
            assert config.lang == "en"
            assert config.poll_interval == 60
            assert config.limit == 50
            assert config.user_agent == "TestBot/1.0"
        finally:
            for k in env:
                os.environ.pop(k, None)
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_validation_empty_queries(self):
        config = BlueskyConfig(search_queries=(), enabled=True)
        errors = config.validate()
        assert any("BLUESKY_SEARCH_QUERIES" in e for e in errors)

    def test_validation_negative_interval(self):
        config = BlueskyConfig(poll_interval=-1, enabled=True)
        errors = config.validate()
        assert any("BLUESKY_POLL_INTERVAL" in e for e in errors)

    def test_validation_limit_too_low(self):
        config = BlueskyConfig(limit=0, enabled=True)
        errors = config.validate()
        assert any("BLUESKY_LIMIT" in e for e in errors)

    def test_validation_limit_too_high(self):
        config = BlueskyConfig(limit=101, enabled=True)
        errors = config.validate()
        assert any("BLUESKY_LIMIT" in e for e in errors)

    def test_validation_disabled_skips(self):
        config = BlueskyConfig(search_queries=(), limit=0, enabled=False)
        errors = config.validate()
        assert errors == []

    def test_load_invalid_raises(self):
        env = {
            "BLUESKY_ENABLED": "true",
            "BLUESKY_SEARCH_QUERIES": "",
        }
        old_vals = {k: os.environ.pop(k, None) for k in env}
        os.environ.update(env)
        try:
            with pytest.raises(ValueError, match="Invalid Bluesky configuration"):
                load_bluesky_config()
        finally:
            for k in env:
                os.environ.pop(k, None)
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v


# ===========================================================================
# Integration test
# ===========================================================================


class TestBlueskyIntegration:
    """Integration tests that make real HTTP calls to the Bluesky public API."""

    @pytest.mark.integration
    def test_search_returns_posts(self):
        """Verify the public search API returns results for 'wien'."""
        import requests

        url = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
        resp = requests.get(
            url,
            params={"q": "wien", "limit": 5, "lang": "de"},
            headers={"User-Agent": "ViennaTalksBout/1.0 (integration-test)"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        assert "posts" in data
        assert len(data["posts"]) > 0

        # Verify structure of first post
        first = data["posts"][0]
        assert "uri" in first
        assert "record" in first
        assert "text" in first["record"]
