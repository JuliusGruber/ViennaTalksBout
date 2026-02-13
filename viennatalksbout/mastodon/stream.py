"""Mastodon streaming client for ViennaTalksBout.

Connects to a Mastodon instance's public:local SSE stream, validates and
filters incoming statuses, strips HTML to plain text, and emits normalized
Post objects via callback.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable

from bs4 import BeautifulSoup
from mastodon import Mastodon, StreamListener

from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

def strip_html(html: str) -> str:
    """Strip HTML tags from Mastodon post content and return plain text.

    Uses Python's built-in html.parser via BeautifulSoup (no extra
    dependency needed). Paragraph breaks and <br> tags become spaces.

    Args:
        html: Raw HTML string from a Mastodon status ``content`` field.

    Returns:
        Plain text with tags removed and whitespace normalized.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    # Collapse runs of whitespace (caused by nested inline tags) into single spaces
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def validate_status(status: Any) -> dict[str, Any] | None:
    """Validate that a Mastodon status has the required fields.

    Returns the status dict if valid, or ``None`` if it should be dropped.
    Logs a warning for each invalid status explaining what was wrong.
    """
    if not isinstance(status, dict):
        logger.warning("Status is not a dict, got %s", type(status).__name__)
        return None

    status_id = status.get("id")

    if not status_id:
        logger.warning("Status missing required 'id' field")
        return None

    if "content" not in status or status["content"] is None:
        logger.warning("Status %s: missing or null 'content' field", status_id)
        return None

    if "created_at" not in status or status["created_at"] is None:
        logger.warning("Status %s: missing or null 'created_at' field", status_id)
        return None

    return status


# ---------------------------------------------------------------------------
# Post filtering
# ---------------------------------------------------------------------------

def filter_status(status: dict[str, Any]) -> bool:
    """Decide whether a validated status should be kept.

    Filters out:
    - **Reblogs** — ``status['reblog']`` is not None.
    - **Sensitive posts** — ``status['sensitive']`` is True.
      Design decision: skip sensitive/NSFW content so it never reaches the
      tag cloud. This is a definitive choice per plan review item 6.
    - **Empty posts** — content is empty after HTML stripping.

    Returns:
        True if the post should be processed, False if it should be skipped.
    """
    if status.get("reblog") is not None:
        return False

    if status.get("sensitive", False):
        return False

    content = status.get("content", "")
    if not strip_html(content):
        return False

    return True


# ---------------------------------------------------------------------------
# Status → Post conversion
# ---------------------------------------------------------------------------

def parse_status(status: dict[str, Any], source: str) -> Post:
    """Convert a validated, filtered Mastodon status into a normalized Post.

    Handles various ``created_at`` formats: ``datetime`` objects (from
    Mastodon.py) and ISO 8601 strings (from raw JSON).

    Args:
        status: A validated Mastodon status dict.
        source: Datasource identifier (e.g. ``"mastodon:wien.rocks"``).

    Returns:
        A Post with HTML stripped and fields normalized.
    """
    created_at = status["created_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    elif not isinstance(created_at, datetime):
        logger.warning(
            "Status %s: unexpected created_at type %s, using current time",
            status["id"],
            type(created_at).__name__,
        )
        created_at = datetime.now(timezone.utc)

    language = status.get("language")
    if language is not None:
        language = str(language).strip() or None

    return Post(
        id=str(status["id"]),
        text=strip_html(status["content"]),
        created_at=created_at,
        language=language,
        source=source,
    )


# ---------------------------------------------------------------------------
# Stream listener
# ---------------------------------------------------------------------------

class ViennaTalksBoutStreamListener(StreamListener):
    """Mastodon StreamListener that validates, filters, and emits Posts.

    Wired into Mastodon.py's SSE streaming. Each incoming status goes
    through validation → filtering → parsing → callback.
    """

    def __init__(
        self,
        on_post: Callable[[Post], None],
        source: str,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_post = on_post
        self._source = source
        self._on_error = on_error

    def on_update(self, status: Any) -> None:
        """Called by Mastodon.py for each new status on the stream."""
        validated = validate_status(status)
        if validated is None:
            return

        if not filter_status(validated):
            return

        post = parse_status(validated, self._source)
        logger.info("Post received via stream: id=%s lang=%s source=%s text=%s", post.id, post.language, post.source, post.text[:120])
        self._on_post(post)

    def on_abort(self, err: Exception) -> None:
        """Called by Mastodon.py when the stream connection is lost."""
        logger.error("Mastodon stream aborted: %s", err)
        if self._on_error is not None:
            self._on_error(err)


# ---------------------------------------------------------------------------
# Datasource implementation
# ---------------------------------------------------------------------------

class MastodonDatasource(BaseDatasource):
    """Streams posts from a Mastodon instance's public:local timeline.

    Uses Mastodon.py with ``run_async=True`` to stream in a background
    thread and ``reconnect_async=True`` for automatic reconnection on
    disconnects.
    """

    def __init__(self, instance_url: str, access_token: str | None = None) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._access_token = access_token
        self._handle: Any | None = None
        self._on_error: Callable[[Exception], None] | None = None

    @property
    def source_id(self) -> str:
        """Datasource identifier, e.g. ``"mastodon:wien.rocks"``."""
        domain = self._instance_url.replace("https://", "").replace("http://", "")
        return f"mastodon:{domain}"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start streaming from the Mastodon public:local timeline.

        Args:
            on_post: Callback invoked for each incoming post.
            on_error: Optional callback invoked when the stream connection
                      is lost or encounters an error.
        """
        self._on_error = on_error
        client = Mastodon(
            access_token=self._access_token,
            api_base_url=self._instance_url,
        )
        listener = ViennaTalksBoutStreamListener(on_post, self.source_id, on_error)
        self._handle = client.stream_public(
            listener,
            local=True,
            run_async=True,
            reconnect_async=True,
        )
        logger.info("Started Mastodon stream for %s", self.source_id)

    def stop(self) -> None:
        """Stop the stream and release resources."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None
            logger.info("Stopped Mastodon stream for %s", self.source_id)
