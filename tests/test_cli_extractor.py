"""Tests for CLITopicExtractor — topic extraction via claude CLI subprocess."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from viennatalksbout.buffer import PostBatch
from viennatalksbout.datasource import Post
from viennatalksbout.extractor import (
    CLITopicExtractor,
    DEFAULT_INITIAL_BACKOFF,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    ExtractedTopic,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_post(id: str = "1", text: str = "Hello Wien!", **overrides) -> Post:
    defaults = {
        "id": id,
        "text": text,
        "created_at": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "language": "de",
        "source": "mastodon:wien.rocks",
    }
    defaults.update(overrides)
    return Post(**defaults)


def _make_batch(posts=None, **overrides) -> PostBatch:
    if posts is None:
        posts = (_make_post(),)
    if not isinstance(posts, tuple):
        posts = tuple(posts)
    now = datetime.now(timezone.utc)
    defaults = {
        "posts": posts,
        "window_start": now,
        "window_end": now,
        "post_count": len(posts),
        "source": "mastodon:wien.rocks",
    }
    defaults.update(overrides)
    return PostBatch(**defaults)


def _cli_result(topics: list[dict], returncode: int = 0) -> subprocess.CompletedProcess:
    """Build a mock subprocess.CompletedProcess with a JSON envelope."""
    inner_json = json.dumps({"topics": topics})
    envelope = json.dumps({"result": inner_json})
    return subprocess.CompletedProcess(
        args=["claude"],
        returncode=returncode,
        stdout=envelope,
        stderr="",
    )


def _cli_error(stderr: str = "error", returncode: int = 1) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["claude"],
        returncode=returncode,
        stdout="",
        stderr=stderr,
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestCLIExtractorInit:
    def test_default_values(self) -> None:
        ext = CLITopicExtractor()
        assert ext.model == DEFAULT_MODEL
        assert ext.max_retries == DEFAULT_MAX_RETRIES

    def test_custom_model(self) -> None:
        ext = CLITopicExtractor(model="claude-sonnet-4-5-20250514")
        assert ext.model == "claude-sonnet-4-5-20250514"

    def test_negative_retries_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CLITopicExtractor(max_retries=-1)

    def test_zero_backoff_rejected(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            CLITopicExtractor(initial_backoff=0)


# ---------------------------------------------------------------------------
# Extraction — happy path
# ---------------------------------------------------------------------------


class TestCLIExtractHappyPath:
    @patch("viennatalksbout.extractor.subprocess.run")
    def test_successful_extraction(self, mock_run: MagicMock) -> None:
        topics_data = [
            {"topic": "Donauinselfest", "score": 0.9, "count": 5},
            {"topic": "U2 Störung", "score": 0.6, "count": 3},
        ]
        mock_run.return_value = _cli_result(topics_data)

        ext = CLITopicExtractor(max_retries=0)
        result = ext.extract(_make_batch())

        assert len(result) == 2
        assert result[0] == ExtractedTopic("Donauinselfest", 0.9, 5)
        assert result[1] == ExtractedTopic("U2 Störung", 0.6, 3)

    @patch("viennatalksbout.extractor.subprocess.run")
    def test_empty_batch_skips_cli(self, mock_run: MagicMock) -> None:
        ext = CLITopicExtractor()
        result = ext.extract(_make_batch(posts=(), post_count=0))
        assert result == []
        mock_run.assert_not_called()

    @patch("viennatalksbout.extractor.subprocess.run")
    def test_no_topics_returns_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _cli_result([])
        ext = CLITopicExtractor(max_retries=0)
        result = ext.extract(_make_batch())
        assert result == []

    @patch("viennatalksbout.extractor.subprocess.run")
    def test_cli_invocation_args(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _cli_result([])
        ext = CLITopicExtractor(model="test-model", max_retries=0)
        ext.extract(_make_batch())

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "claude"
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--model" in cmd
        assert "test-model" in cmd
        assert call_args.kwargs["text"] is True
        assert call_args.kwargs["capture_output"] is True


# ---------------------------------------------------------------------------
# Extraction — error handling and retries
# ---------------------------------------------------------------------------


class TestCLIExtractRetries:
    @patch("viennatalksbout.extractor.time.sleep")
    @patch("viennatalksbout.extractor.subprocess.run")
    def test_retry_on_cli_error(
        self, mock_run: MagicMock, mock_sleep: MagicMock
    ) -> None:
        topics_data = [{"topic": "Wien", "score": 0.5, "count": 1}]
        mock_run.side_effect = [
            _cli_error("timeout"),
            _cli_result(topics_data),
        ]

        ext = CLITopicExtractor(max_retries=1, initial_backoff=1.0)
        result = ext.extract(_make_batch())

        assert len(result) == 1
        assert mock_run.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch("viennatalksbout.extractor.time.sleep")
    @patch("viennatalksbout.extractor.subprocess.run")
    def test_all_retries_exhausted_returns_empty(
        self, mock_run: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_run.return_value = _cli_error("fail")
        ext = CLITopicExtractor(max_retries=2, initial_backoff=0.5)
        result = ext.extract(_make_batch())

        assert result == []
        assert mock_run.call_count == 3  # 1 initial + 2 retries

    @patch("viennatalksbout.extractor.time.sleep")
    @patch("viennatalksbout.extractor.subprocess.run")
    def test_exponential_backoff(
        self, mock_run: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_run.return_value = _cli_error("fail")
        ext = CLITopicExtractor(max_retries=2, initial_backoff=1.0)
        ext.extract(_make_batch())

        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)

    @patch("viennatalksbout.extractor.time.sleep")
    @patch("viennatalksbout.extractor.subprocess.run")
    def test_retry_on_invalid_json(
        self, mock_run: MagicMock, mock_sleep: MagicMock
    ) -> None:
        bad_result = subprocess.CompletedProcess(
            args=["claude"],
            returncode=0,
            stdout="not json at all",
            stderr="",
        )
        good_result = _cli_result(
            [{"topic": "Test", "score": 0.5, "count": 1}]
        )
        mock_run.side_effect = [bad_result, good_result]

        ext = CLITopicExtractor(max_retries=1)
        result = ext.extract(_make_batch())
        assert len(result) == 1

    @patch("viennatalksbout.extractor.subprocess.run")
    def test_timeout_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        ext = CLITopicExtractor(max_retries=0)
        result = ext.extract(_make_batch())
        assert result == []


# ---------------------------------------------------------------------------
# Response parsing — code fence stripping
# ---------------------------------------------------------------------------


class TestCLIResponseParsing:
    @patch("viennatalksbout.extractor.subprocess.run")
    def test_strips_code_fences(self, mock_run: MagicMock) -> None:
        inner = '```json\n{"topics": [{"topic": "Wien", "score": 0.5, "count": 1}]}\n```'
        # Simulate a non-envelope stdout (raw text)
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout=inner, stderr=""
        )
        ext = CLITopicExtractor(max_retries=0)
        result = ext.extract(_make_batch())
        assert len(result) == 1
        assert result[0].topic == "Wien"

    @patch("viennatalksbout.extractor.subprocess.run")
    def test_plain_json_result_field(self, mock_run: MagicMock) -> None:
        """When CLI outputs a JSON envelope with result as a JSON string."""
        inner = json.dumps({"topics": [{"topic": "Prater", "score": 0.8, "count": 2}]})
        envelope = json.dumps({"result": inner})
        mock_run.return_value = subprocess.CompletedProcess(
            args=["claude"], returncode=0, stdout=envelope, stderr=""
        )
        ext = CLITopicExtractor(max_retries=0)
        result = ext.extract(_make_batch())
        assert len(result) == 1
        assert result[0].topic == "Prater"
