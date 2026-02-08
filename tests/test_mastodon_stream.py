"""Tests for talkbout.mastodon.stream — stream listener, HTML stripping, filtering, validation."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from talkbout.datasource import BaseDatasource, Post
from talkbout.mastodon.stream import (
    TalkBoutStreamListener,
    filter_status,
    parse_status,
    strip_html,
    validate_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status(**overrides) -> dict:
    """Create a valid Mastodon status dict with sensible defaults."""
    defaults = {
        "id": "123456",
        "content": "<p>Hello from Wien!</p>",
        "created_at": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "language": "de",
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
    }
    defaults.update(overrides)
    return defaults


# ===========================================================================
# HTML stripping
# ===========================================================================


class TestStripHtml:
    """Tests for strip_html()."""

    def test_simple_paragraph(self):
        assert strip_html("<p>Hello world</p>") == "Hello world"

    def test_nested_tags(self):
        html = "<p>Hello <strong>bold</strong> and <em>italic</em></p>"
        assert strip_html(html) == "Hello bold and italic"

    def test_br_tags_become_spaces(self):
        html = "<p>Line one<br>Line two<br/>Line three</p>"
        result = strip_html(html)
        assert "Line one" in result
        assert "Line two" in result
        assert "Line three" in result

    def test_multiple_paragraphs(self):
        html = "<p>First paragraph</p><p>Second paragraph</p>"
        result = strip_html(html)
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_link_tags_extract_text(self):
        html = '<p>Check out <a href="https://example.com">this link</a></p>'
        assert strip_html(html) == "Check out this link"

    def test_empty_html(self):
        assert strip_html("") == ""

    def test_only_tags_no_text(self):
        assert strip_html("<p><br><br></p>") == ""

    def test_html_entities(self):
        html = "<p>Caf&eacute; &amp; more</p>"
        result = strip_html(html)
        assert "Café" in result
        assert "&" in result

    def test_plain_text_passthrough(self):
        assert strip_html("No HTML here") == "No HTML here"

    def test_whitespace_normalized(self):
        html = "<p>  lots   of   spaces  </p>"
        result = strip_html(html)
        # Multiple whitespace characters are collapsed into single spaces
        assert result == "lots of spaces"

    def test_mastodon_typical_post(self):
        html = (
            '<p>Guten Morgen Wien! ☀️</p>'
            '<p>Die <a href="https://wien.rocks/tags/ubahn">#ubahn</a> '
            'ist heute pünktlich.</p>'
        )
        result = strip_html(html)
        assert "Guten Morgen Wien!" in result
        assert "#ubahn" in result
        assert "pünktlich" in result
        assert "<" not in result

    def test_span_and_div_tags(self):
        html = '<div><span class="h-card">@user</span> hello</div>'
        assert strip_html(html) == "@user hello"


# ===========================================================================
# Input validation
# ===========================================================================


class TestValidateStatus:
    """Tests for validate_status()."""

    def test_valid_status_passes(self):
        status = _make_status()
        assert validate_status(status) is status

    def test_non_dict_returns_none(self):
        assert validate_status("not a dict") is None
        assert validate_status(42) is None
        assert validate_status([]) is None
        assert validate_status(None) is None

    def test_missing_id_returns_none(self):
        status = _make_status()
        del status["id"]
        assert validate_status(status) is None

    def test_empty_id_returns_none(self):
        assert validate_status(_make_status(id="")) is None

    def test_none_id_returns_none(self):
        assert validate_status(_make_status(id=None)) is None

    def test_missing_content_returns_none(self):
        status = _make_status()
        del status["content"]
        assert validate_status(status) is None

    def test_null_content_returns_none(self):
        assert validate_status(_make_status(content=None)) is None

    def test_missing_created_at_returns_none(self):
        status = _make_status()
        del status["created_at"]
        assert validate_status(status) is None

    def test_null_created_at_returns_none(self):
        assert validate_status(_make_status(created_at=None)) is None

    def test_empty_content_still_valid(self):
        """Empty string content passes validation — filtering handles it."""
        status = _make_status(content="")
        assert validate_status(status) is not None

    def test_missing_language_still_valid(self):
        """Language is optional — missing language should not fail validation."""
        status = _make_status()
        del status["language"]
        assert validate_status(status) is not None

    def test_null_language_still_valid(self):
        assert validate_status(_make_status(language=None)) is not None

    def test_integer_id_passes(self):
        """Mastodon IDs can be integers in some contexts."""
        status = _make_status(id=123456)
        assert validate_status(status) is not None


# ===========================================================================
# Post filtering
# ===========================================================================


class TestFilterStatus:
    """Tests for filter_status()."""

    def test_normal_post_passes(self):
        assert filter_status(_make_status()) is True

    def test_reblog_filtered_out(self):
        reblog_content = _make_status(id="original")
        status = _make_status(reblog=reblog_content)
        assert filter_status(status) is False

    def test_sensitive_post_filtered_out(self):
        assert filter_status(_make_status(sensitive=True)) is False

    def test_empty_content_filtered_out(self):
        assert filter_status(_make_status(content="")) is False

    def test_html_only_content_filtered_out(self):
        """Post with only HTML tags and no text is effectively empty."""
        assert filter_status(_make_status(content="<p><br></p>")) is False

    def test_whitespace_only_content_filtered_out(self):
        assert filter_status(_make_status(content="<p>   </p>")) is False

    def test_non_sensitive_with_spoiler_text_passes(self):
        """Posts with spoiler_text but sensitive=False should pass."""
        status = _make_status(sensitive=False, spoiler_text="mild spoiler")
        assert filter_status(status) is True

    def test_missing_sensitive_field_treated_as_false(self):
        status = _make_status()
        del status["sensitive"]
        assert filter_status(status) is True

    def test_missing_reblog_field_treated_as_none(self):
        status = _make_status()
        del status["reblog"]
        assert filter_status(status) is True


# ===========================================================================
# Status → Post parsing
# ===========================================================================


class TestParseStatus:
    """Tests for parse_status()."""

    def test_basic_parsing(self):
        status = _make_status()
        post = parse_status(status, "mastodon:wien.rocks")

        assert post.id == "123456"
        assert post.text == "Hello from Wien!"
        assert post.created_at == datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert post.language == "de"
        assert post.source == "mastodon:wien.rocks"

    def test_html_is_stripped(self):
        status = _make_status(content="<p>Bold <strong>text</strong></p>")
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.text == "Bold text"
        assert "<" not in post.text

    def test_iso_string_created_at(self):
        status = _make_status(created_at="2025-06-15T12:00:00Z")
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.created_at == datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_iso_string_with_offset(self):
        status = _make_status(created_at="2025-06-15T14:00:00+02:00")
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.created_at.utcoffset().total_seconds() == 7200

    def test_unexpected_created_at_type_falls_back_to_now(self):
        status = _make_status(created_at=12345)
        post = parse_status(status, "mastodon:wien.rocks")
        # Should be a recent datetime (fallback to now)
        assert isinstance(post.created_at, datetime)
        assert post.created_at.tzinfo is not None

    def test_null_language_becomes_none(self):
        status = _make_status(language=None)
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.language is None

    def test_empty_language_becomes_none(self):
        status = _make_status(language="")
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.language is None

    def test_whitespace_language_becomes_none(self):
        status = _make_status(language="   ")
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.language is None

    def test_missing_language_key_becomes_none(self):
        status = _make_status()
        del status["language"]
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.language is None

    def test_integer_id_converted_to_string(self):
        status = _make_status(id=789)
        post = parse_status(status, "mastodon:wien.rocks")
        assert post.id == "789"

    def test_post_is_frozen(self):
        status = _make_status()
        post = parse_status(status, "mastodon:wien.rocks")
        with pytest.raises(AttributeError):
            post.text = "modified"  # type: ignore[misc]


# ===========================================================================
# TalkBoutStreamListener
# ===========================================================================


class TestTalkBoutStreamListener:
    """Tests for TalkBoutStreamListener callback handling."""

    def _make_listener(self) -> tuple[TalkBoutStreamListener, MagicMock]:
        callback = MagicMock()
        listener = TalkBoutStreamListener(on_post=callback, source="mastodon:wien.rocks")
        return listener, callback

    def test_valid_post_triggers_callback(self):
        listener, callback = self._make_listener()
        listener.on_update(_make_status())

        callback.assert_called_once()
        post = callback.call_args[0][0]
        assert isinstance(post, Post)
        assert post.id == "123456"
        assert post.text == "Hello from Wien!"

    def test_reblog_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        listener.on_update(_make_status(reblog=_make_status(id="original")))
        callback.assert_not_called()

    def test_sensitive_post_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        listener.on_update(_make_status(sensitive=True))
        callback.assert_not_called()

    def test_empty_content_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        listener.on_update(_make_status(content="<p></p>"))
        callback.assert_not_called()

    def test_invalid_status_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        listener.on_update("not a dict")
        callback.assert_not_called()

    def test_missing_id_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        status = _make_status()
        del status["id"]
        listener.on_update(status)
        callback.assert_not_called()

    def test_missing_content_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        status = _make_status()
        del status["content"]
        listener.on_update(status)
        callback.assert_not_called()

    def test_missing_created_at_does_not_trigger_callback(self):
        listener, callback = self._make_listener()
        status = _make_status()
        del status["created_at"]
        listener.on_update(status)
        callback.assert_not_called()

    def test_multiple_valid_posts_trigger_multiple_callbacks(self):
        listener, callback = self._make_listener()
        listener.on_update(_make_status(id="1", content="<p>Post one</p>"))
        listener.on_update(_make_status(id="2", content="<p>Post two</p>"))
        listener.on_update(_make_status(id="3", content="<p>Post three</p>"))

        assert callback.call_count == 3
        posts = [call[0][0] for call in callback.call_args_list]
        assert [p.id for p in posts] == ["1", "2", "3"]

    def test_source_propagated_to_post(self):
        callback = MagicMock()
        listener = TalkBoutStreamListener(on_post=callback, source="mastodon:custom.instance")
        listener.on_update(_make_status())

        post = callback.call_args[0][0]
        assert post.source == "mastodon:custom.instance"

    def test_on_abort_does_not_raise(self):
        listener, _ = self._make_listener()
        # on_abort should log but not raise
        listener.on_abort(ConnectionError("Stream disconnected"))

    def test_on_abort_with_various_exceptions(self):
        listener, _ = self._make_listener()
        listener.on_abort(TimeoutError("timed out"))
        listener.on_abort(OSError("network unreachable"))
        listener.on_abort(Exception("generic error"))


# ===========================================================================
# MastodonDatasource
# ===========================================================================


class TestMastodonDatasource:
    """Tests for MastodonDatasource."""

    def test_source_id(self):
        from talkbout.mastodon.stream import MastodonDatasource

        ds = MastodonDatasource("https://wien.rocks", "token")
        assert ds.source_id == "mastodon:wien.rocks"

    def test_source_id_strips_trailing_slash(self):
        from talkbout.mastodon.stream import MastodonDatasource

        ds = MastodonDatasource("https://wien.rocks/", "token")
        assert ds.source_id == "mastodon:wien.rocks"

    def test_is_base_datasource(self):
        from talkbout.mastodon.stream import MastodonDatasource

        ds = MastodonDatasource("https://wien.rocks", "token")
        assert isinstance(ds, BaseDatasource)
