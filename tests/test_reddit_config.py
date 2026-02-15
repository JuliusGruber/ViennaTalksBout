"""Tests for Reddit configuration in viennatalksbout.config."""

from __future__ import annotations

import pytest

from viennatalksbout.config import RedditConfig, load_reddit_config


# ===========================================================================
# RedditConfig dataclass
# ===========================================================================


class TestRedditConfig:
    """Tests for the RedditConfig dataclass."""

    def test_create_with_defaults(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
        )
        assert config.client_id == "cid"
        assert config.subreddits == ("wien", "austria")
        assert config.poll_interval == 60
        assert config.enabled is False
        assert config.include_comments is True

    def test_user_agent_auto_generated(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="mybot",
            password="pass",
        )
        assert "mybot" in config.user_agent
        assert "ViennaTalksBout" in config.user_agent

    def test_custom_user_agent(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            user_agent="CustomAgent/2.0",
        )
        assert config.user_agent == "CustomAgent/2.0"

    def test_frozen(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
        )
        with pytest.raises(AttributeError):
            config.client_id = "other"  # type: ignore[misc]


# ===========================================================================
# RedditConfig validation
# ===========================================================================


class TestRedditConfigValidation:
    """Tests for RedditConfig.validate()."""

    def test_valid(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            enabled=True,
        )
        assert config.validate() == []

    def test_disabled_skips_validation(self):
        config = RedditConfig(
            client_id="",
            client_secret="",
            username="",
            password="",
            enabled=False,
        )
        assert config.validate() == []

    def test_missing_client_id(self):
        config = RedditConfig(
            client_id="",
            client_secret="csec",
            username="user",
            password="pass",
            enabled=True,
        )
        errors = config.validate()
        assert any("REDDIT_CLIENT_ID" in e for e in errors)

    def test_missing_client_secret(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="",
            username="user",
            password="pass",
            enabled=True,
        )
        errors = config.validate()
        assert any("REDDIT_CLIENT_SECRET" in e for e in errors)

    def test_missing_username(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="",
            password="pass",
            enabled=True,
        )
        errors = config.validate()
        assert any("REDDIT_USERNAME" in e for e in errors)

    def test_missing_password(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="",
            enabled=True,
        )
        errors = config.validate()
        assert any("REDDIT_PASSWORD" in e for e in errors)

    def test_empty_subreddits(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            subreddits=(),
            enabled=True,
        )
        errors = config.validate()
        assert any("REDDIT_SUBREDDITS" in e for e in errors)

    def test_negative_poll_interval(self):
        config = RedditConfig(
            client_id="cid",
            client_secret="csec",
            username="user",
            password="pass",
            poll_interval=-1,
            enabled=True,
        )
        errors = config.validate()
        assert any("REDDIT_POLL_INTERVAL" in e for e in errors)


# ===========================================================================
# load_reddit_config
# ===========================================================================


class TestLoadRedditConfig:
    """Tests for load_reddit_config()."""

    def _clear_reddit_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for key in [
            "REDDIT_ENABLED",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "REDDIT_USERNAME",
            "REDDIT_PASSWORD",
            "REDDIT_SUBREDDITS",
            "REDDIT_POLL_INTERVAL",
            "REDDIT_INCLUDE_COMMENTS",
        ]:
            monkeypatch.delenv(key, raising=False)

    def test_default_disabled(self, monkeypatch: pytest.MonkeyPatch):
        self._clear_reddit_env(monkeypatch)
        config = load_reddit_config()
        assert config.enabled is False

    def test_enabled_with_credentials(self, monkeypatch: pytest.MonkeyPatch):
        self._clear_reddit_env(monkeypatch)
        monkeypatch.setenv("REDDIT_ENABLED", "true")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")
        monkeypatch.setenv("REDDIT_USERNAME", "user")
        monkeypatch.setenv("REDDIT_PASSWORD", "pass")
        config = load_reddit_config()
        assert config.enabled is True
        assert config.client_id == "cid"
        assert config.subreddits == ("wien", "austria")
        assert config.poll_interval == 60
        assert config.include_comments is True

    def test_custom_subreddits(self, monkeypatch: pytest.MonkeyPatch):
        self._clear_reddit_env(monkeypatch)
        monkeypatch.setenv("REDDIT_ENABLED", "true")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")
        monkeypatch.setenv("REDDIT_USERNAME", "user")
        monkeypatch.setenv("REDDIT_PASSWORD", "pass")
        monkeypatch.setenv("REDDIT_SUBREDDITS", "wien, vienna, austria")
        config = load_reddit_config()
        assert config.subreddits == ("wien", "vienna", "austria")

    def test_custom_poll_interval(self, monkeypatch: pytest.MonkeyPatch):
        self._clear_reddit_env(monkeypatch)
        monkeypatch.setenv("REDDIT_ENABLED", "true")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")
        monkeypatch.setenv("REDDIT_USERNAME", "user")
        monkeypatch.setenv("REDDIT_PASSWORD", "pass")
        monkeypatch.setenv("REDDIT_POLL_INTERVAL", "120")
        config = load_reddit_config()
        assert config.poll_interval == 120

    def test_include_comments_false(self, monkeypatch: pytest.MonkeyPatch):
        self._clear_reddit_env(monkeypatch)
        monkeypatch.setenv("REDDIT_ENABLED", "true")
        monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")
        monkeypatch.setenv("REDDIT_USERNAME", "user")
        monkeypatch.setenv("REDDIT_PASSWORD", "pass")
        monkeypatch.setenv("REDDIT_INCLUDE_COMMENTS", "false")
        config = load_reddit_config()
        assert config.include_comments is False

    def test_invalid_when_enabled_raises(self, monkeypatch: pytest.MonkeyPatch):
        self._clear_reddit_env(monkeypatch)
        monkeypatch.setenv("REDDIT_ENABLED", "true")
        # Missing all credentials
        with pytest.raises(ValueError, match="Invalid Reddit configuration"):
            load_reddit_config()
