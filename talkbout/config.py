"""Configuration loading and validation for TalkBout.

Loads settings from environment variables (with optional .env file support).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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
