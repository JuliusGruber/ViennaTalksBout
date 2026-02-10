"""Abstract base interface for ViennaTalksBout datasources.

Defines the common contract that all datasources (Mastodon, Reddit, etc.)
must implement, plus the normalized Post model that flows through the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


@dataclass(frozen=True)
class Post:
    """A normalized post from any datasource.

    Attributes:
        id: Unique post identifier from the source platform.
        text: Plain text content (HTML already stripped).
        created_at: When the post was created.
        language: ISO 639-1 language code, or None if unknown.
        source: Datasource identifier (e.g. "mastodon:wien.rocks").
    """

    id: str
    text: str
    created_at: datetime
    language: str | None
    source: str


class BaseDatasource(ABC):
    """Abstract interface for ViennaTalksBout datasources.

    Each datasource connects to an external platform, receives posts in
    real time, normalizes them into Post objects, and delivers them via
    a callback. Implementations handle platform-specific details like
    authentication, streaming protocols, and reconnection.
    """

    @abstractmethod
    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start receiving posts from the datasource.

        Args:
            on_post: Callback invoked for each incoming post.
            on_error: Optional callback invoked when the stream encounters
                      an error or the connection is lost.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop receiving posts and release resources."""
