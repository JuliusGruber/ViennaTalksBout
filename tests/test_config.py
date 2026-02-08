"""Tests for talkbout.config — configuration loading and validation."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from talkbout.config import MastodonConfig, load_config


class TestMastodonConfigValidation:
    """Tests for MastodonConfig.validate()."""

    def test_valid_config_has_no_errors(self):
        config = MastodonConfig(
            instance_url="https://wien.rocks",
            client_id="abc123",
            client_secret="secret456",
            access_token="token789",
        )
        assert config.validate() == []

    def test_missing_instance_url(self):
        config = MastodonConfig(
            instance_url="",
            client_id="abc123",
            client_secret="secret456",
            access_token="token789",
        )
        errors = config.validate()
        assert any("MASTODON_INSTANCE_URL is required" in e for e in errors)

    def test_instance_url_must_be_https(self):
        config = MastodonConfig(
            instance_url="http://wien.rocks",
            client_id="abc123",
            client_secret="secret456",
            access_token="token789",
        )
        errors = config.validate()
        assert any("must start with https://" in e for e in errors)

    def test_missing_client_id(self):
        config = MastodonConfig(
            instance_url="https://wien.rocks",
            client_id="",
            client_secret="secret456",
            access_token="token789",
        )
        errors = config.validate()
        assert any("MASTODON_CLIENT_ID is required" in e for e in errors)

    def test_missing_client_secret(self):
        config = MastodonConfig(
            instance_url="https://wien.rocks",
            client_id="abc123",
            client_secret="",
            access_token="token789",
        )
        errors = config.validate()
        assert any("MASTODON_CLIENT_SECRET is required" in e for e in errors)

    def test_missing_access_token(self):
        config = MastodonConfig(
            instance_url="https://wien.rocks",
            client_id="abc123",
            client_secret="secret456",
            access_token="",
        )
        errors = config.validate()
        assert any("MASTODON_ACCESS_TOKEN is required" in e for e in errors)

    def test_multiple_missing_fields(self):
        config = MastodonConfig(
            instance_url="",
            client_id="",
            client_secret="",
            access_token="",
        )
        errors = config.validate()
        assert len(errors) == 4

    def test_config_is_frozen(self):
        config = MastodonConfig(
            instance_url="https://wien.rocks",
            client_id="abc123",
            client_secret="secret456",
            access_token="token789",
        )
        with pytest.raises(AttributeError):
            config.instance_url = "https://other.instance"  # type: ignore[misc]


class TestLoadConfig:
    """Tests for load_config() — loading from .env files and environment."""

    def test_load_from_env_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            textwrap.dedent("""\
                MASTODON_INSTANCE_URL=https://wien.rocks
                MASTODON_CLIENT_ID=test_client_id
                MASTODON_CLIENT_SECRET=test_client_secret
                MASTODON_ACCESS_TOKEN=test_access_token
            """)
        )
        config = load_config(env_file)
        assert config.instance_url == "https://wien.rocks"
        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.access_token == "test_access_token"

    def test_load_from_env_file_strips_whitespace(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            textwrap.dedent("""\
                MASTODON_INSTANCE_URL= https://wien.rocks
                MASTODON_CLIENT_ID= test_client_id
                MASTODON_CLIENT_SECRET= test_client_secret
                MASTODON_ACCESS_TOKEN= test_access_token
            """)
        )
        config = load_config(env_file)
        assert config.instance_url == "https://wien.rocks"
        assert config.client_id == "test_client_id"

    def test_load_raises_on_missing_required_fields(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        # Clear any env vars that might leak from the outer environment
        for key in [
            "MASTODON_INSTANCE_URL",
            "MASTODON_CLIENT_ID",
            "MASTODON_CLIENT_SECRET",
            "MASTODON_ACCESS_TOKEN",
        ]:
            monkeypatch.delenv(key, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("")  # empty file

        with pytest.raises(ValueError, match="Invalid Mastodon configuration"):
            load_config(env_file)

    def test_load_raises_with_http_url(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            textwrap.dedent("""\
                MASTODON_INSTANCE_URL=http://wien.rocks
                MASTODON_CLIENT_ID=test_client_id
                MASTODON_CLIENT_SECRET=test_client_secret
                MASTODON_ACCESS_TOKEN=test_access_token
            """)
        )
        with pytest.raises(ValueError, match="must start with https://"):
            load_config(env_file)

    def test_load_from_environment_variables(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MASTODON_INSTANCE_URL", "https://wien.rocks")
        monkeypatch.setenv("MASTODON_CLIENT_ID", "env_client_id")
        monkeypatch.setenv("MASTODON_CLIENT_SECRET", "env_client_secret")
        monkeypatch.setenv("MASTODON_ACCESS_TOKEN", "env_access_token")

        # Pass a nonexistent .env so only env vars are used
        config = load_config(Path("/nonexistent/.env"))
        assert config.client_id == "env_client_id"
        assert config.access_token == "env_access_token"

    def test_error_message_lists_all_missing_fields(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        for key in [
            "MASTODON_INSTANCE_URL",
            "MASTODON_CLIENT_ID",
            "MASTODON_CLIENT_SECRET",
            "MASTODON_ACCESS_TOKEN",
        ]:
            monkeypatch.delenv(key, raising=False)

        env_file = tmp_path / ".env"
        env_file.write_text("")

        with pytest.raises(ValueError) as exc_info:
            load_config(env_file)

        error_msg = str(exc_info.value)
        assert "MASTODON_INSTANCE_URL is required" in error_msg
        assert "MASTODON_CLIENT_ID is required" in error_msg
        assert "MASTODON_CLIENT_SECRET is required" in error_msg
        assert "MASTODON_ACCESS_TOKEN is required" in error_msg
