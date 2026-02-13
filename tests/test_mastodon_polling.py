"""Tests for viennatalksbout.mastodon.polling — REST API polling datasource.

Unit tests covering:
- source_id property
- start() delivering valid statuses via on_post
- Filtering (reblogs, sensitive, empty) still applies
- since_id tracking across poll cycles
- HTTP error handling via on_error callback
- stop() terminating the poll thread
- BaseDatasource interface compliance
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.mastodon.polling import MastodonPollingDatasource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status(
    id: str = "100",
    content: str = "<p>Hallo Wien!</p>",
    created_at: str = "2025-06-15T12:00:00Z",
    language: str = "de",
    reblog: object = None,
    sensitive: bool = False,
) -> dict:
    """Create a minimal Mastodon status dict."""
    return {
        "id": id,
        "content": content,
        "created_at": created_at,
        "language": language,
        "reblog": reblog,
        "sensitive": sensitive,
    }


# ===========================================================================
# Interface compliance
# ===========================================================================


class TestPollingDatasourceInterface:
    """Verify MastodonPollingDatasource implements BaseDatasource."""

    def test_is_base_datasource_subclass(self):
        assert issubclass(MastodonPollingDatasource, BaseDatasource)

    def test_instance_is_base_datasource(self):
        ds = MastodonPollingDatasource(instance_url="https://wien.rocks")
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    """Tests for the source_id property."""

    def test_source_id_https(self):
        ds = MastodonPollingDatasource(instance_url="https://wien.rocks")
        assert ds.source_id == "mastodon:wien.rocks"

    def test_source_id_strips_trailing_slash(self):
        ds = MastodonPollingDatasource(instance_url="https://wien.rocks/")
        assert ds.source_id == "mastodon:wien.rocks"

    def test_source_id_http(self):
        ds = MastodonPollingDatasource(instance_url="http://localhost:3000")
        assert ds.source_id == "mastodon:localhost:3000"


# ===========================================================================
# start / on_post delivery
# ===========================================================================


class TestStartDeliversPosts:
    """Tests that start() delivers posts for valid statuses."""

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_valid_status_calls_on_post(self, mock_get):
        statuses = [_make_status(id="1")]
        mock_resp = MagicMock()
        mock_resp.json.return_value = statuses
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        on_post = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=0.05,
        )
        ds.start(on_post)
        time.sleep(0.15)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert post.text == "Hallo Wien!"
        assert post.source == "mastodon:wien.rocks"

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_multiple_statuses_delivered_oldest_first(self, mock_get):
        statuses = [
            _make_status(id="3", content="<p>Third</p>"),
            _make_status(id="2", content="<p>Second</p>"),
            _make_status(id="1", content="<p>First</p>"),
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = statuses
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        received: list[Post] = []
        on_post = MagicMock(side_effect=lambda p: received.append(p))

        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=999,  # Only one poll cycle
        )
        ds.start(on_post)
        time.sleep(0.15)
        ds.stop()

        # First call should be oldest (id=1), last should be newest (id=3)
        assert len(received) >= 3
        assert received[0].id == "1"
        assert received[1].id == "2"
        assert received[2].id == "3"


# ===========================================================================
# Filtering
# ===========================================================================


class TestFiltering:
    """Tests that reblogs, sensitive, and empty statuses are filtered out."""

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_reblogs_filtered(self, mock_get):
        statuses = [_make_status(id="1", reblog={"id": "99"})]
        mock_resp = MagicMock()
        mock_resp.json.return_value = statuses
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        on_post = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks", poll_interval=999
        )
        ds.start(on_post)
        time.sleep(0.15)
        ds.stop()

        on_post.assert_not_called()

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_sensitive_filtered(self, mock_get):
        statuses = [_make_status(id="1", sensitive=True)]
        mock_resp = MagicMock()
        mock_resp.json.return_value = statuses
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        on_post = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks", poll_interval=999
        )
        ds.start(on_post)
        time.sleep(0.15)
        ds.stop()

        on_post.assert_not_called()

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_empty_content_filtered(self, mock_get):
        statuses = [_make_status(id="1", content="<p>  </p>")]
        mock_resp = MagicMock()
        mock_resp.json.return_value = statuses
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        on_post = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks", poll_interval=999
        )
        ds.start(on_post)
        time.sleep(0.15)
        ds.stop()

        on_post.assert_not_called()


# ===========================================================================
# since_id tracking
# ===========================================================================


class TestSinceIdTracking:
    """Tests that since_id is updated and sent on subsequent polls."""

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_since_id_used_on_second_poll(self, mock_get):
        first_statuses = [_make_status(id="42")]
        second_statuses = [_make_status(id="43")]

        first_resp = MagicMock()
        first_resp.json.return_value = first_statuses
        first_resp.raise_for_status = MagicMock()

        second_resp = MagicMock()
        second_resp.json.return_value = second_statuses
        second_resp.raise_for_status = MagicMock()

        # Use a function so extra calls beyond the expected ones don't raise StopIteration
        call_count = 0

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_resp
            return second_resp

        mock_get.side_effect = get_side_effect

        on_post = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=0.05,
        )
        ds.start(on_post)
        time.sleep(0.2)
        ds.stop()

        # First call should not have since_id
        first_call_params = mock_get.call_args_list[0][1].get(
            "params", mock_get.call_args_list[0][0][0] if mock_get.call_args_list[0][0] else {}
        )
        first_call_params = mock_get.call_args_list[0].kwargs.get("params", {})
        assert "since_id" not in first_call_params

        # Second call should have since_id=42
        if len(mock_get.call_args_list) >= 2:
            second_call_params = mock_get.call_args_list[1].kwargs.get("params", {})
            assert second_call_params.get("since_id") == "42"


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Tests that HTTP errors are handled gracefully."""

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_http_error_calls_on_error(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("Connection refused")

        on_post = MagicMock()
        on_error = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks", poll_interval=999
        )
        ds.start(on_post, on_error=on_error)
        time.sleep(0.15)
        ds.stop()

        on_post.assert_not_called()
        assert on_error.call_count >= 1
        err = on_error.call_args_list[0][0][0]
        assert isinstance(err, requests.ConnectionError)

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_http_error_continues_polling(self, mock_get):
        """After an error, the next poll cycle should still run."""
        ok_resp = MagicMock()
        ok_resp.json.return_value = [_make_status(id="1")]
        ok_resp.raise_for_status = MagicMock()

        call_count = 0

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise requests.ConnectionError("fail")
            return ok_resp

        mock_get.side_effect = get_side_effect

        on_post = MagicMock()
        on_error = MagicMock()
        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=0.05,
        )
        ds.start(on_post, on_error=on_error)
        time.sleep(0.25)
        ds.stop()

        # on_error should have been called for the first failure
        assert on_error.call_count >= 1
        # on_post should have been called after recovery
        assert on_post.call_count >= 1


# ===========================================================================
# stop()
# ===========================================================================


class TestStop:
    """Tests that stop() terminates the poll thread."""

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_stop_terminates_thread(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=0.05,
        )
        ds.start(MagicMock())
        assert ds._thread is not None
        assert ds._thread.is_alive()

        ds.stop()
        assert ds._thread is None

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_stop_is_idempotent(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=0.05,
        )
        ds.start(MagicMock())
        ds.stop()
        ds.stop()  # Should not raise


# ===========================================================================
# Authorization header
# ===========================================================================


class TestAuthHeader:
    """Tests that the access token is passed as a Bearer header."""

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_access_token_sent_as_bearer(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            access_token="my-token",
            poll_interval=999,
        )
        ds.start(MagicMock())
        time.sleep(0.15)
        ds.stop()

        headers = mock_get.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer my-token"

    @patch("viennatalksbout.mastodon.polling.requests.get")
    def test_no_auth_header_when_no_token(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        ds = MastodonPollingDatasource(
            instance_url="https://wien.rocks",
            poll_interval=999,
        )
        ds.start(MagicMock())
        time.sleep(0.15)
        ds.stop()

        headers = mock_get.call_args.kwargs.get("headers", {})
        assert "Authorization" not in headers
