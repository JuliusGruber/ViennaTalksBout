"""Tests for viennatalksbout.extractor — topic extraction using Claude API."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest

from viennatalksbout.buffer import PostBatch
from viennatalksbout.datasource import Post
from viennatalksbout.extractor import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    EXTRACT_TOPICS_TOOL,
    SYSTEM_PROMPT,
    ExtractedTopic,
    TopicExtractor,
    build_user_message,
    parse_tool_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_post(id: str = "1", text: str = "Hello Wien!", **overrides) -> Post:
    """Create a Post with sensible defaults."""
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
    """Create a PostBatch with sensible defaults."""
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


def _make_tool_use_block(topics: list[dict]) -> MagicMock:
    """Create a mock tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "record_topics"
    block.input = {"topics": topics}
    return block


def _make_text_block(text: str = "...") -> MagicMock:
    """Create a mock text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_response(content_blocks: list) -> MagicMock:
    """Create a mock API response with the given content blocks."""
    response = MagicMock()
    response.content = content_blocks
    return response


def _make_api_error(message: str = "API error") -> anthropic.APIConnectionError:
    """Create an anthropic API error for testing."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(request=request, message=message)


# ===========================================================================
# ExtractedTopic dataclass
# ===========================================================================


class TestExtractedTopic:
    """Tests for the ExtractedTopic frozen dataclass."""

    def test_create_topic(self):
        topic = ExtractedTopic(topic="Donauinselfest", score=0.9, count=5)
        assert topic.topic == "Donauinselfest"
        assert topic.score == 0.9
        assert topic.count == 5

    def test_topic_is_frozen(self):
        topic = ExtractedTopic(topic="Test", score=0.5, count=1)
        with pytest.raises(AttributeError):
            topic.score = 0.8  # type: ignore[misc]

    def test_topic_equality(self):
        a = ExtractedTopic(topic="Test", score=0.5, count=1)
        b = ExtractedTopic(topic="Test", score=0.5, count=1)
        assert a == b

    def test_topic_inequality(self):
        a = ExtractedTopic(topic="A", score=0.5, count=1)
        b = ExtractedTopic(topic="B", score=0.5, count=1)
        assert a != b


# ===========================================================================
# build_user_message
# ===========================================================================


class TestBuildUserMessage:
    """Tests for building the user message from a PostBatch."""

    def test_single_post(self):
        batch = _make_batch([_make_post(text="Hallo Wien!")])
        msg = build_user_message(batch)
        assert msg == "[1] Hallo Wien!"

    def test_multiple_posts(self):
        batch = _make_batch([
            _make_post(id="1", text="First post"),
            _make_post(id="2", text="Second post"),
            _make_post(id="3", text="Third post"),
        ])
        msg = build_user_message(batch)
        lines = msg.strip().split("\n")
        assert len(lines) == 3
        assert lines[0] == "[1] First post"
        assert lines[1] == "[2] Second post"
        assert lines[2] == "[3] Third post"

    def test_german_text_with_umlauts(self):
        batch = _make_batch([
            _make_post(text="Die U2 Störung ist ärgerlich!"),
        ])
        msg = build_user_message(batch)
        assert "U2 Störung" in msg
        assert "ärgerlich" in msg

    def test_empty_batch(self):
        batch = _make_batch(posts=(), post_count=0)
        msg = build_user_message(batch)
        assert msg == ""

    def test_post_numbering_starts_at_one(self):
        batch = _make_batch([_make_post(text="Test")])
        msg = build_user_message(batch)
        assert msg.startswith("[1]")

    def test_multiline_post_text(self):
        batch = _make_batch([_make_post(text="Line one\nLine two")])
        msg = build_user_message(batch)
        assert "[1] Line one\nLine two" == msg


# ===========================================================================
# parse_tool_response
# ===========================================================================


