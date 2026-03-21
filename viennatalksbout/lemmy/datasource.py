"""Lemmy polling datasource for ViennaTalksBout.

Periodically polls configured Lemmy communities for new posts using the
Lemmy REST API (v3), and emits normalized Post objects via callback.
Follows the same daemon-thread polling pattern as RedditDatasource and
RssDatasource.

Uses raw HTTP requests (not lemmy-js-client) to avoid AGPL concerns.
No authentication is required for reading public posts.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Callable

import requests
from bs4 import BeautifulSoup

from viennatalksbout.config import LemmyConfig
from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)


def strip_markdown(text: str) -> str:
    """Strip Markdown formatting to plain text.

    Removes bold, italic, strikethrough, links, block quotes, headings,
    code blocks/spans, and normalizes whitespace.
    """
    # Remove fenced code blocks (```...```)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove inline code (`...`)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Remove images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Replace links [text](url) with text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove headings (# ... at start of lines)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold (**text** or __text__)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Remove italic (*text* or _text_)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    # Remove strikethrough (~~text~~)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Remove block quotes (> at start of lines)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove horizontal rules (---, ***, ___)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_html(text: str) -> str:
    """Strip HTML tags to plain text."""
    return BeautifulSoup(text, "html.parser").get_text(separator=" ").strip()


def validate_post(post_data: dict) -> bool:
    """Return True if a Lemmy post should be processed.

    Filters out:
    - Deleted or removed posts
    - Posts with no meaningful text content (title + body)
    - Stickied (featured) posts
    """
    post = post_data.get("post", {})

    if post.get("deleted", False) or post.get("removed", False):
        return False

    if post.get("featured_community", False) or post.get("featured_local", False):
        return False

    name = post.get("name", "").strip()
    body = post.get("body", "").strip()

    if not name and not body:
        return False

    return True


def parse_post(post_data: dict, source: str) -> Post:
    """Convert a Lemmy API post object to a normalized Post.

    Args:
        post_data: A single element from the Lemmy ``posts`` array,
            containing ``post``, ``creator``, ``community``, etc.
        source: The datasource identifier string.

    Returns:
        A normalized Post object.
    """
    post = post_data["post"]
    post_id = post["id"]
    ap_id = post.get("ap_id", f"lemmy:{post_id}")

    name = strip_markdown(post.get("name", ""))
    body_raw = post.get("body", "")
    body = strip_markdown(body_raw) if body_raw else ""

    if name and body:
        text = f"{name}. {body}"
    elif name:
        text = name
    else:
        text = body

    published = post.get("published", "")
    created_at = _parse_lemmy_datetime(published)

    return Post(
        id=f"lemmy:{ap_id}",
        text=text,
        created_at=created_at,
        language="de",
        source=source,
    )


def _parse_lemmy_datetime(dt_str: str) -> datetime:
    """Parse a Lemmy datetime string to a timezone-aware datetime.

    Lemmy returns ISO 8601 timestamps, typically in UTC.
    """
    if not dt_str:
        return datetime.now(tz=timezone.utc)

    # Lemmy timestamps may or may not have timezone info
    # Strip trailing Z and parse as UTC
    dt_str = dt_str.rstrip("Z")
    # Handle fractional seconds of varying length
    if "." in dt_str:
        # Truncate fractional seconds to 6 digits (microseconds)
        base, frac = dt_str.rsplit(".", 1)
        frac = frac[:6].ljust(6, "0")
        dt_str = f"{base}.{frac}"
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
    else:
        fmt = "%Y-%m-%dT%H:%M:%S"

    return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)


class LemmyDatasource(BaseDatasource):
    """Polls Lemmy communities for new posts.

    Follows the same daemon-thread pattern as ``RedditDatasource``
    and ``RssDatasource``.
    """

    def __init__(self, config: LemmyConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_ids: set[int] = set()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = config.user_agent

    @property
    def source_id(self) -> str:
        """Datasource identifier, e.g. ``"lemmy:feddit.org"``."""
        return f"lemmy:{self._config.instance}"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start polling Lemmy in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Started Lemmy polling for %s communities: %s",
            self._config.instance,
            ", ".join(self._config.communities),
        )

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped Lemmy polling for %s", self._config.instance)

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_communities(on_post)
            except Exception as exc:
                logger.error("Lemmy polling error: %s", exc)
                if on_error is not None:
                    on_error(exc)
            self._stop_event.wait(timeout=self._config.poll_interval)

    def _poll_communities(self, on_post: Callable[[Post], None]) -> None:
        """Fetch new posts from all configured communities and emit Posts."""
        for community in self._config.communities:
            self._poll_community(community, on_post)

    def _poll_community(
        self, community: str, on_post: Callable[[Post], None]
    ) -> None:
        """Fetch new posts from a single community."""
        url = f"https://{self._config.instance}/api/v3/post/list"
        params = {
            "community_name": community,
            "sort": "New",
            "limit": 50,
        }

        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        posts = data.get("posts", [])

        # Process only new posts (oldest first for chronological order)
        new_posts = []
        for post_data in posts:
            post_id = post_data.get("post", {}).get("id")
            if post_id is not None and post_id not in self._seen_ids:
                new_posts.append(post_data)

        for post_data in reversed(new_posts):
            post_id = post_data["post"]["id"]
            if validate_post(post_data):
                post = parse_post(post_data, self.source_id)
                on_post(post)
            self._seen_ids.add(post_id)
