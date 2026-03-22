"""Wien.gv.at petitions polling datasource for ViennaTalksBout.

Periodically polls petitionen.wien.gv.at for active citizen petitions,
scrapes the HTML petition listing, and emits normalized Post objects via
callback. Follows the same daemon-thread polling pattern as LemmyDatasource
and RedditDatasource.

No authentication is required — the petition platform is fully public.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Callable

import requests
from bs4 import BeautifulSoup

from viennatalksbout.config import WienGvConfig
from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)

# Base URL for the petition platform
_BASE_URL = "https://petitionen.wien.gv.at"


def _parse_date(date_str: str) -> datetime:
    """Parse a German-format date string (DD.MM.YYYY) to UTC datetime."""
    date_str = date_str.strip()
    if not date_str:
        return datetime.now(tz=timezone.utc)
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Could not parse date: %r", date_str)
        return datetime.now(tz=timezone.utc)


def validate_petition(petition: dict) -> bool:
    """Return True if a petition should be processed.

    Filters out petitions with no meaningful title text.
    """
    title = petition.get("title", "").strip()
    return len(title) > 3


def parse_petition(petition: dict, source: str) -> Post:
    """Convert a scraped petition dict to a normalized Post.

    Args:
        petition: Dict with keys: id, title, date, supporters, status.
        source: The datasource identifier string.

    Returns:
        A normalized Post object.
    """
    title = petition["title"].strip()
    status = petition.get("status", "").strip()
    supporters = petition.get("supporters", "").strip()

    # Include supporter count and status as context for topic extraction
    parts = [title]
    if supporters:
        parts.append(f"({supporters} Unterstützungen)")
    if status:
        parts.append(f"[{status}]")

    text = " ".join(parts)
    created_at = _parse_date(petition.get("date", ""))

    return Post(
        id=f"wien-gv:{petition['id']}",
        text=text,
        created_at=created_at,
        language="de",
        source=source,
    )


def scrape_petitions(html: str) -> list[dict]:
    """Parse the petition listing HTML into a list of petition dicts.

    Each dict has keys: id, title, date, supporters, status.
    """
    soup = BeautifulSoup(html, "html.parser")
    petitions: list[dict] = []

    # The petition listing renders as table rows or repeated elements
    # with links to PetitionDetail.aspx?PetID=<uuid>
    for link in soup.find_all("a", href=re.compile(r"PetitionDetail\.aspx\?PetID=")):
        pet_id_match = re.search(r"PetID=([a-f0-9]+)", link["href"])
        if not pet_id_match:
            continue

        pet_id = pet_id_match.group(1)
        title = link.get_text(strip=True)

        if not title:
            continue

        # Walk up to the containing row element to find sibling data
        row = link.find_parent("tr")
        if row is None:
            # Fallback: try parent containers for non-table layouts
            row = link.find_parent(["div", "li"])

        date = ""
        supporters = ""
        status = ""

        if row is not None:
            cells = row.find_all(["td", "span", "div"])
            texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]

            # Expected order from the site: date, title, supporters, status
            for text in texts:
                if re.match(r"\d{2}\.\d{2}\.\d{4}$", text):
                    date = text
                elif re.match(r"^\d+$", text):
                    supporters = text
                elif text in (
                    "Freigegeben",
                    "Ausgezählt",
                    "In Bearbeitung",
                    "Beendet",
                    "Abgeschlossen",
                ):
                    status = text

        petitions.append(
            {
                "id": pet_id,
                "title": title,
                "date": date,
                "supporters": supporters,
                "status": status,
            }
        )

    return petitions


class WienGvPetitionsDatasource(BaseDatasource):
    """Polls petitionen.wien.gv.at for active citizen petitions.

    Follows the same daemon-thread pattern as ``LemmyDatasource``
    and ``RedditDatasource``.
    """

    def __init__(self, config: WienGvConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_ids: set[str] = set()
        self._session = requests.Session()
        self._session.headers["User-Agent"] = config.user_agent

    @property
    def source_id(self) -> str:
        """Datasource identifier: ``"wien-gv:petitions"``."""
        return "wien-gv:petitions"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start polling petitionen.wien.gv.at in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        logger.info("Started Wien.gv petitions polling (%s)", self._config.url)

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped Wien.gv petitions polling")

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_once(on_post)
            except Exception as exc:
                logger.error("Wien.gv polling error: %s", exc)
                if on_error is not None:
                    on_error(exc)
            self._stop_event.wait(timeout=self._config.poll_interval)

    def _poll_once(self, on_post: Callable[[Post], None]) -> None:
        """Fetch petition listing, parse, deduplicate, and emit Posts."""
        resp = self._session.get(self._config.url, timeout=30)
        resp.raise_for_status()

        petitions = scrape_petitions(resp.text)
        new_count = 0

        for petition in petitions:
            pet_id = petition["id"]
            if pet_id in self._seen_ids:
                continue
            self._seen_ids.add(pet_id)
            if validate_petition(petition):
                post = parse_petition(petition, self.source_id)
                on_post(post)
                new_count += 1

        if new_count:
            logger.debug("Emitted %d new petitions", new_count)