class TestParseToolResponse:
    """Tests for parsing and validating the tool use response."""

    def test_valid_single_topic(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Donauinselfest", "score": 0.9, "count": 5}]
        })
        assert len(topics) == 1
        assert topics[0] == ExtractedTopic("Donauinselfest", 0.9, 5)

    def test_valid_multiple_topics(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "Donauinselfest", "score": 0.9, "count": 5},
                {"topic": "U2 Störung", "score": 0.6, "count": 2},
                {"topic": "Wiener Linien", "score": 0.3, "count": 1},
            ]
        })
        assert len(topics) == 3
        assert topics[0].topic == "Donauinselfest"
        assert topics[1].topic == "U2 Störung"
        assert topics[2].topic == "Wiener Linien"

    def test_empty_topics_list(self):
        topics = parse_tool_response({"topics": []})
        assert topics == []

    def test_score_clamped_above_one(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Over", "score": 1.5, "count": 1}]
        })
        assert topics[0].score == 1.0

    def test_score_clamped_below_zero(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Under", "score": -0.5, "count": 1}]
        })
        assert topics[0].score == 0.0

    def test_negative_count_clamped_to_zero(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Test", "score": 0.5, "count": -3}]
        })
        assert topics[0].count == 0

    def test_skips_entry_with_missing_topic_name(self):
        topics = parse_tool_response({
            "topics": [
                {"score": 0.5, "count": 1},
                {"topic": "Valid", "score": 0.5, "count": 1},
            ]
        })
        assert len(topics) == 1
        assert topics[0].topic == "Valid"

    def test_skips_entry_with_empty_topic_name(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "", "score": 0.5, "count": 1},
            ]
        })
        assert len(topics) == 0

    def test_skips_entry_with_whitespace_only_topic(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "   ", "score": 0.5, "count": 1},
            ]
        })
        assert len(topics) == 0

    def test_skips_entry_with_invalid_score(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "Bad", "score": "not_a_number", "count": 1},
                {"topic": "Good", "score": 0.5, "count": 1},
            ]
        })
        assert len(topics) == 1
        assert topics[0].topic == "Good"

    def test_skips_entry_with_none_score(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Bad", "score": None, "count": 1}]
        })
        assert len(topics) == 0

    def test_skips_entry_with_invalid_count(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "Bad", "score": 0.5, "count": "many"},
                {"topic": "Good", "score": 0.5, "count": 1},
            ]
        })
        assert len(topics) == 1
        assert topics[0].topic == "Good"

    def test_skips_entry_with_none_count(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Bad", "score": 0.5, "count": None}]
        })
        assert len(topics) == 0

    def test_skips_non_dict_entries(self):
        topics = parse_tool_response({
            "topics": [
                "not a dict",
                42,
                {"topic": "Valid", "score": 0.5, "count": 1},
            ]
        })
        assert len(topics) == 1
        assert topics[0].topic == "Valid"

    def test_missing_topics_key_raises(self):
        with pytest.raises(ValueError, match="Missing 'topics' key"):
            parse_tool_response({"other": "data"})

    def test_topics_not_list_raises(self):
        with pytest.raises(ValueError, match="Expected 'topics' to be a list"):
            parse_tool_response({"topics": "not a list"})

    def test_non_dict_input_raises(self):
        with pytest.raises(ValueError, match="Expected dict"):
            parse_tool_response("not a dict")

    def test_topic_name_is_stripped(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "  Donauinselfest  ", "score": 0.5, "count": 1}
            ]
        })
        assert topics[0].topic == "Donauinselfest"

    def test_score_as_int_coerced_to_float(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Test", "score": 1, "count": 1}]
        })
        assert topics[0].score == 1.0
        assert isinstance(topics[0].score, float)

    def test_count_as_float_coerced_to_int(self):
        topics = parse_tool_response({
            "topics": [{"topic": "Test", "score": 0.5, "count": 3.7}]
        })
        assert topics[0].count == 3
        assert isinstance(topics[0].count, int)

    def test_score_at_exact_boundaries(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "Zero", "score": 0.0, "count": 1},
                {"topic": "One", "score": 1.0, "count": 1},
            ]
        })
        assert topics[0].score == 0.0
        assert topics[1].score == 1.0

    def test_mixed_valid_and_invalid_entries(self):
        topics = parse_tool_response({
            "topics": [
                {"topic": "Good1", "score": 0.5, "count": 1},
                {"topic": "", "score": 0.5, "count": 1},       # bad: empty name
                {"topic": "Good2", "score": 0.8, "count": 2},
                {"score": 0.5, "count": 1},                     # bad: no name
                {"topic": "Good3", "score": 0.3, "count": 1},
                "bad entry",                                     # bad: not a dict
            ]
        })
        assert len(topics) == 3
        assert [t.topic for t in topics] == ["Good1", "Good2", "Good3"]


# ===========================================================================
# TopicExtractor — construction
# ===========================================================================


