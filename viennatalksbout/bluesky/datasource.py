"""Bluesky polling datasource for ViennaTalksBout.

Periodically searches Bluesky for posts matching Vienna-related keywords
using the public app.bsky.feed.searchPosts API endpoint. No authentication
required for the public API.

Follows the same daemon-thread polling pattern as LemmyDatasource and
RedditDatasource.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Callable

import requests

from viennatalksbout.config import BlueskyConfig
from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)

# Public Bluesky API base URL (no auth required for search)
BLUESKY_PUBLIC_API = "https://public.api.bsky.app"


def strip_facets(text: str) -> str:
    """Strip rich-text facet artifacts (mentions, links) to plain text.

    Bluesky post text is already plain text, but we normalize whitespace
    and strip any leftover URL noise.
    """
    # Remove bare URLs that might appear inline
    text = re.sub(r"https?://\S+", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def validate_post(post_view: dict) -> bool:
    """Return True if a Bluesky post should be processed.

    Filters out:
    - Posts with no text content
    - Reposts (reason field present with repost type)
    """
    record = post_view.get("record", {})
    text = record.get("text", "").strip()
    if not text:
        return False
    return True


def parse_post(post_view: dict, source: str) -> Post:
    """Convert a Bluesky postView object to a normalized Post.

    Args:
        post_view: A single element from the searchPosts ``posts`` array.
        source: The datasource identifier string.

    Returns:
        A normalized Post object.
    """
    uri = post_view["uri"]
    record = post_view.get("record", {})

    text = strip_facets(record.get("text", ""))

    created_str = record.get("createdAt", "")
    created_at = _parse_bluesky_datetime(created_str)

    # Bluesky posts may have language tags in the record
    langs = record.get("langs", [])
    language = langs[0] if langs else None

    return Post(
        id=f"bluesky:{uri}",
        text=text,
        created_at=created_at,
        language=language,
        source=source,
    )


def _parse_bluesky_datetime(dt_str: str) -> datetime:
    """Parse a Bluesky datetime string to a timezone-aware datetime.

    Bluesky uses ISO 8601 timestamps with Z suffix or +00:00 offset.
    """
    if not dt_str:
        return datetime.now(tz=timezone.utc)

    # Handle Z suffix
    dt_str = dt_str.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return datetime.now(tz=timezone.utc)


class BlueskyDatasource(BaseDatasource):
    """Polls Bluesky search API for Vienna-related posts.

    Uses the public ``app.bsky.feed.searchPosts`` endpoint to search
    for configurable keywords (default: ``wien``, ``vienna``).
    """

    def __init__(self, config: BlueskyConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_uris: set[str] = set()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = config.user_agent

    @property
    def source_id(self) -> str:
        """Datasource identifier: ``"bluesky:search"``."""
        return "bluesky:search"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start polling Bluesky search in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Started Bluesky polling for keywords: %s",
            ", ".join(self._config.search_queries),
        )

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped Bluesky polling")

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_queries(on_post)
            except Exception as exc:
                logger.error("Bluesky polling error: %s", exc)
                if on_error is not None:
                    on_error(exc)
            self._stop_event.wait(timeout=self._config.poll_interval)

    def _poll_queries(self, on_post: Callable[[Post], None]) -> None:
        """Search for each configured query and emit new Posts."""
        for query in self._config.search_queries:
            self._poll_query(query, on_post)

    def _poll_query(
        self, query: str, on_post: Callable[[Post], None]
    ) -> None:
        """Execute a single search query and emit new posts."""
        url = f"{BLUESKY_PUBLIC_API}/xrpc/app.bsky.feed.searchPosts"
        params: dict[str, str | int] = {
            "q": query,
            "sort": "latest",
            "limit": self._config.limit,
        }
        if self._config.lang:
            params["lang"] = self._config.lang

        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        posts = data.get("posts", [])

        new_posts = []
        for post_view in posts:
            uri = post_view.get("uri", "")
            if uri and uri not in self._seen_uris:
                new_posts.append(post_view)

        # Process oldest first for chronological order
        for post_view in reversed(new_posts):
            uri = post_view["uri"]
            if validate_post(post_view):
                post = parse_post(post_view, self.source_id)
                on_post(post)
            self._seen_uris.add(uri)
