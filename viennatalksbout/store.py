"""Topic store for managing trending topics with lifecycle states.

Maintains up to 20 active topics, each with lifecycle states (entering,
growing, shrinking). Topics are merged from LLM extraction results and
decay over time when no longer mentioned. Hourly snapshots are persisted
as JSON files for the time slider feature.

**Topic matching:** Case-insensitive, whitespace-normalized, Unicode NFC.
For the MVP, exact normalized matching is used. The LLM tends to be
consistent in naming; fuzzy matching can be added later if fragmentation
becomes a problem.

**Lifecycle state transitions:**

- New topic → ``entering``
- ``entering`` + seen again → ``growing``
- ``growing`` + seen again → ``growing`` (score updated)
- ``entering``/``growing`` + unseen for ``stale_after`` batches → ``shrinking``
- ``shrinking`` + seen again → ``growing`` (recovery)
- ``shrinking`` + score decays below ``min_score`` → removed (disappeared)

**Active topics definition:** All topics in ``entering``, ``growing``, or
``shrinking`` states count toward the 20-topic cap. When a new topic
enters and the cap is reached, the lowest-scoring topic is evicted. This
naturally prioritizes growing topics over fading ones.

**Snapshot format:** JSON files named ``topics_YYYYMMDD_HH.json`` in a
configurable directory. Snapshots older than ``retention_hours`` are
cleaned up.
"""

from __future__ import annotations

import json
import logging
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from viennatalksbout.extractor import ExtractedTopic

logger = logging.getLogger(__name__)

DEFAULT_MAX_ACTIVE = 20
DEFAULT_STALE_AFTER = 3
DEFAULT_DECAY_FACTOR = 0.5
DEFAULT_MIN_SCORE = 0.05
DEFAULT_RETENTION_HOURS = 24


class TopicState(Enum):
    """Lifecycle states for a topic in the tag cloud."""

    ENTERING = "entering"
    GROWING = "growing"
    SHRINKING = "shrinking"


@dataclass
class Topic:
    """A topic tracked in the store with lifecycle metadata.

    Attributes:
        name: Display name (original casing from first extraction).
        normalized_name: Lowercased, whitespace-normalized name for matching.
        score: Current relevance score (0.0 to 1.0).
        first_seen: When this topic was first extracted (UTC).
        last_seen: When this topic was last extracted (UTC).
        source: Datasource identifier (e.g. "mastodon:wien.rocks").
        state: Current lifecycle state.
        batches_since_seen: Consecutive merge cycles without seeing this topic.
    """

    name: str
    normalized_name: str
    score: float
    first_seen: datetime
    last_seen: datetime
    source: str
    state: TopicState
    batches_since_seen: int = 0


def normalize_topic_name(name: str) -> str:
    """Normalize a topic name for case-insensitive matching.

    Applies Unicode NFC normalization, lowercasing, whitespace stripping
    and collapsing.

    >>> normalize_topic_name("  U2  Störung  ")
    'u2 störung'
    """
    normalized = unicodedata.normalize("NFC", name)
    normalized = normalized.lower().strip()
    return " ".join(normalized.split())


