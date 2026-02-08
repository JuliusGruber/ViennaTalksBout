"""End-to-end tests for the Mastodon stream client with mocked SSE stream.

These tests simulate the full flow: Mastodon.py delivers status dicts to the
listener, which validates, filters, strips HTML, and emits Post objects via
the callback — exactly as it would in production, but without a real SSE
connection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from talkbout.datasource import Post
from talkbout.mastodon.stream import (
    MastodonDatasource,
    TalkBoutStreamListener,
)


# ---------------------------------------------------------------------------
# Realistic sample statuses from wien.rocks
# ---------------------------------------------------------------------------

SAMPLE_STATUSES = [
    {
        "id": "111000001",
        "content": "<p>Guten Morgen Wien! Die Sonne scheint endlich ☀️</p>",
        "created_at": datetime(2025, 6, 15, 7, 30, 0, tzinfo=timezone.utc),
        "language": "de",
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "1", "username": "wiener1"},
    },
    {
        "id": "111000002",
        "content": (
            '<p>Massive Störung auf der <a href="https://wien.rocks/tags/u2">#U2</a> '
            "Linie — bitte Ersatzverkehr nutzen!</p>"
        ),
        "created_at": "2025-06-15T08:15:00Z",
        "language": "de",
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "2", "username": "transit_alert"},
    },
    {
        "id": "111000003",
        "content": "<p>New exhibition at Belvedere is amazing 🎨</p>",
        "created_at": datetime(2025, 6, 15, 9, 0, 0, tzinfo=timezone.utc),
        "language": "en",
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "3", "username": "artlover"},
    },
    # This is a reblog — should be filtered out
    {
        "id": "111000004",
        "content": "<p>Reblogged content</p>",
        "created_at": datetime(2025, 6, 15, 9, 30, 0, tzinfo=timezone.utc),
        "language": "de",
        "reblog": {"id": "999", "content": "<p>Original post</p>"},
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "4", "username": "reblogger"},
    },
    # This is a sensitive post — should be filtered out
    {
        "id": "111000005",
        "content": "<p>Something sensitive here</p>",
        "created_at": datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
        "language": "de",
        "reblog": None,
        "sensitive": True,
        "spoiler_text": "CW: sensitive content",
        "visibility": "public",
        "account": {"id": "5", "username": "cautious_poster"},
    },
    {
        "id": "111000006",
        "content": "<p>Donauinselfest Lineup ist raus! 🎵 Wer kommt mit?</p>",
        "created_at": datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
        "language": "de",
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "6", "username": "musikfan"},
    },
    # Empty content post — should be filtered out
    {
        "id": "111000007",
        "content": "<p></p>",
        "created_at": datetime(2025, 6, 15, 11, 30, 0, tzinfo=timezone.utc),
        "language": "de",
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "7", "username": "empty_poster"},
    },
    # Post with null language — should still be processed
    {
        "id": "111000008",
        "content": "<p>🌭🌭🌭</p>",
        "created_at": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "language": None,
        "reblog": None,
        "sensitive": False,
        "spoiler_text": "",
        "visibility": "public",
        "account": {"id": "8", "username": "emoji_user"},
    },
]


class TestMockStreamEndToEnd:
    """Simulate Mastodon.py delivering statuses to our listener."""

    def test_full_stream_of_sample_statuses(self):
        """Feed all sample statuses through the listener and verify output."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        for status in SAMPLE_STATUSES:
            listener.on_update(status)

        # 8 total statuses: 3 should be filtered (reblog, sensitive, empty)
        assert len(received) == 5

        # Check IDs of posts that passed through
        ids = [p.id for p in received]
        assert "111000001" in ids  # normal German post
        assert "111000002" in ids  # transit alert
        assert "111000003" in ids  # English post
        assert "111000006" in ids  # festival post
        assert "111000008" in ids  # emoji post with null language

        # Filtered out
        assert "111000004" not in ids  # reblog
        assert "111000005" not in ids  # sensitive
        assert "111000007" not in ids  # empty content

    def test_html_stripped_in_full_pipeline(self):
        """Verify HTML is properly stripped through the full pipeline."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        for status in SAMPLE_STATUSES:
            listener.on_update(status)

        # No post should contain HTML tags
        for post in received:
            assert "<" not in post.text, f"Post {post.id} still has HTML: {post.text}"
            assert ">" not in post.text, f"Post {post.id} still has HTML: {post.text}"

    def test_hashtags_preserved_as_text(self):
        """Hashtag links should become plain text like '#U2'."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        # Feed the transit alert status (has a #U2 hashtag link)
        listener.on_update(SAMPLE_STATUSES[1])

        assert len(received) == 1
        assert "#U2" in received[0].text

    def test_source_consistent_across_all_posts(self):
        """All posts from one listener should have the same source."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        for status in SAMPLE_STATUSES:
            listener.on_update(status)

        for post in received:
            assert post.source == "mastodon:wien.rocks"

    def test_null_language_handled(self):
        """Posts with null language should come through with language=None."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        listener.on_update(SAMPLE_STATUSES[7])  # null language emoji post

        assert len(received) == 1
        assert received[0].language is None

    def test_iso_string_timestamps_parsed(self):
        """ISO 8601 string timestamps should be parsed correctly."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        # Feed the transit alert (has string timestamp)
        listener.on_update(SAMPLE_STATUSES[1])

        assert len(received) == 1
        assert received[0].created_at == datetime(
            2025, 6, 15, 8, 15, 0, tzinfo=timezone.utc
        )

    def test_datetime_timestamps_preserved(self):
        """datetime objects from Mastodon.py should pass through unchanged."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        listener.on_update(SAMPLE_STATUSES[0])

        assert len(received) == 1
        assert received[0].created_at == datetime(
            2025, 6, 15, 7, 30, 0, tzinfo=timezone.utc
        )

    def test_stream_with_interleaved_invalid_statuses(self):
        """The stream should handle a mix of valid, invalid, and filtered statuses."""
        received: list[Post] = []
        listener = TalkBoutStreamListener(
            on_post=received.append,
            source="mastodon:wien.rocks",
        )

        # Valid
        listener.on_update(SAMPLE_STATUSES[0])
        # Invalid — not a dict
        listener.on_update("garbage")
        # Invalid — missing id
        listener.on_update({"content": "<p>no id</p>", "created_at": "2025-01-01T00:00:00Z"})
        # Valid
        listener.on_update(SAMPLE_STATUSES[2])
        # Filtered — reblog
        listener.on_update(SAMPLE_STATUSES[3])
        # Invalid — None
        listener.on_update(None)
        # Valid
        listener.on_update(SAMPLE_STATUSES[5])

        assert len(received) == 3
        assert [p.id for p in received] == ["111000001", "111000003", "111000006"]

    def test_callback_exception_does_not_crash_listener(self):
        """If the callback raises, it should propagate (not be silently swallowed)."""
        def exploding_callback(post: Post) -> None:
            raise RuntimeError("callback exploded")

        listener = TalkBoutStreamListener(
            on_post=exploding_callback,
            source="mastodon:wien.rocks",
        )

        # The exception should propagate — we don't swallow callback errors
        with pytest.raises(RuntimeError, match="callback exploded"):
            listener.on_update(SAMPLE_STATUSES[0])


