"""Topic extraction from post batches using Claude.

Takes a PostBatch from the buffer and uses the Anthropic API to extract
specific trending topics. Uses tool use for reliable structured output.

**Model choice:** Haiku 4.5 by default. At ~10 posts/hour from wien.rocks,
each LLM call processes a small batch of 1-3 posts. Haiku handles this
simple extraction task well at a fraction of Sonnet's cost. The model is
configurable via the ``ANTHROPIC_MODEL`` environment variable.

**Failed batch policy:** When extraction fails after all retries, the batch
is dropped (returns an empty list). This is acceptable for an MVP showing
trending topics — a few missed batches do not significantly affect the
tag cloud. Batches are NOT re-queued or merged into the next window.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from viennatalksbout.buffer import PostBatch

logger = logging.getLogger(__name__)

# Model choice: Haiku for cost efficiency. See module docstring.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 1.0  # seconds

SYSTEM_PROMPT = (
    "You are analyzing posts about Vienna, Austria from multiple sources "
    "(social media, news headlines, press releases). "
    "The posts are primarily in German.\n\n"
    "Extract the specific topics that people are discussing "
    "or that are being reported on. "
    "Return concrete, specific topic terms "
    '(e.g. "Donauinselfest", "U2 Störung", "Wiener Linien") '
    "— NOT broad categories like \"politics\" or \"weather\".\n\n"
    "Rules:\n"
    "- Only extract topics actually discussed in the posts. Do not invent topics.\n"
    "- Each topic should be a short noun phrase (1-4 words).\n"
    "- Score reflects how prominently the topic features across the batch "
    "(0.0 = barely mentioned, 1.0 = dominant topic).\n"
    "- Count is the number of posts that discuss this topic.\n"
    "- If the posts contain no meaningful or extractable topics, return an empty list."
)

# Tool definition for structured output — forces Claude to return
# topics in a validated JSON schema via tool use.
EXTRACT_TOPICS_TOOL: dict[str, Any] = {
    "name": "record_topics",
    "description": (
        "Record the trending topics extracted from the social media posts."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": (
                                "The specific topic term "
                                "(short noun phrase, 1-4 words)"
                            ),
                        },
                        "score": {
                            "type": "number",
                            "description": (
                                "Relevance score from 0.0 "
                                "(barely mentioned) to 1.0 (dominant topic)"
                            ),
                        },
                        "count": {
                            "type": "integer",
                            "description": (
                                "Number of posts discussing this topic"
                            ),
                        },
                    },
                    "required": ["topic", "score", "count"],
                },
            },
        },
        "required": ["topics"],
    },
}


@dataclass(frozen=True)
class ExtractedTopic:
    """A topic extracted from a batch of posts.

    Attributes:
        topic: The specific topic term (e.g. "Donauinselfest").
        score: Relevance score from 0.0 to 1.0.
        count: Number of posts discussing this topic.
    """

    topic: str
    score: float
    count: int


def build_user_message(batch: PostBatch) -> str:
    """Build the user message content from a PostBatch.

    Each post is formatted as a numbered entry with its text content.
    Returns an empty string for an empty batch.
    """
    lines = []
    for i, post in enumerate(batch.posts, 1):
        lines.append(f"[{i}] {post.text}")
    return "\n".join(lines)


def parse_tool_response(tool_input: Any) -> list[ExtractedTopic]:
    """Parse and validate the tool use response from Claude.

    Performs lenient parsing: individual malformed entries are skipped
    (with a warning logged) rather than rejecting the entire response.

    Args:
        tool_input: The ``input`` dict from a ``tool_use`` content block.

    Returns:
        A list of validated ExtractedTopic objects.

    Raises:
        ValueError: If the top-level response structure is invalid
            (not a dict, missing ``topics`` key, or ``topics`` is not a list).
    """
    if not isinstance(tool_input, dict):
        raise ValueError(f"Expected dict, got {type(tool_input).__name__}")

    topics_raw = tool_input.get("topics")
    if topics_raw is None:
        raise ValueError("Missing 'topics' key in tool response")
    if not isinstance(topics_raw, list):
        raise ValueError(
            f"Expected 'topics' to be a list, got {type(topics_raw).__name__}"
        )

    result: list[ExtractedTopic] = []
    for i, entry in enumerate(topics_raw):
        if not isinstance(entry, dict):
            logger.warning("Skipping non-dict topic entry at index %d", i)
            continue

        topic = entry.get("topic")
        score = entry.get("score")
        count = entry.get("count")

        # Validate topic name
        if not isinstance(topic, str) or not topic.strip():
            logger.warning(
                "Skipping topic at index %d: invalid or empty name", i
            )
            continue

        # Coerce and clamp score to [0.0, 1.0]
        try:
            score_val = float(score)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping topic '%s': invalid score %r", topic, score
            )
            continue
        score_val = max(0.0, min(1.0, score_val))

        # Coerce count to non-negative int
        try:
            count_val = int(count)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping topic '%s': invalid count %r", topic, count
            )
            continue
        count_val = max(0, count_val)

        result.append(
            ExtractedTopic(
                topic=topic.strip(),
                score=score_val,
                count=count_val,
            )
        )

    return result


class TopicExtractor:
    """Extracts trending topics from post batches using Claude.

    Uses the Anthropic API with tool use for structured output.
    Retries failed calls with exponential backoff. On persistent failure,
    drops the batch and returns an empty list (see module docstring).

    Args:
        api_key: Anthropic API key.
        model: Claude model ID (default: Haiku 4.5 for cost efficiency).
        max_retries: Maximum retry attempts on failure (0 = no retries).
        initial_backoff: Initial backoff duration in seconds (doubles each retry).
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if max_retries < 0:
            raise ValueError(
                f"max_retries must be non-negative, got {max_retries}"
            )
        if initial_backoff <= 0:
            raise ValueError(
                f"initial_backoff must be positive, got {initial_backoff}"
            )

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff

    @property
    def model(self) -> str:
        """The Claude model ID used for extraction."""
        return self._model

    @property
    def max_retries(self) -> int:
        """Maximum retry attempts on API failure."""
        return self._max_retries

    def extract(self, batch: PostBatch) -> list[ExtractedTopic]:
        """Extract topics from a batch of posts.

        Args:
            batch: A PostBatch from the buffer.

        Returns:
            A list of extracted topics. Returns an empty list if extraction
            fails after all retries, or if the batch contains no meaningful
            topics.
        """
        if batch.post_count == 0:
            logger.debug("Empty batch, skipping extraction")
            return []

        user_message = build_user_message(batch)
        last_exception: Exception | None = None
        backoff = self._initial_backoff

        for attempt in range(1 + self._max_retries):
            try:
                response = self._call_api(user_message)
                topics = self._parse_response(response)
                logger.info(
                    "Extracted %d topics from %d posts (attempt %d)",
                    len(topics),
                    batch.post_count,
                    attempt + 1,
                )
                return topics
            except anthropic.APIError as exc:
                last_exception = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "API error on attempt %d/%d: %s. Retrying in %.1fs...",
                        attempt + 1,
                        1 + self._max_retries,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2
            except Exception as exc:
                last_exception = exc
                if attempt < self._max_retries:
                    logger.warning(
                        "Unexpected error on attempt %d/%d: %s. "
                        "Retrying in %.1fs...",
                        attempt + 1,
                        1 + self._max_retries,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2

        # All retries exhausted — drop the batch
        logger.error(
            "Topic extraction failed after %d attempts for batch "
            "(%d posts, window %s -> %s). Dropping batch. Last error: %s",
            1 + self._max_retries,
            batch.post_count,
            batch.window_start.isoformat(),
            batch.window_end.isoformat(),
            last_exception,
        )
        return []

    def _call_api(self, user_message: str) -> anthropic.types.Message:
        """Make the Claude API call with forced tool use."""
        return self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=[EXTRACT_TOPICS_TOOL],
            tool_choice={"type": "tool", "name": "record_topics"},
            messages=[{"role": "user", "content": user_message}],
        )

    def _parse_response(
        self, response: anthropic.types.Message
    ) -> list[ExtractedTopic]:
        """Parse the API response, extracting topics from the tool use block.

        Raises:
            ValueError: If no ``record_topics`` tool use block is found.
        """
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_topics":
                return parse_tool_response(block.input)

        raise ValueError(
            "No record_topics tool use block in response. "
            f"Got content types: {[b.type for b in response.content]}"
        )
