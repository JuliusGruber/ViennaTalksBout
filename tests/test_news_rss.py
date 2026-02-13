"""Tests for viennatalksbout.news.rss — RSS feed polling datasource.

Mirrors the structure of test_mastodon_polling.py.
"""

from __future__ import annotations

import time
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from viennatalksbout.config import FeedConfig
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.news.rss import RssDatasource, strip_html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FEED_ORF = FeedConfig(url="https://rss.orf.at/wien.xml", name="orf-wien")
FEED_OTS = FeedConfig(url="https://www.ots.at/rss/index", name="ots")


def _make_entry(
    title="Test headline",
    summary="<p>Test summary</p>",
    link="https://example.com/1",
    entry_id=None,
    published_parsed=None,
    language=None,
):
    """Create a mock feedparser entry."""
    entry = {
        "title": title,
        "summary": summary,
        "link": link,
        "id": entry_id or link,
    }
    if published_parsed is not None:
        entry["published_parsed"] = published_parsed
    if language is not None:
        entry["language"] = language
    # Make it behave like feedparser FeedParserDict (supports .get())
    return type("Entry", (), {"get": lambda self, k, d=None: entry.get(k, d), **entry})()


def _make_parsed_feed(entries):
    """Create a mock feedparser result."""
    result = MagicMock()
    result.entries = entries
    return result


