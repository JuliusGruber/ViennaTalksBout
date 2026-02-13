"""Mastodon REST API polling datasource for ViennaTalksBout.

Periodically polls the public local timeline via ``GET /api/v1/timelines/public``
and emits normalized Post objects via callback.  Uses ``since_id`` to fetch only
new statuses each cycle.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

import requests

from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.mastodon.stream import filter_status, parse_status, validate_status

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 30  # seconds


class MastodonPollingDatasource(BaseDatasource):
    """Polls posts from a Mastodon instance's public local timeline.

    An alternative to the SSE-based ``MastodonDatasource`` that uses the
    REST API instead.  Suitable for instances that don't support streaming
    or when a simpler deployment model is preferred.
    """

    def __init__(
        self,
        instance_url: str,
        access_token: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        initial_since_id: str | None = None,
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._access_token = access_token
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._since_id: str | None = initial_since_id

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
        """Start polling the Mastodon public local timeline.

        Spawns a daemon thread that polls in a loop until :meth:`stop` is
        called.

        Args:
            on_post: Callback invoked for each incoming post.
            on_error: Optional callback invoked on HTTP errors.
        """
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        logger.info("Started Mastodon polling for %s", self.source_id)

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped Mastodon polling for %s", self.source_id)

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_once(on_post)
            except requests.RequestException as exc:
                logger.error("Polling error: %s", exc)
                if on_error is not None:
                    on_error(exc)
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_once(self, on_post: Callable[[Post], None]) -> None:
        """Execute a single poll cycle."""
        url = f"{self._instance_url}/api/v1/timelines/public"
        params: dict[str, str] = {"local": "true"}
        if self._since_id is not None:
            params["since_id"] = self._since_id

        headers: dict[str, str] = {}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()

        statuses = resp.json()
        if not isinstance(statuses, list):
            logger.warning("Expected list from timeline, got %s", type(statuses).__name__)
            return

        # API returns newest-first; process oldest-first for chronological order
        for status in reversed(statuses):
            validated = validate_status(status)
            if validated is None:
                continue
            if not filter_status(validated):
                continue
            post = parse_status(validated, self.source_id)
            logger.info("Post received via polling: id=%s lang=%s source=%s", post.id, post.language, post.source)
            on_post(post)

        if not statuses:
            logger.info("Poll cycle complete: 0 new posts (since_id=%s)", self._since_id)

        # Track the newest id for the next poll
        if statuses:
            self._since_id = str(statuses[0]["id"])