class TestMastodonDatasourceStartStop:
    """Tests for MastodonDatasource.start() and stop() with mocked Mastodon.py."""

    @patch("talkbout.mastodon.stream.Mastodon")
    def test_start_creates_stream(self, MockMastodon: MagicMock):
        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_client.stream_public.return_value = mock_handle
        MockMastodon.return_value = mock_client

        ds = MastodonDatasource("https://wien.rocks", "test_token")
        ds.start(on_post=MagicMock())

        MockMastodon.assert_called_once_with(
            access_token="test_token",
            api_base_url="https://wien.rocks",
        )
        mock_client.stream_public.assert_called_once()
        call_kwargs = mock_client.stream_public.call_args
        assert call_kwargs[1]["local"] is True
        assert call_kwargs[1]["run_async"] is True
        assert call_kwargs[1]["reconnect_async"] is True

    @patch("talkbout.mastodon.stream.Mastodon")
    def test_stop_closes_handle(self, MockMastodon: MagicMock):
        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_client.stream_public.return_value = mock_handle
        MockMastodon.return_value = mock_client

        ds = MastodonDatasource("https://wien.rocks", "test_token")
        ds.start(on_post=MagicMock())
        ds.stop()

        mock_handle.close.assert_called_once()

    @patch("talkbout.mastodon.stream.Mastodon")
    def test_stop_without_start_is_safe(self, MockMastodon: MagicMock):
        ds = MastodonDatasource("https://wien.rocks", "test_token")
        ds.stop()  # Should not raise

    @patch("talkbout.mastodon.stream.Mastodon")
    def test_double_stop_is_safe(self, MockMastodon: MagicMock):
        mock_client = MagicMock()
        mock_handle = MagicMock()
        mock_client.stream_public.return_value = mock_handle
        MockMastodon.return_value = mock_client

        ds = MastodonDatasource("https://wien.rocks", "test_token")
        ds.start(on_post=MagicMock())
        ds.stop()
        ds.stop()  # Should not raise

        mock_handle.close.assert_called_once()

    @patch("talkbout.mastodon.stream.Mastodon")
    def test_stream_delivers_posts_through_listener(self, MockMastodon: MagicMock):
        """Simulate Mastodon.py calling the listener from the stream."""
        captured_listener = None

        def fake_stream_public(listener, **kwargs):
            nonlocal captured_listener
            captured_listener = listener
            return MagicMock()

        mock_client = MagicMock()
        mock_client.stream_public.side_effect = fake_stream_public
        MockMastodon.return_value = mock_client

        received: list[Post] = []
        ds = MastodonDatasource("https://wien.rocks", "test_token")
        ds.start(on_post=received.append)

        # Simulate the stream delivering statuses
        assert captured_listener is not None
        captured_listener.on_update({
            "id": "42",
            "content": "<p>Hallo Wien!</p>",
            "created_at": "2025-06-15T12:00:00Z",
            "language": "de",
            "reblog": None,
            "sensitive": False,
        })

        assert len(received) == 1
        assert received[0].id == "42"
        assert received[0].text == "Hallo Wien!"
        assert received[0].source == "mastodon:wien.rocks"