def _make_response(content=b"<rss/>", status_code=200, headers=None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    return resp


# ===========================================================================
# Interface
# ===========================================================================


class TestRssDatasourceInterface:
    """Test that RssDatasource satisfies BaseDatasource."""

    def test_is_subclass(self):
        assert issubclass(RssDatasource, BaseDatasource)

    def test_instance(self):
        ds = RssDatasource(feeds=[FEED_ORF])
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    def test_returns_news_rss(self):
        ds = RssDatasource(feeds=[FEED_ORF])
        assert ds.source_id == "news:rss"


# ===========================================================================
# _entry_to_post
# ===========================================================================


class TestEntryToPost:
    """Tests for feed entry → Post conversion."""

    def _ds(self):
        return RssDatasource(feeds=[FEED_ORF])

    def test_title_and_summary(self):
        entry = _make_entry(title="Headline", summary="<p>Body text</p>")
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.text == "Headline. Body text"

    def test_title_only(self):
        entry = _make_entry(title="Headline only", summary="")
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.text == "Headline only"

    def test_html_stripping(self):
        entry = _make_entry(
            title="Title",
            summary="<b>Bold</b> and <a href='#'>link</a>",
        )
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert "<" not in post.text
        assert "Bold" in post.text

    def test_date_parsing(self):
        # time.struct_time for 2025-06-15 12:00:00 UTC
        import time as _time
        parsed_time = _time.strptime("2025-06-15 12:00:00", "%Y-%m-%d %H:%M:%S")
        entry = _make_entry(published_parsed=parsed_time)
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.created_at.year == 2025
        assert post.created_at.month == 6

    def test_missing_date_falls_back_to_now(self):
        entry = _make_entry(published_parsed=None)
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        # Should be approximately now
        assert (datetime.now(timezone.utc) - post.created_at).total_seconds() < 5

    def test_empty_text_returns_none(self):
        entry = _make_entry(title="", summary="")
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is None

    def test_language_from_entry(self):
        entry = _make_entry(language="en")
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.language == "en"

    def test_language_fallback_to_feed(self):
        entry = _make_entry(language=None)
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.language == "de"

    def test_id_format(self):
        entry = _make_entry(entry_id="unique-123", link="https://example.com/1")
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.id == "rss:orf-wien:unique-123"

    def test_source_format(self):
        entry = _make_entry()
        post = self._ds()._entry_to_post(entry, FEED_ORF)
        assert post is not None
        assert post.source == "news:orf-wien"


# ===========================================================================
# start delivers posts
# ===========================================================================


class TestStartDeliversPosts:
    """Test that start() polls feeds and calls on_post."""

    @patch("viennatalksbout.news.rss.requests.get")
    @patch("viennatalksbout.news.rss.feedparser.parse")
    def test_delivers_posts(self, mock_parse, mock_get):
        entry = _make_entry(title="News", summary="Details")
        mock_get.return_value = _make_response()
        mock_parse.return_value = _make_parsed_feed([entry])

        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args[0][0]
        assert isinstance(post, Post)
        assert "News" in post.text


# ===========================================================================
# Deduplication
# ===========================================================================


class TestDeduplication:
    """Test in-memory deduplication across polls."""

    @patch("viennatalksbout.news.rss.requests.get")
    @patch("viennatalksbout.news.rss.feedparser.parse")
    def test_same_entries_not_re_emitted(self, mock_parse, mock_get):
        entry = _make_entry(title="Same", entry_id="id-1")
        mock_get.return_value = _make_response()
        mock_parse.return_value = _make_parsed_feed([entry])

        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()

        # First poll
        ds._poll_feed(FEED_ORF, on_post)
        assert on_post.call_count == 1

        # Second poll with same entries
        ds._poll_feed(FEED_ORF, on_post)
        assert on_post.call_count == 1  # Still 1 — duplicate suppressed

    @patch("viennatalksbout.news.rss.requests.get")
    @patch("viennatalksbout.news.rss.feedparser.parse")
    def test_new_entries_emitted(self, mock_parse, mock_get):
        entry1 = _make_entry(title="First", entry_id="id-1")
        entry2 = _make_entry(title="Second", entry_id="id-2")

        mock_get.return_value = _make_response()

        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()

        # First poll
        mock_parse.return_value = _make_parsed_feed([entry1])
        ds._poll_feed(FEED_ORF, on_post)
        assert on_post.call_count == 1

        # Second poll with a new entry
        mock_parse.return_value = _make_parsed_feed([entry1, entry2])
        ds._poll_feed(FEED_ORF, on_post)
        assert on_post.call_count == 2


# ===========================================================================
# Conditional requests
# ===========================================================================


class TestConditionalRequests:
    """Test ETag/If-Modified-Since handling."""

    @patch("viennatalksbout.news.rss.requests.get")
    @patch("viennatalksbout.news.rss.feedparser.parse")
    def test_etag_sent_on_subsequent_request(self, mock_parse, mock_get):
        entry = _make_entry(title="News", entry_id="id-1")
        mock_get.return_value = _make_response(
            headers={"ETag": '"abc123"', "Last-Modified": "Sat, 01 Jan 2025 00:00:00 GMT"}
        )
        mock_parse.return_value = _make_parsed_feed([entry])

        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()

        ds._poll_feed(FEED_ORF, on_post)

        # Second call should include conditional headers
        mock_get.return_value = _make_response(status_code=304)
        ds._poll_feed(FEED_ORF, on_post)

        second_call_headers = mock_get.call_args_list[1][1]["headers"]
        assert second_call_headers.get("If-None-Match") == '"abc123"'
        assert "If-Modified-Since" in second_call_headers

    @patch("viennatalksbout.news.rss.requests.get")
    def test_304_skips_parsing(self, mock_get):
        mock_get.return_value = _make_response(status_code=304)

        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()

        ds._poll_feed(FEED_ORF, on_post)
        assert on_post.call_count == 0


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Test error resilience."""

    @patch("viennatalksbout.news.rss.requests.get")
    def test_network_error_calls_on_error(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")

        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1

    @patch("viennatalksbout.news.rss.requests.get")
    @patch("viennatalksbout.news.rss.feedparser.parse")
    def test_error_on_one_feed_continues_to_next(self, mock_parse, mock_get):
        """If the first feed errors, the second should still be polled."""
        entry = _make_entry(title="From OTS", entry_id="ots-1")

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Feed 1 down")
            return _make_response()

        mock_get.side_effect = side_effect
        mock_parse.return_value = _make_parsed_feed([entry])

        ds = RssDatasource(feeds=[FEED_ORF, FEED_OTS], poll_interval=9999)
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        # on_error should be called for the first feed
        assert on_error.call_count >= 1
        # on_post should be called for the second feed
        assert on_post.call_count >= 1


# ===========================================================================
# Stop
# ===========================================================================


class TestStop:
    """Test stop behavior."""

    def test_thread_terminates(self):
        ds = RssDatasource(feeds=[FEED_ORF], poll_interval=9999)
        on_post = MagicMock()

        with patch("viennatalksbout.news.rss.requests.get") as mock_get:
            mock_get.return_value = _make_response(status_code=304)
            ds.start(on_post)
            time.sleep(0.1)
            ds.stop()

        assert ds._thread is None

    def test_stop_idempotent(self):
        ds = RssDatasource(feeds=[FEED_ORF])
        ds.stop()  # Should not raise even without start
        ds.stop()


# ===========================================================================
# Multiple feeds
# ===========================================================================


class TestMultipleFeeds:
    """Test that all feeds are polled with correct source per feed."""

    @patch("viennatalksbout.news.rss.requests.get")
    @patch("viennatalksbout.news.rss.feedparser.parse")
    def test_all_feeds_polled(self, mock_parse, mock_get):
        entry1 = _make_entry(title="ORF News", entry_id="orf-1")
        entry2 = _make_entry(title="OTS News", entry_id="ots-1")

        mock_get.return_value = _make_response()

        # Return different entries per call
        mock_parse.side_effect = [
            _make_parsed_feed([entry1]),
            _make_parsed_feed([entry2]),
        ]

        ds = RssDatasource(feeds=[FEED_ORF, FEED_OTS], poll_interval=9999)
        on_post = MagicMock()

        ds.start(on_post)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 2
        sources = {call[0][0].source for call in on_post.call_args_list}
        assert "news:orf-wien" in sources
        assert "news:ots" in sources


# ===========================================================================
# strip_html
# ===========================================================================


class TestStripHtml:
    def test_strips_tags(self):
        assert strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_empty(self):
        assert strip_html("") == ""

    def test_plain_text_unchanged(self):
        assert strip_html("plain text") == "plain text"


# ===========================================================================
# Integration — real ORF feed
# ===========================================================================


@pytest.mark.integration
class TestRealOrfFeed:
    """Integration test: fetch and parse a real ORF RSS feed."""

    def test_orf_wien_parseable(self):
        import feedparser
        import requests

        resp = requests.get(
            "https://rss.orf.at/wien.xml",
            headers={"User-Agent": "ViennaTalksBout/1.0 (test)"},
            timeout=15,
        )
        assert resp.status_code == 200

        parsed = feedparser.parse(resp.content)
        assert len(parsed.entries) > 0

        # Entries should have titles
        for entry in parsed.entries[:3]:
            assert entry.get("title"), "ORF entry missing title"
