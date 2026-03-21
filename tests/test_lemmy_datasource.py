"""Tests for viennatalksbout.lemmy.datasource — Lemmy polling datasource.

Unit tests covering:
- BaseDatasource interface compliance
- source_id property
- strip_markdown helper
- validate_post filter
- parse_post converter
- _parse_lemmy_datetime helper
- start() delivering posts via on_post callback
- Deduplication across poll cycles
- Error handling
- stop() terminating the poll thread
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from viennatalksbout.config import LemmyConfig
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.lemmy.datasource import (
    LemmyDatasource,
    _parse_lemmy_datetime,
    parse_post,
    strip_markdown,
    validate_post,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> LemmyConfig:
    """Create a LemmyConfig with test defaults."""
    defaults = dict(
        instance="feddit.org",
        communities=("austria", "dach"),
        poll_interval=300,
        user_agent="ViennaTalksBout/1.0 (test)",
        enabled=True,
    )
    defaults.update(overrides)
    return LemmyConfig(**defaults)


def _make_post_data(
    id: int = 12345,
    name: str = "Test post title",
    body: str = "Test body text about Vienna",
    published: str = "2024-06-15T12:00:00.000000Z",
    ap_id: str = "https://feddit.org/post/12345",
    deleted: bool = False,
    removed: bool = False,
    featured_community: bool = False,
    featured_local: bool = False,
    creator_name: str = "test_user",
    community_name: str = "austria",
) -> dict:
    """Create a mock Lemmy API post object."""
    return {
        "post": {
            "id": id,
            "name": name,
            "body": body,
            "published": published,
            "ap_id": ap_id,
            "deleted": deleted,
            "removed": removed,
            "featured_community": featured_community,
            "featured_local": featured_local,
        },
        "creator": {
            "name": creator_name,
        },
        "community": {
            "name": community_name,
        },
    }


# ===========================================================================
# Interface
# ===========================================================================


class TestInterface:
    """Test that LemmyDatasource satisfies BaseDatasource."""

    def test_is_subclass(self):
        assert issubclass(LemmyDatasource, BaseDatasource)

    def test_instance(self):
        ds = LemmyDatasource(config=_make_config())
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    def test_default_instance(self):
        ds = LemmyDatasource(config=_make_config())
        assert ds.source_id == "lemmy:feddit.org"

    def test_custom_instance(self):
        ds = LemmyDatasource(config=_make_config(instance="linz.city"))
        assert ds.source_id == "lemmy:linz.city"


# ===========================================================================
# strip_markdown
# ===========================================================================


class TestStripMarkdown:
    def test_bold(self):
        assert strip_markdown("**bold text**") == "bold text"

    def test_italic(self):
        assert strip_markdown("*italic text*") == "italic text"

    def test_strikethrough(self):
        assert strip_markdown("~~removed~~") == "removed"

    def test_links(self):
        assert strip_markdown("[click here](https://example.com)") == "click here"

    def test_headings(self):
        assert strip_markdown("# Heading\nText") == "Heading Text"

    def test_block_quotes(self):
        assert strip_markdown("> quoted text") == "quoted text"

    def test_inline_code(self):
        assert strip_markdown("use `code` here") == "use code here"

    def test_code_blocks(self):
        result = strip_markdown("```\ncode block\n```")
        assert "```" not in result

    def test_images(self):
        assert strip_markdown("![alt](https://img.png)") == "alt"

    def test_mixed(self):
        text = "**Bold** and *italic* with [link](url)"
        result = strip_markdown(text)
        assert result == "Bold and italic with link"

    def test_empty(self):
        assert strip_markdown("") == ""

    def test_plain_text_unchanged(self):
        assert strip_markdown("plain text") == "plain text"


# ===========================================================================
# _parse_lemmy_datetime
# ===========================================================================


class TestParseLemmyDatetime:
    def test_with_z_suffix(self):
        dt = _parse_lemmy_datetime("2024-06-15T12:00:00.000000Z")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_without_z_suffix(self):
        dt = _parse_lemmy_datetime("2024-06-15T12:00:00.000000")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_without_fractional_seconds(self):
        dt = _parse_lemmy_datetime("2024-06-15T12:00:00")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_short_fractional_seconds(self):
        dt = _parse_lemmy_datetime("2024-06-15T12:00:00.123")
        assert dt.tzinfo == timezone.utc

    def test_empty_string_returns_now(self):
        dt = _parse_lemmy_datetime("")
        assert dt.tzinfo == timezone.utc

    def test_long_fractional_seconds(self):
        """Lemmy sometimes returns more than 6 fractional digits."""
        dt = _parse_lemmy_datetime("2024-06-15T12:00:00.1234567890")
        assert dt == datetime(2024, 6, 15, 12, 0, 0, 123456, tzinfo=timezone.utc)


# ===========================================================================
# validate_post
# ===========================================================================


class TestValidatePost:
    def test_valid_post(self):
        post_data = _make_post_data()
        assert validate_post(post_data) is True

    def test_deleted(self):
        post_data = _make_post_data(deleted=True)
        assert validate_post(post_data) is False

    def test_removed(self):
        post_data = _make_post_data(removed=True)
        assert validate_post(post_data) is False

    def test_featured_community(self):
        post_data = _make_post_data(featured_community=True)
        assert validate_post(post_data) is False

    def test_featured_local(self):
        post_data = _make_post_data(featured_local=True)
        assert validate_post(post_data) is False

    def test_empty_title_and_body(self):
        post_data = _make_post_data(name="", body="")
        assert validate_post(post_data) is False

    def test_title_only(self):
        post_data = _make_post_data(name="Title", body="")
        assert validate_post(post_data) is True

    def test_body_only(self):
        post_data = _make_post_data(name="", body="Body text")
        assert validate_post(post_data) is True


# ===========================================================================
# parse_post
# ===========================================================================


class TestParsePost:
    def test_title_and_body(self):
        post_data = _make_post_data(name="Title", body="Body text")
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.text == "Title. Body text"

    def test_title_only(self):
        post_data = _make_post_data(name="Title only", body="")
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.text == "Title only"

    def test_body_only(self):
        post_data = _make_post_data(name="", body="Body only")
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.text == "Body only"

    def test_id_format(self):
        post_data = _make_post_data(ap_id="https://feddit.org/post/12345")
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.id == "lemmy:https://feddit.org/post/12345"

    def test_timestamp(self):
        post_data = _make_post_data(published="2024-06-15T12:00:00.000000Z")
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.created_at.tzinfo == timezone.utc
        assert post.created_at == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_language_default_de(self):
        post_data = _make_post_data()
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.language == "de"

    def test_source(self):
        post_data = _make_post_data()
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.source == "lemmy:feddit.org"

    def test_markdown_stripped(self):
        post_data = _make_post_data(
            name="**Bold Title**", body="Check [this](url) out"
        )
        post = parse_post(post_data, "lemmy:feddit.org")
        assert post.text == "Bold Title. Check this out"


# ===========================================================================
# start delivers posts
# ===========================================================================


class TestStartDeliversPosts:
    """Test that start() polls communities and calls on_post."""

    @patch("viennatalksbout.lemmy.datasource.requests.Session")
    def test_delivers_posts(self, mock_session_cls):
        post_data = _make_post_data(name="Wien Discussion", body="Content here")
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [post_data]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = LemmyDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert "Wien Discussion" in post.text

    @patch("viennatalksbout.lemmy.datasource.requests.Session")
    def test_polls_all_communities(self, mock_session_cls):
        """Should poll each community separately."""
        post1 = _make_post_data(id=1, name="Post from austria")
        post2 = _make_post_data(id=2, name="Post from dach")

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"posts": [post1]}
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"posts": [post2]}
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = LemmyDatasource(config=_make_config(poll_interval=9999))
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

    @patch("viennatalksbout.lemmy.datasource.requests.Session")
    def test_posts_not_re_emitted(self, mock_session_cls):
        post_data = _make_post_data(id=100)

        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [post_data]}
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = LemmyDatasource(
            config=_make_config(communities=("austria",), poll_interval=9999)
        )
        on_post = MagicMock()

        # First poll
        ds._poll_communities(on_post)
        assert on_post.call_count == 1

        # Second poll with same post
        ds._poll_communities(on_post)
        assert on_post.call_count == 1  # Still 1 — dedup

    @patch("viennatalksbout.lemmy.datasource.requests.Session")
    def test_new_posts_emitted(self, mock_session_cls):
        post1 = _make_post_data(id=100, name="First post")
        post2 = _make_post_data(id=101, name="Second post")

        mock_response1 = MagicMock()
        mock_response1.json.return_value = {"posts": [post1]}
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {"posts": [post2, post1]}
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = LemmyDatasource(
            config=_make_config(communities=("austria",), poll_interval=9999)
        )
        on_post = MagicMock()

        # First poll
        ds._poll_communities(on_post)
        assert on_post.call_count == 1

        # Second poll with new + old post
        ds._poll_communities(on_post)
        assert on_post.call_count == 2


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Test error resilience."""

    @patch("viennatalksbout.lemmy.datasource.requests.Session")
    def test_api_error_calls_on_error(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = Exception("API error")

        ds = LemmyDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1

    @patch("viennatalksbout.lemmy.datasource.requests.Session")
    def test_error_continues_polling(self, mock_session_cls):
        """After an error, the next poll cycle should still run."""
        post_data = _make_post_data()
        mock_response = MagicMock()
        mock_response.json.return_value = {"posts": [post_data]}
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First community poll errors
                raise Exception("API error")
            return mock_response

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = get_side_effect

        ds = LemmyDatasource(config=_make_config(poll_interval=0.05))
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
        ds = LemmyDatasource(config=_make_config(poll_interval=9999))

        with patch("viennatalksbout.lemmy.datasource.requests.Session"):
            ds.start(MagicMock())
            assert ds._thread is not None
            assert ds._thread.is_alive()

            ds.stop()
            assert ds._thread is None

    def test_stop_idempotent(self):
        ds = LemmyDatasource(config=_make_config())
        ds.stop()  # Should not raise even without start
        ds.stop()


# ===========================================================================
# Config
# ===========================================================================


class TestLemmyConfig:
    """Test LemmyConfig loading and validation."""

    def test_load_defaults(self):
        import os
        from viennatalksbout.config import load_lemmy_config

        # Ensure clean env
        env_vars = [
            "LEMMY_ENABLED", "LEMMY_INSTANCE", "LEMMY_COMMUNITIES",
            "LEMMY_POLL_INTERVAL", "LEMMY_USER_AGENT",
        ]
        old_vals = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            config = load_lemmy_config()
            assert config.enabled is False
            assert config.instance == "feddit.org"
            assert config.communities == ("austria", "dach")
            assert config.poll_interval == 300
        finally:
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_load_custom(self):
        import os
        from viennatalksbout.config import load_lemmy_config

        env = {
            "LEMMY_ENABLED": "true",
            "LEMMY_INSTANCE": "linz.city",
            "LEMMY_COMMUNITIES": "austria,wien",
            "LEMMY_POLL_INTERVAL": "120",
            "LEMMY_USER_AGENT": "TestBot/1.0",
        }
        old_vals = {k: os.environ.pop(k, None) for k in env}
        os.environ.update(env)
        try:
            config = load_lemmy_config()
            assert config.enabled is True
            assert config.instance == "linz.city"
            assert config.communities == ("austria", "wien")
            assert config.poll_interval == 120
            assert config.user_agent == "TestBot/1.0"
        finally:
            for k in env:
                os.environ.pop(k, None)
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_validation_empty_instance(self):
        config = LemmyConfig(instance="", enabled=True)
        errors = config.validate()
        assert any("LEMMY_INSTANCE" in e for e in errors)

    def test_validation_empty_communities(self):
        config = LemmyConfig(communities=(), enabled=True)
        errors = config.validate()
        assert any("LEMMY_COMMUNITIES" in e for e in errors)

    def test_validation_negative_interval(self):
        config = LemmyConfig(poll_interval=-1, enabled=True)
        errors = config.validate()
        assert any("LEMMY_POLL_INTERVAL" in e for e in errors)

    def test_validation_disabled_skips(self):
        config = LemmyConfig(instance="", communities=(), enabled=False)
        errors = config.validate()
        assert errors == []
