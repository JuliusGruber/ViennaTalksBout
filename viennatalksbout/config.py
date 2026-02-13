"""Configuration loading and validation for ViennaTalksBout.

Loads settings from environment variables (with optional .env file support).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Default model for topic extraction (Haiku 4.5 — cost efficient for small batches)
DEFAULT_EXTRACTOR_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class MastodonConfig:
    """Configuration for connecting to a Mastodon instance."""

    instance_url: str
    client_id: str
    client_secret: str
    access_token: str

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.instance_url:
            errors.append("MASTODON_INSTANCE_URL is required")
        elif not self.instance_url.startswith("https://"):
            errors.append("MASTODON_INSTANCE_URL must start with https://")
        if not self.client_id:
            errors.append("MASTODON_CLIENT_ID is required")
        if not self.client_secret:
            errors.append("MASTODON_CLIENT_SECRET is required")
        if not self.access_token:
            errors.append("MASTODON_ACCESS_TOKEN is required")
        return errors


@dataclass(frozen=True)
class ExtractorConfig:
    """Configuration for the Claude-based topic extractor.

    Attributes:
        api_key: Anthropic API key.
        model: Claude model ID (default: Haiku 4.5).
    """

    api_key: str
    model: str = DEFAULT_EXTRACTOR_MODEL

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.api_key:
            errors.append("ANTHROPIC_API_KEY is required")
        if not self.model:
            errors.append("ANTHROPIC_MODEL must not be empty")
        return errors


DEFAULT_RSS_FEEDS = (
    ("https://rss.orf.at/wien.xml", "orf-wien"),
    ("https://rss.orf.at/news.xml", "orf-news"),
    ("http://www.vienna.at/rss", "vienna-at"),
    ("https://www.ots.at/rss/index", "ots"),
)


@dataclass(frozen=True)
class FeedConfig:
    """Configuration for a single RSS feed."""

    url: str
    name: str
    language: str = "de"


@dataclass(frozen=True)
class RssConfig:
    """Configuration for the RSS news datasource.

    Attributes:
        feeds: Tuple of feed configurations to poll.
        poll_interval: Seconds between poll cycles.
        user_agent: User-Agent header for HTTP requests.
        enabled: Whether the RSS datasource is active.
    """

    feeds: tuple[FeedConfig, ...]
    poll_interval: int = 600
    user_agent: str = "ViennaTalksBout/1.0"
    enabled: bool = True

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.feeds:
            errors.append("RSS_FEEDS must not be empty when RSS is enabled")
        if self.poll_interval <= 0:
            errors.append("RSS_POLL_INTERVAL must be positive")
        return errors


def load_rss_config() -> RssConfig:
    """Load RSS datasource configuration from environment variables.

    Environment variables:
        RSS_ENABLED: "true" to enable (default "false").
        RSS_FEEDS: Comma-separated "url|name" pairs (default: Tier 1 Vienna feeds).
        RSS_POLL_INTERVAL: Seconds between polls (default 600).
        RSS_USER_AGENT: User-Agent header (default "ViennaTalksBout/1.0").

    Returns:
        An RssConfig instance.

    Raises:
        ValueError: If the configuration is invalid when enabled.
    """
    enabled = os.environ.get("RSS_ENABLED", "false").strip().lower() == "true"

    feeds_raw = os.environ.get("RSS_FEEDS", "").strip()
    if feeds_raw:
        feeds = []
        for pair in feeds_raw.split(","):
            pair = pair.strip()
            if "|" in pair:
                url, name = pair.split("|", 1)
                feeds.append(FeedConfig(url=url.strip(), name=name.strip()))
        feeds_tuple = tuple(feeds)
    else:
        feeds_tuple = tuple(
            FeedConfig(url=url, name=name) for url, name in DEFAULT_RSS_FEEDS
        )

    poll_interval = int(os.environ.get("RSS_POLL_INTERVAL", "600").strip())
    user_agent = os.environ.get("RSS_USER_AGENT", "ViennaTalksBout/1.0").strip()

    config = RssConfig(
        feeds=feeds_tuple,
        poll_interval=poll_interval,
        user_agent=user_agent,
        enabled=enabled,
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid RSS configuration:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return config


def load_config(env_path: str | Path | None = None) -> MastodonConfig:
    """Load Mastodon configuration from environment variables.

    Args:
        env_path: Optional path to a .env file. If None, looks for .env
                  in the current working directory.

    Returns:
        A validated MastodonConfig instance.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    if env_path is not None:
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    config = MastodonConfig(
        instance_url=os.environ.get("MASTODON_INSTANCE_URL", "").strip(),
        client_id=os.environ.get("MASTODON_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("MASTODON_CLIENT_SECRET", "").strip(),
        access_token=os.environ.get("MASTODON_ACCESS_TOKEN", "").strip(),
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid Mastodon configuration:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return config


def load_extractor_config(env_path: str | Path | None = None) -> ExtractorConfig:
    """Load topic extractor configuration from environment variables.

    Args:
        env_path: Optional path to a .env file. If None, looks for .env
                  in the current working directory.

    Returns:
        A validated ExtractorConfig instance.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    if env_path is not None:
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    config = ExtractorConfig(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_EXTRACTOR_MODEL).strip(),
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid extractor configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return config