class TopicStore:
    """Thread-safe store for active trending topics.

    Maintains up to ``max_active`` topics with lifecycle state tracking.
    Call :meth:`merge` after each LLM extraction to update the topic set.

    Args:
        max_active: Maximum number of active topics (default: 20).
        stale_after: Unseen merge cycles before a topic starts shrinking.
        decay_factor: Score multiplier applied each merge cycle while shrinking.
        min_score: Score threshold below which a shrinking topic is removed.
        snapshot_dir: Directory for hourly JSON snapshots (None disables).
        retention_hours: Hours to keep snapshot files before cleanup.
    """

    def __init__(
        self,
        max_active: int = DEFAULT_MAX_ACTIVE,
        stale_after: int = DEFAULT_STALE_AFTER,
        decay_factor: float = DEFAULT_DECAY_FACTOR,
        min_score: float = DEFAULT_MIN_SCORE,
        snapshot_dir: str | Path | None = None,
        retention_hours: int = DEFAULT_RETENTION_HOURS,
    ) -> None:
        if max_active <= 0:
            raise ValueError(f"max_active must be positive, got {max_active}")
        if stale_after <= 0:
            raise ValueError(f"stale_after must be positive, got {stale_after}")
        if not (0.0 < decay_factor < 1.0):
            raise ValueError(
                f"decay_factor must be in (0.0, 1.0), got {decay_factor}"
            )
        if min_score <= 0:
            raise ValueError(f"min_score must be positive, got {min_score}")
        if retention_hours <= 0:
            raise ValueError(
                f"retention_hours must be positive, got {retention_hours}"
            )

        self._max_active = max_active
        self._stale_after = stale_after
        self._decay_factor = decay_factor
        self._min_score = min_score
        self._snapshot_dir = Path(snapshot_dir) if snapshot_dir is not None else None
        self._retention_hours = retention_hours

        self._lock = threading.Lock()
        self._topics: dict[str, Topic] = {}  # keyed by normalized_name

    @property
    def max_active(self) -> int:
        """Maximum number of active topics."""
        return self._max_active

    @property
    def stale_after(self) -> int:
        """Unseen merge cycles before shrinking begins."""
        return self._stale_after

    @property
    def decay_factor(self) -> float:
        """Score multiplier per merge cycle while shrinking."""
        return self._decay_factor

    @property
    def min_score(self) -> float:
        """Score threshold below which topics are removed."""
        return self._min_score

    @property
    def retention_hours(self) -> int:
        """Hours to retain snapshot files."""
        return self._retention_hours

    def merge(
        self,
        extracted_topics: list[ExtractedTopic],
        source: str,
        now: datetime | None = None,
    ) -> None:
        """Merge newly extracted topics into the store.

        - Matched topics: update score, refresh ``last_seen``, transition
          to ``growing``.
        - New topics: add with ``entering`` state.
        - Unseen existing topics: increment staleness counter; apply score
          decay when shrinking; remove when score falls below ``min_score``.
        - Enforce ``max_active`` cap by evicting lowest-scoring topics.

        Args:
            extracted_topics: Topics from the latest LLM extraction.
            source: Datasource identifier (e.g. ``"mastodon:wien.rocks"``).
            now: Current timestamp (defaults to UTC now; injectable for testing).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        with self._lock:
            self._merge_locked(extracted_topics, source, now)

    def _merge_locked(
        self,
        extracted_topics: list[ExtractedTopic],
        source: str,
        now: datetime,
    ) -> None:
        """Internal merge logic. Must be called with ``_lock`` held."""
        seen_normalized: set[str] = set()

        for et in extracted_topics:
            norm = normalize_topic_name(et.topic)
            if not norm:
                continue
            seen_normalized.add(norm)

            if norm in self._topics:
                topic = self._topics[norm]
                topic.score = et.score
                topic.last_seen = now
                topic.batches_since_seen = 0
                if topic.state in (TopicState.ENTERING, TopicState.SHRINKING):
                    topic.state = TopicState.GROWING
            else:
                self._topics[norm] = Topic(
                    name=et.topic.strip(),
                    normalized_name=norm,
                    score=et.score,
                    first_seen=now,
                    last_seen=now,
                    source=source,
                    state=TopicState.ENTERING,
                    batches_since_seen=0,
                )

        # Process unseen topics
        to_remove: list[str] = []
        for norm, topic in self._topics.items():
            if norm in seen_normalized:
                continue

            topic.batches_since_seen += 1

            if topic.state in (TopicState.ENTERING, TopicState.GROWING):
                if topic.batches_since_seen >= self._stale_after:
                    topic.state = TopicState.SHRINKING

            if topic.state == TopicState.SHRINKING:
                topic.score *= self._decay_factor
                if topic.score < self._min_score:
                    to_remove.append(norm)

        for norm in to_remove:
            logger.debug("Topic disappeared: %s", self._topics[norm].name)
            del self._topics[norm]

        self._enforce_cap()

    def _enforce_cap(self) -> None:
        """Remove lowest-scoring topics to stay within ``max_active``.

        Must be called with ``_lock`` held.
        """
        while len(self._topics) > self._max_active:
            lowest_norm = min(
                self._topics, key=lambda n: self._topics[n].score
            )
            logger.debug(
                "Evicting topic (cap): %s (score=%.3f)",
                self._topics[lowest_norm].name,
                self._topics[lowest_norm].score,
            )
            del self._topics[lowest_norm]

    def get_current_topics(self) -> list[Topic]:
        """Return a snapshot of all active topics, sorted by score descending.

        Returns a new list of copied Topic objects that is safe to use
        without holding the store's lock.
        """
        with self._lock:
            topics = [
                Topic(
                    name=t.name,
                    normalized_name=t.normalized_name,
                    score=t.score,
                    first_seen=t.first_seen,
                    last_seen=t.last_seen,
                    source=t.source,
                    state=t.state,
                    batches_since_seen=t.batches_since_seen,
                )
                for t in self._topics.values()
            ]
        topics.sort(key=lambda t: t.score, reverse=True)
        return topics

    def get_topic_count(self) -> int:
        """Return the number of active topics."""
        with self._lock:
            return len(self._topics)

    # ------------------------------------------------------------------
    # Snapshot persistence
    # ------------------------------------------------------------------

    def save_snapshot(self, now: datetime | None = None) -> Path | None:
        """Save the current topic state as an hourly JSON snapshot.

        The snapshot file is named ``topics_YYYYMMDD_HH.json`` and placed
        in ``snapshot_dir``. If ``snapshot_dir`` is not configured, returns
        None.

        Args:
            now: Current timestamp (defaults to UTC now; injectable for testing).

        Returns:
            Path to the saved snapshot file, or None if snapshots are disabled.
        """
        if self._snapshot_dir is None:
            return None

        if now is None:
            now = datetime.now(timezone.utc)

        topics = self.get_current_topics()

        snapshot = {
            "timestamp": now.isoformat(),
            "topics": [
                {
                    "name": t.name,
                    "score": t.score,
                    "first_seen": t.first_seen.isoformat(),
                    "last_seen": t.last_seen.isoformat(),
                    "source": t.source,
                    "state": t.state.value,
                    "batches_since_seen": t.batches_since_seen,
                }
                for t in topics
            ],
        }

        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"topics_{now.strftime('%Y%m%d_%H')}.json"
        path = self._snapshot_dir / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)

        logger.info("Saved snapshot: %s (%d topics)", path, len(topics))
        return path

    def load_snapshot(self, path: str | Path) -> list[Topic]:
        """Load topics from a snapshot file.

        Args:
            path: Path to the JSON snapshot file.

        Returns:
            List of Topic objects from the snapshot.

        Raises:
            FileNotFoundError: If the snapshot file does not exist.
            ValueError: If the snapshot format is invalid.
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "topics" not in data:
            raise ValueError(
                f"Invalid snapshot format: missing 'topics' key in {path}"
            )

        topics: list[Topic] = []
        for entry in data["topics"]:
            try:
                topics.append(
                    Topic(
                        name=entry["name"],
                        normalized_name=normalize_topic_name(entry["name"]),
                        score=float(entry["score"]),
                        first_seen=datetime.fromisoformat(entry["first_seen"]),
                        last_seen=datetime.fromisoformat(entry["last_seen"]),
                        source=entry["source"],
                        state=TopicState(entry["state"]),
                        batches_since_seen=int(
                            entry.get("batches_since_seen", 0)
                        ),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "Skipping malformed topic in snapshot %s: %s", path, exc
                )

        return topics

    def cleanup_snapshots(self, now: datetime | None = None) -> int:
        """Remove snapshot files older than the retention period.

        Parses the timestamp from each snapshot filename and removes files
        whose hour is older than ``now - retention_hours``.

        Args:
            now: Current timestamp (defaults to UTC now; injectable for testing).

        Returns:
            Number of snapshot files removed.
        """
        if self._snapshot_dir is None:
            return 0

        if now is None:
            now = datetime.now(timezone.utc)

        cutoff = now - timedelta(hours=self._retention_hours)
        removed = 0

        if not self._snapshot_dir.exists():
            return 0

        for path in self._snapshot_dir.glob("topics_*.json"):
            try:
                stem = path.stem  # e.g. "topics_20250615_12"
                date_str = stem[len("topics_"):]  # "20250615_12"
                file_time = datetime.strptime(date_str, "%Y%m%d_%H").replace(
                    tzinfo=timezone.utc
                )

                if file_time < cutoff:
                    path.unlink()
                    removed += 1
                    logger.debug("Removed old snapshot: %s", path)
            except (ValueError, OSError) as exc:
                logger.warning(
                    "Error processing snapshot %s: %s", path, exc
                )

        if removed > 0:
            logger.info("Cleaned up %d old snapshot(s)", removed)

        return removed
