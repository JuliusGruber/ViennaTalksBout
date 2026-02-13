"""RSS feed polling datasource for ViennaTalksBout.

Periodically polls configured RSS feeds (Austrian news outlets) and emits
normalized Post objects via callback. Uses feedparser for robust feed parsing
and conditional HTTP requests (ETag / If-Modified-Since) to minimise bandwidth.
"""

from __future__ import annotations

import calendar
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Callable

import feedparser
import requests
from bs4 import BeautifulSoup

from viennatalksbout.config import FeedConfig
from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)


def strip_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    return re.sub(r"\s+", " ", text).strip()


class RssDatasource(BaseDatasource):
    """Polls RSS feeds and emits Posts.

    Follows the same daemon-thread pattern as ``MastodonPollingDatasource``.
    """

    def __init__(
        self,
        feeds: list[FeedConfig],
        poll_interval: int = 600,
        user_agent: str = "ViennaTalksBout/1.0",
    ) -> None:
        self._feeds = feeds
        self._poll_interval = poll_interval
        self._user_agent = user_agent
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Per-feed dedup: {feed.name: set of entry IDs}
        self._seen_ids: dict[str, set[str]] = {}
        # Conditional request headers per feed
        self._etags: dict[str, str] = {}
        self._last_modified: dict[str, str] = {}

    @property
    def source_id(self) -> str:
        """Datasource identifier."""
        return "news:rss"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start polling RSS feeds in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        feed_names = [f.name for f in self._feeds]
        logger.info("Started RSS polling for feeds: %s", feed_names)

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped RSS polling")

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            for feed in self._feeds:
                if self._stop_event.is_set():
                    break
                try:
                    self._poll_feed(feed, on_post)
                except Exception as exc:
                    logger.error("Error polling feed %s: %s", feed.name, exc)
                    if on_error is not None:
                        on_error(exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_feed(
        self,
        feed: FeedConfig,
        on_post: Callable[[Post], None],
    ) -> None:
        """Fetch and parse a single feed, emitting new entries as Posts."""
        headers: dict[str, str] = {"User-Agent": self._user_agent}
        if feed.name in self._etags:
            headers["If-None-Match"] = self._etags[feed.name]
        if feed.name in self._last_modified:
            headers["If-Modified-Since"] = self._last_modified[feed.name]

        resp = requests.get(feed.url, headers=headers, timeout=30)

        # 304 Not Modified — nothing new
        if resp.status_code == 304:
            logger.debug("Feed %s: 304 Not Modified", feed.name)
            return

        resp.raise_for_status()

        # Store conditional headers for next request
        if "ETag" in resp.headers:
            self._etags[feed.name] = resp.headers["ETag"]
        if "Last-Modified" in resp.headers:
            self._last_modified[feed.name] = resp.headers["Last-Modified"]

        parsed = feedparser.parse(resp.content)

        # Build current set of entry IDs
        current_ids: set[str] = set()
        new_entries = []
        previous_ids = self._seen_ids.get(feed.name, set())

        for entry in parsed.entries:
            entry_id = self._get_entry_id(entry, feed)
            current_ids.add(entry_id)
            if entry_id not in previous_ids:
                new_entries.append(entry)

        # Replace previous with current for next poll
        self._seen_ids[feed.name] = current_ids

        for entry in new_entries:
            post = self._entry_to_post(entry, feed)
            if post is not None:
                on_post(post)

        if new_entries:
            logger.info(
                "Feed %s: %d new entries", feed.name, len(new_entries)
            )

    def _get_entry_id(self, entry: feedparser.FeedParserDict, feed: FeedConfig) -> str:
        """Get a unique ID for a feed entry."""
        return entry.get("id") or entry.get("link") or ""

    def _entry_to_post(
        self, entry: feedparser.FeedParserDict, feed: FeedConfig
    ) -> Post | None:
        """Convert a feed entry to a Post, or None if unusable."""
        title = entry.get("title", "")
        summary_raw = entry.get("summary", "")
        summary = strip_html(summary_raw) if summary_raw else ""

        if title and summary:
            text = f"{title}. {summary}"
        elif title:
            text = title
        else:
            text = summary

        if not text.strip():
            return None

        # Parse date
        published = entry.get("published_parsed")
        if published:
            try:
                timestamp = calendar.timegm(published)
                created_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            except (ValueError, OverflowError, OSError):
                created_at = datetime.now(timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)

        # Language: entry-level > feed default
        language = entry.get("language") or feed.language

        entry_id = self._get_entry_id(entry, feed)
        post_id = f"rss:{feed.name}:{entry_id}"

        return Post(
            id=post_id,
            text=text,
            created_at=created_at,
            language=language,
            source=f"news:{feed.name}",
        )