@patch("viennatalksbout.extractor.anthropic.Anthropic")
class TestTopicExtractorConfig:
    """Tests for TopicExtractor constructor and configuration."""

    def test_empty_api_key_raises(self, mock_cls):
        with pytest.raises(ValueError, match="api_key must not be empty"):
            TopicExtractor(api_key="")

    def test_negative_max_retries_raises(self, mock_cls):
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            TopicExtractor(api_key="test-key", max_retries=-1)

    def test_zero_backoff_raises(self, mock_cls):
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            TopicExtractor(api_key="test-key", initial_backoff=0)

    def test_negative_backoff_raises(self, mock_cls):
        with pytest.raises(ValueError, match="initial_backoff must be positive"):
            TopicExtractor(api_key="test-key", initial_backoff=-1.0)

    def test_default_model(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        assert ext.model == DEFAULT_MODEL

    def test_custom_model(self, mock_cls):
        ext = TopicExtractor(api_key="test-key", model="claude-sonnet-4-5-20250929")
        assert ext.model == "claude-sonnet-4-5-20250929"

    def test_default_max_retries(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        assert ext.max_retries == DEFAULT_MAX_RETRIES

    def test_zero_retries_allowed(self, mock_cls):
        ext = TopicExtractor(api_key="test-key", max_retries=0)
        assert ext.max_retries == 0

    def test_creates_anthropic_client(self, mock_cls):
        TopicExtractor(api_key="sk-ant-test-key")
        mock_cls.assert_called_once_with(api_key="sk-ant-test-key")


# ===========================================================================
# TopicExtractor.extract — successful extraction
# ===========================================================================


@patch("viennatalksbout.extractor.anthropic.Anthropic")
class TestTopicExtractorExtract:
    """Tests for the extract method — happy path."""

    def test_successful_extraction(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        tool_block = _make_tool_use_block([
            {"topic": "Donauinselfest", "score": 0.9, "count": 3},
            {"topic": "U2 Störung", "score": 0.6, "count": 2},
        ])
        mock_client.messages.create.return_value = _make_response([tool_block])

        ext = TopicExtractor(api_key="test-key")
        batch = _make_batch([
            _make_post(id="1", text="Donauinselfest ist toll!"),
            _make_post(id="2", text="U2 Störung nervt."),
            _make_post(id="3", text="Donauinselfest heute Abend"),
        ])
        topics = ext.extract(batch)

        assert len(topics) == 2
        assert topics[0] == ExtractedTopic("Donauinselfest", 0.9, 3)
        assert topics[1] == ExtractedTopic("U2 Störung", 0.6, 2)

    def test_empty_batch_returns_empty_list(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        ext = TopicExtractor(api_key="test-key")
        batch = _make_batch(posts=(), post_count=0)
        topics = ext.extract(batch)

        assert topics == []
        mock_client.messages.create.assert_not_called()

    def test_no_meaningful_topics_returns_empty(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        tool_block = _make_tool_use_block([])
        mock_client.messages.create.return_value = _make_response([tool_block])

        ext = TopicExtractor(api_key="test-key")
        batch = _make_batch([_make_post(text="lol")])
        topics = ext.extract(batch)

        assert topics == []

    def test_api_called_with_correct_parameters(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        tool_block = _make_tool_use_block([])
        mock_client.messages.create.return_value = _make_response([tool_block])

        ext = TopicExtractor(api_key="test-key", model="claude-haiku-4-5-20251001")
        batch = _make_batch([_make_post(text="Test post")])
        ext.extract(batch)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["max_tokens"] == 1024
        assert call_kwargs["system"] == SYSTEM_PROMPT
        assert call_kwargs["tools"] == [EXTRACT_TOPICS_TOOL]
        assert call_kwargs["tool_choice"] == {
            "type": "tool",
            "name": "record_topics",
        }

    def test_user_message_contains_post_text(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        tool_block = _make_tool_use_block([])
        mock_client.messages.create.return_value = _make_response([tool_block])

        ext = TopicExtractor(api_key="test-key")
        batch = _make_batch([
            _make_post(id="1", text="Grüße aus Wien!"),
            _make_post(id="2", text="Heute regnet es."),
        ])
        ext.extract(batch)

        call_kwargs = mock_client.messages.create.call_args[1]
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "Grüße aus Wien!" in messages[0]["content"]
        assert "Heute regnet es." in messages[0]["content"]

    def test_response_with_text_and_tool_blocks(self, mock_cls):
        """Response may contain both text and tool_use blocks."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        text_block = _make_text_block("Analyzing posts...")
        tool_block = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        mock_client.messages.create.return_value = _make_response(
            [text_block, tool_block]
        )

        ext = TopicExtractor(api_key="test-key")
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert len(topics) == 1
        assert topics[0].topic == "Test"


# ===========================================================================
# TopicExtractor.extract — retry logic
# ===========================================================================


@patch("viennatalksbout.extractor.time.sleep")
@patch("viennatalksbout.extractor.anthropic.Anthropic")
class TestTopicExtractorRetry:
    """Tests for retry behavior on API errors."""

    def test_retries_on_api_connection_error(self, mock_cls, mock_sleep):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        error = _make_api_error("Connection failed")
        tool_block = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        mock_client.messages.create.side_effect = [
            error,
            _make_response([tool_block]),
        ]

        ext = TopicExtractor(
            api_key="test-key", max_retries=2, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert len(topics) == 1
        assert mock_client.messages.create.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    def test_exponential_backoff(self, mock_cls, mock_sleep):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        error = _make_api_error("Server error")
        tool_block = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        mock_client.messages.create.side_effect = [
            error,
            error,
            _make_response([tool_block]),
        ]

        ext = TopicExtractor(
            api_key="test-key", max_retries=3, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        ext.extract(batch)

        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    def test_drops_batch_after_max_retries_exhausted(self, mock_cls, mock_sleep):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        error = _make_api_error("Persistent failure")
        mock_client.messages.create.side_effect = error

        ext = TopicExtractor(
            api_key="test-key", max_retries=2, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert topics == []
        # 1 initial + 2 retries = 3 calls
        assert mock_client.messages.create.call_count == 3

    def test_zero_retries_no_retry_on_failure(self, mock_cls, mock_sleep):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        error = _make_api_error("Fail once")
        mock_client.messages.create.side_effect = error

        ext = TopicExtractor(
            api_key="test-key", max_retries=0, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert topics == []
        assert mock_client.messages.create.call_count == 1
        mock_sleep.assert_not_called()

    def test_retries_on_unexpected_exception(self, mock_cls, mock_sleep):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        tool_block = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        mock_client.messages.create.side_effect = [
            RuntimeError("Unexpected!"),
            _make_response([tool_block]),
        ]

        ext = TopicExtractor(
            api_key="test-key", max_retries=1, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert len(topics) == 1
        assert mock_client.messages.create.call_count == 2

    def test_retries_on_missing_tool_block(self, mock_cls, mock_sleep):
        """If response has no tool_use block, retry (ValueError from _parse_response)."""
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        text_only = _make_response([_make_text_block("No tool call")])
        tool_block = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        mock_client.messages.create.side_effect = [
            text_only,
            _make_response([tool_block]),
        ]

        ext = TopicExtractor(
            api_key="test-key", max_retries=1, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert len(topics) == 1
        assert mock_client.messages.create.call_count == 2

    def test_drops_batch_when_all_retries_fail_with_value_error(
        self, mock_cls, mock_sleep
    ):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        # Response always missing tool block
        text_only = _make_response([_make_text_block("No tool call")])
        mock_client.messages.create.return_value = text_only

        ext = TopicExtractor(
            api_key="test-key", max_retries=1, initial_backoff=1.0
        )
        batch = _make_batch([_make_post()])
        topics = ext.extract(batch)

        assert topics == []
        assert mock_client.messages.create.call_count == 2


# ===========================================================================
# TopicExtractor._parse_response
# ===========================================================================


@patch("viennatalksbout.extractor.anthropic.Anthropic")
class TestTopicExtractorParseResponse:
    """Tests for the _parse_response method."""

    def test_extracts_from_tool_use_block(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        tool_block = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        response = _make_response([tool_block])
        topics = ext._parse_response(response)
        assert len(topics) == 1

    def test_skips_text_blocks_finds_tool_block(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        text = _make_text_block("Thinking...")
        tool = _make_tool_use_block([
            {"topic": "Test", "score": 0.5, "count": 1},
        ])
        response = _make_response([text, tool])
        topics = ext._parse_response(response)
        assert len(topics) == 1

    def test_raises_when_no_tool_use_block(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        response = _make_response([_make_text_block("No tool call")])
        with pytest.raises(ValueError, match="No record_topics tool use block"):
            ext._parse_response(response)

    def test_raises_when_wrong_tool_name(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        block = MagicMock()
        block.type = "tool_use"
        block.name = "wrong_tool"
        block.input = {"topics": []}
        response = _make_response([block])
        with pytest.raises(ValueError, match="No record_topics tool use block"):
            ext._parse_response(response)

    def test_empty_content_raises(self, mock_cls):
        ext = TopicExtractor(api_key="test-key")
        response = _make_response([])
        with pytest.raises(ValueError, match="No record_topics tool use block"):
            ext._parse_response(response)


# ===========================================================================
# Prompt and tool definition constants
# ===========================================================================


class TestConstants:
    """Tests for module-level constants and prompt content."""

    def test_system_prompt_mentions_vienna(self):
        assert "Vienna" in SYSTEM_PROMPT

    def test_system_prompt_mentions_german(self):
        assert "German" in SYSTEM_PROMPT

    def test_system_prompt_mentions_specific_topics(self):
        assert "Donauinselfest" in SYSTEM_PROMPT

    def test_system_prompt_warns_against_broad_categories(self):
        assert "politics" in SYSTEM_PROMPT
        assert "weather" in SYSTEM_PROMPT

    def test_tool_has_required_fields(self):
        schema = EXTRACT_TOPICS_TOOL["input_schema"]
        assert "topics" in schema["required"]
        item_props = schema["properties"]["topics"]["items"]["properties"]
        assert "topic" in item_props
        assert "score" in item_props
        assert "count" in item_props

    def test_tool_name(self):
        assert EXTRACT_TOPICS_TOOL["name"] == "record_topics"

    def test_default_model_is_haiku(self):
        assert "haiku" in DEFAULT_MODEL
