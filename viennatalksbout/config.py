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
        api_key: Anthropic API key (required for ``sdk`` backend only).
        model: Claude model ID (default: Haiku 4.5).
        backend: Which extraction backend to use: ``"sdk"`` (Anthropic API)
            or ``"cli"`` (claude CLI subprocess).
    """

    api_key: str
    model: str = DEFAULT_EXTRACTOR_MODEL
    backend: str = "sdk"

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if self.backend not in ("sdk", "cli"):
            errors.append(
                f"EXTRACTOR_BACKEND must be 'sdk' or 'cli', got '{self.backend}'"
            )
        if self.backend == "sdk" and not self.api_key:
            errors.append("ANTHROPIC_API_KEY is required for sdk backend")
        if not self.model:
            errors.append("ANTHROPIC_MODEL must not be empty")
        return errors


@dataclass(frozen=True)
class RedditConfig:
    """Configuration for the Reddit datasource.

    Attributes:
        client_id: Reddit API OAuth client ID.
        client_secret: Reddit API OAuth client secret.
        username: Reddit account username.
        password: Reddit account password.
        subreddits: Tuple of subreddit names to poll.
        poll_interval: Seconds between poll cycles.
        user_agent: User-Agent string for Reddit API requests.
        enabled: Whether the Reddit datasource is active.
        include_comments: Whether to also poll comments (not just submissions).
    """

    client_id: str
    client_secret: str
    username: str
    password: str
    subreddits: tuple[str, ...] = ("wien", "austria")
    poll_interval: int = 60
    user_agent: str = ""
    enabled: bool = False
    include_comments: bool = True

    def __post_init__(self) -> None:
        if not self.user_agent:
            ua = f"ViennaTalksBout/1.0 (by /u/{self.username})"
            object.__setattr__(self, "user_agent", ua)

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.client_id:
            errors.append("REDDIT_CLIENT_ID is required")
        if not self.client_secret:
            errors.append("REDDIT_CLIENT_SECRET is required")
        if not self.username:
            errors.append("REDDIT_USERNAME is required")
        if not self.password:
            errors.append("REDDIT_PASSWORD is required")
        if not self.subreddits:
            errors.append("REDDIT_SUBREDDITS must not be empty when Reddit is enabled")
        if self.poll_interval <= 0:
            errors.append("REDDIT_POLL_INTERVAL must be positive")
        return errors


DEFAULT_RSS_FEEDS = (
    ("https://rss.orf.at/wien.xml", "orf-wien"),
    ("https://rss.orf.at/news.xml", "orf-news"),
    ("http://www.vienna.at/rss", "vienna-at"),
    ("https://www.ots.at/rss/index", "ots"),
    ("https://www.falter.at/rss", "falter"),
    ("https://www.1000thingsmagazine.com/feed/", "1000things"),
    ("https://www.stadtbekannt.at/feed/", "stadtbekannt"),
    ("https://www.derstandard.at/rss", "derstandard"),
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


@dataclass(frozen=True)
class LemmyConfig:
    """Configuration for the Lemmy datasource.

    Attributes:
        instance: Lemmy instance hostname (e.g. "feddit.org").
        communities: Tuple of community names to poll.
        poll_interval: Seconds between poll cycles.
        user_agent: User-Agent header for HTTP requests.
        enabled: Whether the Lemmy datasource is active.
    """

    instance: str = "feddit.org"
    communities: tuple[str, ...] = ("austria", "dach")
    poll_interval: int = 300
    user_agent: str = "ViennaTalksBout/1.0"
    enabled: bool = False

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.instance:
            errors.append("LEMMY_INSTANCE is required")
        if not self.communities:
            errors.append(
                "LEMMY_COMMUNITIES must not be empty when Lemmy is enabled"
            )
        if self.poll_interval <= 0:
            errors.append("LEMMY_POLL_INTERVAL must be positive")
        return errors


@dataclass(frozen=True)
class ThreadsConfig:
    """Configuration for the Threads datasource.

    Attributes:
        access_token: Meta API access token (long-lived).
        keywords: Tuple of keywords to search for.
        poll_interval: Seconds between poll cycles.
        user_agent: User-Agent header for HTTP requests.
        enabled: Whether the Threads datasource is active.
    """

    access_token: str
    keywords: tuple[str, ...] = ("wien", "vienna")
    poll_interval: int = 300
    user_agent: str = "ViennaTalksBout/1.0"
    enabled: bool = False

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.access_token:
            errors.append("THREADS_ACCESS_TOKEN is required")
        if not self.keywords:
            errors.append(
                "THREADS_KEYWORDS must not be empty when Threads is enabled"
            )
        if self.poll_interval <= 0:
            errors.append("THREADS_POLL_INTERVAL must be positive")
        return errors


@dataclass(frozen=True)
class WienGvConfig:
    """Configuration for the Wien.gv.at petitions datasource.

    Attributes:
        url: Base URL for the petition platform.
        poll_interval: Seconds between poll cycles.
        user_agent: User-Agent header for HTTP requests.
        enabled: Whether the Wien.gv datasource is active.
    """

    url: str = "https://petitionen.wien.gv.at"
    poll_interval: int = 3600
    user_agent: str = "ViennaTalksBout/1.0"
    enabled: bool = False

    def validate(self) -> list[str]:
        """Return a list of validation error messages. Empty list means valid."""
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.url:
            errors.append("WIEN_GV_URL is required")
        if self.poll_interval <= 0:
            errors.append("WIEN_GV_POLL_INTERVAL must be positive")
        return errors


def load_threads_config() -> ThreadsConfig:
    """Load Threads datasource configuration from environment variables.

    Environment variables:
        THREADS_ENABLED: "true" to enable (default "false").
        THREADS_ACCESS_TOKEN: Meta API access token.
        THREADS_KEYWORDS: Comma-separated keywords (default "wien,vienna").
        THREADS_POLL_INTERVAL: Seconds between polls (default 300).
        THREADS_USER_AGENT: User-Agent header (default "ViennaTalksBout/1.0").

    Returns:
        A ThreadsConfig instance.

    Raises:
        ValueError: If the configuration is invalid when enabled.
    """
    enabled = os.environ.get("THREADS_ENABLED", "false").strip().lower() == "true"

    keywords_raw = os.environ.get("THREADS_KEYWORDS", "wien,vienna").strip()
    keywords = tuple(k.strip() for k in keywords_raw.split(",") if k.strip())

    poll_interval = int(os.environ.get("THREADS_POLL_INTERVAL", "300").strip())
    user_agent = os.environ.get("THREADS_USER_AGENT", "ViennaTalksBout/1.0").strip()

    config = ThreadsConfig(
        access_token=os.environ.get("THREADS_ACCESS_TOKEN", "").strip(),
        keywords=keywords,
        poll_interval=poll_interval,
        user_agent=user_agent,
        enabled=enabled,
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid Threads configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return config


def load_wien_gv_config() -> WienGvConfig:
    """Load Wien.gv.at petitions datasource configuration from environment variables.

    Environment variables:
        WIEN_GV_ENABLED: "true" to enable (default "false").
        WIEN_GV_URL: Petition platform URL (default "https://petitionen.wien.gv.at").
        WIEN_GV_POLL_INTERVAL: Seconds between polls (default 3600).
        WIEN_GV_USER_AGENT: User-Agent header (default "ViennaTalksBout/1.0").

    Returns:
        A WienGvConfig instance.

    Raises:
        ValueError: If the configuration is invalid when enabled.
    """
    enabled = os.environ.get("WIEN_GV_ENABLED", "false").strip().lower() == "true"

    config = WienGvConfig(
        url=os.environ.get(
            "WIEN_GV_URL", "https://petitionen.wien.gv.at"
        ).strip(),
        poll_interval=int(os.environ.get("WIEN_GV_POLL_INTERVAL", "3600").strip()),
        user_agent=os.environ.get(
            "WIEN_GV_USER_AGENT", "ViennaTalksBout/1.0"
        ).strip(),
        enabled=enabled,
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid Wien.gv configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return config


def load_lemmy_config() -> LemmyConfig:
    """Load Lemmy datasource configuration from environment variables.

    Environment variables:
        LEMMY_ENABLED: "true" to enable (default "false").
        LEMMY_INSTANCE: Instance hostname (default "feddit.org").
        LEMMY_COMMUNITIES: Comma-separated community names (default "austria,dach").
        LEMMY_POLL_INTERVAL: Seconds between polls (default 300).
        LEMMY_USER_AGENT: User-Agent header (default "ViennaTalksBout/1.0").

    Returns:
        A LemmyConfig instance.

    Raises:
        ValueError: If the configuration is invalid when enabled.
    """
    enabled = os.environ.get("LEMMY_ENABLED", "false").strip().lower() == "true"

    instance = os.environ.get("LEMMY_INSTANCE", "feddit.org").strip()

    communities_raw = os.environ.get("LEMMY_COMMUNITIES", "austria,dach").strip()
    communities = tuple(
        c.strip() for c in communities_raw.split(",") if c.strip()
    )

    poll_interval = int(os.environ.get("LEMMY_POLL_INTERVAL", "300").strip())
    user_agent = os.environ.get("LEMMY_USER_AGENT", "ViennaTalksBout/1.0").strip()

    config = LemmyConfig(
        instance=instance,
        communities=communities,
        poll_interval=poll_interval,
        user_agent=user_agent,
        enabled=enabled,
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid Lemmy configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return config


def _load_lemmy_instance(prefix: str) -> LemmyConfig | None:
    """Load a single Lemmy instance config from env vars with the given prefix.

    Args:
        prefix: Environment variable prefix, e.g. ``"LEMMY_"`` or ``"LEMMY_2_"``.

    Returns:
        A LemmyConfig if the instance is configured, or None if not.
    """
    instance = os.environ.get(f"{prefix}INSTANCE", "").strip()
    if not instance:
        return None

    enabled_raw = os.environ.get(f"{prefix}ENABLED", "true").strip().lower()
    enabled = enabled_raw == "true"

    communities_raw = os.environ.get(f"{prefix}COMMUNITIES", "").strip()
    communities = tuple(
        c.strip() for c in communities_raw.split(",") if c.strip()
    ) if communities_raw else ()

    poll_interval = int(os.environ.get(f"{prefix}POLL_INTERVAL", "300").strip())
    user_agent = os.environ.get(
        f"{prefix}USER_AGENT", "ViennaTalksBout/1.0"
    ).strip()

    return LemmyConfig(
        instance=instance,
        communities=communities,
        poll_interval=poll_interval,
        user_agent=user_agent,
        enabled=enabled,
    )


def load_lemmy_configs() -> list[LemmyConfig]:
    """Load one or more Lemmy instance configurations.

    The primary instance uses the standard ``LEMMY_*`` env vars.
    Additional instances use numbered prefixes: ``LEMMY_2_*``,
    ``LEMMY_3_*``, etc.

    If no ``LEMMY_ENABLED`` is set to ``"true"`` (or no ``LEMMY_INSTANCE``
    is set), returns an empty list. Each numbered instance defaults to
    enabled unless its own ``LEMMY_N_ENABLED`` is ``"false"``.

    Environment variables (primary):
        LEMMY_ENABLED: "true" to enable (default "false").
        LEMMY_INSTANCE: Instance hostname (default "feddit.org").
        LEMMY_COMMUNITIES: Comma-separated community names (default "austria,dach").
        LEMMY_POLL_INTERVAL: Seconds between polls (default 300).
        LEMMY_USER_AGENT: User-Agent header (default "ViennaTalksBout/1.0").

    Additional instances (numbered):
        LEMMY_2_INSTANCE, LEMMY_2_COMMUNITIES, LEMMY_2_POLL_INTERVAL, etc.
        LEMMY_3_INSTANCE, LEMMY_3_COMMUNITIES, ...

    Returns:
        A list of validated, enabled LemmyConfig instances (may be empty).

    Raises:
        ValueError: If any configured instance has invalid settings.
    """
    configs: list[LemmyConfig] = []

    # Primary instance — use load_lemmy_config() for backwards compatibility
    primary_enabled = (
        os.environ.get("LEMMY_ENABLED", "false").strip().lower() == "true"
    )
    if primary_enabled:
        primary = load_lemmy_config()  # validates and raises on error
        configs.append(primary)

    # Scan for numbered instances (LEMMY_2_*, LEMMY_3_*, …)
    n = 2
    while True:
        prefix = f"LEMMY_{n}_"
        config = _load_lemmy_instance(prefix)
        if config is None:
            break

        errors = config.validate()
        if errors:
            raise ValueError(
                f"Invalid Lemmy instance {n} configuration:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        if config.enabled:
            configs.append(config)
        n += 1

    return configs


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


def load_reddit_config() -> RedditConfig:
    """Load Reddit datasource configuration from environment variables.

    Environment variables:
        REDDIT_ENABLED: "true" to enable (default "false").
        REDDIT_CLIENT_ID: OAuth client ID.
        REDDIT_CLIENT_SECRET: OAuth client secret.
        REDDIT_USERNAME: Reddit account username.
        REDDIT_PASSWORD: Reddit account password.
        REDDIT_SUBREDDITS: Comma-separated subreddit names (default "wien,austria").
        REDDIT_POLL_INTERVAL: Seconds between polls (default 60).
        REDDIT_INCLUDE_COMMENTS: "true" to also poll comments (default "true").

    Returns:
        A RedditConfig instance.

    Raises:
        ValueError: If the configuration is invalid when enabled.
    """
    enabled = os.environ.get("REDDIT_ENABLED", "false").strip().lower() == "true"

    subreddits_raw = os.environ.get("REDDIT_SUBREDDITS", "wien,austria").strip()
    subreddits = tuple(s.strip() for s in subreddits_raw.split(",") if s.strip())

    include_comments = (
        os.environ.get("REDDIT_INCLUDE_COMMENTS", "true").strip().lower() == "true"
    )

    config = RedditConfig(
        client_id=os.environ.get("REDDIT_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("REDDIT_CLIENT_SECRET", "").strip(),
        username=os.environ.get("REDDIT_USERNAME", "").strip(),
        password=os.environ.get("REDDIT_PASSWORD", "").strip(),
        subreddits=subreddits,
        poll_interval=int(os.environ.get("REDDIT_POLL_INTERVAL", "60").strip()),
        enabled=enabled,
        include_comments=include_comments,
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid Reddit configuration:\n" + "\n".join(f"  - {e}" for e in errors)
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


def load_mastodon_configs(
    env_path: str | Path | None = None,
) -> list[MastodonConfig]:
    """Load one or more Mastodon instance configurations.

    The primary instance uses the standard ``MASTODON_*`` env vars.
    Additional instances use numbered prefixes: ``MASTODON_2_*``,
    ``MASTODON_3_*``, etc.

    If no primary ``MASTODON_INSTANCE_URL`` is set, returns an empty list
    (Mastodon is not configured). This allows running the pipeline with
    only other datasources (RSS, Lemmy, Reddit).

    Args:
        env_path: Optional path to a .env file.

    Returns:
        A list of validated MastodonConfig instances (may be empty).

    Raises:
        ValueError: If a Mastodon instance URL is set but the remaining
            credentials are missing or invalid.
    """
    if env_path is not None:
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    # If no primary instance URL is set, Mastodon is not configured
    primary_url = os.environ.get("MASTODON_INSTANCE_URL", "").strip()
    if not primary_url:
        return []

    primary = MastodonConfig(
        instance_url=primary_url,
        client_id=os.environ.get("MASTODON_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("MASTODON_CLIENT_SECRET", "").strip(),
        access_token=os.environ.get("MASTODON_ACCESS_TOKEN", "").strip(),
    )

    errors = primary.validate()
    if errors:
        raise ValueError(
            "Invalid Mastodon configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    configs = [primary]

    # Scan for numbered instances (MASTODON_2_*, MASTODON_3_*, …)
    n = 2
    while True:
        prefix = f"MASTODON_{n}_"
        instance_url = os.environ.get(f"{prefix}INSTANCE_URL", "").strip()
        if not instance_url:
            break

        config = MastodonConfig(
            instance_url=instance_url,
            client_id=os.environ.get(f"{prefix}CLIENT_ID", "").strip(),
            client_secret=os.environ.get(f"{prefix}CLIENT_SECRET", "").strip(),
            access_token=os.environ.get(f"{prefix}ACCESS_TOKEN", "").strip(),
        )

        errors = config.validate()
        if errors:
            raise ValueError(
                f"Invalid Mastodon instance {n} configuration:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        configs.append(config)
        n += 1

    return configs


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
        backend=os.environ.get("EXTRACTOR_BACKEND", "sdk").strip().lower(),
    )

    errors = config.validate()
    if errors:
        raise ValueError(
            "Invalid extractor configuration:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return config
