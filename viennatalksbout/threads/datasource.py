"""Threads keyword search datasource for ViennaTalksBout.

Periodically searches Meta's Threads API for posts matching configured keywords
(e.g. 'wien', 'vienna') and emits normalized Post objects via callback.
Follows the same daemon-thread polling pattern as the other datasources.

Uses the Threads Keyword Search API:
    GET https://graph.threads.net/keyword_search
    ?q={keyword}&fields=id,text,timestamp&access_token={token}

Rate limit: 2200 queries per 24 hours (~1.5/min).
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Callable

import requests

from viennatalksbout.config import ThreadsConfig
from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)

# Fields to request from the Threads API
_SEARCH_FIELDS = "id,text,timestamp"


def strip_html(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def validate_thread(thread_data: dict) -> bool:
    """Return True if a Threads post should be processed.

    Filters out posts with no meaningful text content.
    """
    text = thread_data.get("text", "").strip()
    if not text:
        return False
    if len(text) < 10:
        return False
    return True


def parse_thread(thread_data: dict, source: str) -> Post:
    """Convert a Threads API post object to a normalized Post.

    Args:
        thread_data: A single element from the Threads ``data`` array,
            containing ``id``, ``text``, ``timestamp``.
        source: The datasource identifier string.

    Returns:
        A normalized Post object.
    """
    thread_id = thread_data["id"]
    text = strip_html(thread_data.get("text", ""))
    created_at = _parse_threads_datetime(thread_data.get("timestamp", ""))

    return Post(
        id=f"threads:{thread_id}",
        text=text,
        created_at=created_at,
        language=None,  # Threads API provides no language filtering
        source=source,
    )


def _parse_threads_datetime(dt_str: str) -> datetime:
    """Parse a Threads API timestamp to a timezone-aware datetime.

    Threads returns ISO 8601 timestamps in UTC, with formats like:
    - ``2024-06-15T12:00:00+0000``
    - ``2024-06-15T12:00:00Z``
    - ``2024-06-15T12:00:00``
    """
    if not dt_str:
        return datetime.now(tz=timezone.utc)

    # Strip timezone suffixes — we treat everything as UTC
    import re as _re

    dt_str = _re.sub(r"[Zz]$", "", dt_str)
    dt_str = _re.sub(r"[+-]\d{4}$", "", dt_str)
    dt_str = _re.sub(r"[+-]\d{2}:\d{2}$", "", dt_str)

    if "." in dt_str:
        base, frac = dt_str.rsplit(".", 1)
        frac = frac[:6].ljust(6, "0")
        dt_str = f"{base}.{frac}"
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
    else:
        fmt = "%Y-%m-%dT%H:%M:%S"

    return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)


class ThreadsDatasource(BaseDatasource):
    """Polls Threads keyword search API for new posts.

    Follows the same daemon-thread pattern as ``LemmyDatasource``
    and ``RssDatasource``.
    """

    def __init__(self, config: ThreadsConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_ids: set[str] = set()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = config.user_agent

    @property
    def source_id(self) -> str:
        """Datasource identifier, e.g. ``"threads:wien+vienna"``."""
        return f"threads:{'+'.join(self._config.keywords)}"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start polling Threads in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Started Threads polling for keywords: %s",
            ", ".join(self._config.keywords),
        )

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped Threads polling")

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_keywords(on_post)
            except Exception as exc:
                logger.error("Threads polling error: %s", exc)
                if on_error is not None:
                    on_error(exc)
            self._stop_event.wait(timeout=self._config.poll_interval)

    def _poll_keywords(self, on_post: Callable[[Post], None]) -> None:
        """Search for all configured keywords and emit new Posts."""
        for keyword in self._config.keywords:
            if self._stop_event.is_set():
                break
            self._poll_keyword(keyword, on_post)

    def _poll_keyword(
        self, keyword: str, on_post: Callable[[Post], None]
    ) -> None:
        """Search for a single keyword and emit new Posts."""
        url = "https://graph.threads.net/keyword_search"
        params = {
            "q": keyword,
            "fields": _SEARCH_FIELDS,
            "access_token": self._config.access_token,
        }

        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        threads = data.get("data", [])

        # Process only new posts (oldest first for chronological order)
        new_threads = []
        for thread_data in threads:
            thread_id = thread_data.get("id", "")
            if thread_id and thread_id not in self._seen_ids:
                new_threads.append(thread_data)

        for thread_data in reversed(new_threads):
            thread_id = thread_data["id"]
            if validate_thread(thread_data):
                post = parse_thread(thread_data, self.source_id)
                on_post(post)
            self._seen_ids.add(thread_id)
