"""Tests for viennatalksbout.config — configuration loading and validation."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from viennatalksbout.config import (
    DEFAULT_EXTRACTOR_MODEL,
    ExtractorConfig,
    MastodonConfig,
    load_config,
    load_extractor_config,
)


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


# ===========================================================================
# ExtractorConfig validation
# ===========================================================================


class TestExtractorConfigValidation:
    """Tests for ExtractorConfig.validate()."""

    def test_valid_config_has_no_errors(self):
        config = ExtractorConfig(api_key="sk-ant-test-key")
        assert config.validate() == []

    def test_valid_config_with_custom_model(self):
        config = ExtractorConfig(
            api_key="sk-ant-test-key",
            model="claude-sonnet-4-5-20250929",
        )
        assert config.validate() == []

    def test_missing_api_key(self):
        config = ExtractorConfig(api_key="")
        errors = config.validate()
        assert any("ANTHROPIC_API_KEY is required" in e for e in errors)

    def test_empty_model(self):
        config = ExtractorConfig(api_key="sk-ant-test-key", model="")
        errors = config.validate()
        assert any("ANTHROPIC_MODEL must not be empty" in e for e in errors)

    def test_default_model(self):
        config = ExtractorConfig(api_key="sk-ant-test-key")
        assert config.model == DEFAULT_EXTRACTOR_MODEL

    def test_config_is_frozen(self):
        config = ExtractorConfig(api_key="sk-ant-test-key")
        with pytest.raises(AttributeError):
            config.api_key = "other"  # type: ignore[misc]

    def test_missing_api_key_and_empty_model(self):
        config = ExtractorConfig(api_key="", model="")
        errors = config.validate()
        assert len(errors) == 2


# ===========================================================================
# load_extractor_config
# ===========================================================================


class TestLoadExtractorConfig:
    """Tests for load_extractor_config() — loading from .env files and environment."""

    def test_load_from_env_file(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test-key-123\n")
        config = load_extractor_config(env_file)
        assert config.api_key == "sk-ant-test-key-123"
        assert config.model == DEFAULT_EXTRACTOR_MODEL

    def test_load_with_custom_model(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ANTHROPIC_API_KEY=sk-ant-test-key\n"
            "ANTHROPIC_MODEL=claude-sonnet-4-5-20250929\n"
        )
        config = load_extractor_config(env_file)
        assert config.model == "claude-sonnet-4-5-20250929"

    def test_load_strips_whitespace(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY= sk-ant-test-key \n")
        config = load_extractor_config(env_file)
        assert config.api_key == "sk-ant-test-key"

    def test_load_raises_on_missing_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with pytest.raises(ValueError, match="Invalid extractor configuration"):
            load_extractor_config(env_file)

    def test_load_from_environment_variables(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
        config = load_extractor_config(Path("/nonexistent/.env"))
        assert config.api_key == "sk-ant-env-key"
        assert config.model == "claude-sonnet-4-5-20250929"

    def test_default_model_when_env_not_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test-key\n")
        config = load_extractor_config(env_file)
        assert config.model == DEFAULT_EXTRACTOR_MODEL

    def test_error_message_lists_missing_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with pytest.raises(ValueError) as exc_info:
            load_extractor_config(env_file)
        assert "ANTHROPIC_API_KEY is required" in str(exc_info.value)
