"""Tests for RSS configuration in viennatalksbout.config."""

from __future__ import annotations

import pytest

from viennatalksbout.config import (
    DEFAULT_RSS_FEEDS,
    FeedConfig,
    RssConfig,
    load_rss_config,
)


# ===========================================================================
# FeedConfig
# ===========================================================================


class TestFeedConfig:
    """Tests for the FeedConfig dataclass."""

    def test_create(self):
        feed = FeedConfig(url="https://example.com/rss", name="example")
        assert feed.url == "https://example.com/rss"
        assert feed.name == "example"
        assert feed.language == "de"

    def test_custom_language(self):
        feed = FeedConfig(url="https://example.com/rss", name="ex", language="en")
        assert feed.language == "en"

    def test_frozen(self):
        feed = FeedConfig(url="https://example.com/rss", name="example")
        with pytest.raises(AttributeError):
            feed.url = "other"  # type: ignore[misc]


# ===========================================================================
# RssConfig validation
# ===========================================================================


class TestRssConfigValidation:
    """Tests for RssConfig.validate()."""

    def test_valid(self):
        config = RssConfig(
            feeds=(FeedConfig(url="https://rss.orf.at/wien.xml", name="orf-wien"),),
            poll_interval=600,
            enabled=True,
        )
        assert config.validate() == []

    def test_empty_feeds_when_enabled(self):
        config = RssConfig(feeds=(), enabled=True)
        errors = config.validate()
        assert any("RSS_FEEDS" in e for e in errors)

    def test_negative_interval(self):
        config = RssConfig(
            feeds=(FeedConfig(url="https://x.com/rss", name="x"),),
            poll_interval=-1,
            enabled=True,
        )
        errors = config.validate()
        assert any("RSS_POLL_INTERVAL" in e for e in errors)

    def test_disabled_skips_validation(self):
        config = RssConfig(feeds=(), poll_interval=-1, enabled=False)
        assert config.validate() == []


# ===========================================================================
# load_rss_config
# ===========================================================================


class TestLoadRssConfig:
    """Tests for load_rss_config()."""

    def test_default_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("RSS_ENABLED", raising=False)
        monkeypatch.delenv("RSS_FEEDS", raising=False)
        monkeypatch.delenv("RSS_POLL_INTERVAL", raising=False)
        monkeypatch.delenv("RSS_USER_AGENT", raising=False)
        config = load_rss_config()
        assert config.enabled is False

    def test_enabled_with_defaults(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RSS_ENABLED", "true")
        monkeypatch.delenv("RSS_FEEDS", raising=False)
        monkeypatch.delenv("RSS_POLL_INTERVAL", raising=False)
        monkeypatch.delenv("RSS_USER_AGENT", raising=False)
        config = load_rss_config()
        assert config.enabled is True
        assert len(config.feeds) == len(DEFAULT_RSS_FEEDS)
        assert config.poll_interval == 600
        assert config.user_agent == "ViennaTalksBout/1.0"

    def test_custom_feeds(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RSS_ENABLED", "true")
        monkeypatch.setenv(
            "RSS_FEEDS", "https://a.com/rss|feed-a, https://b.com/rss|feed-b"
        )
        config = load_rss_config()
        assert len(config.feeds) == 2
        assert config.feeds[0].url == "https://a.com/rss"
        assert config.feeds[0].name == "feed-a"
        assert config.feeds[1].url == "https://b.com/rss"
        assert config.feeds[1].name == "feed-b"

    def test_custom_interval(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RSS_ENABLED", "true")
        monkeypatch.setenv("RSS_POLL_INTERVAL", "300")
        monkeypatch.delenv("RSS_FEEDS", raising=False)
        config = load_rss_config()
        assert config.poll_interval == 300

    def test_custom_user_agent(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RSS_ENABLED", "true")
        monkeypatch.setenv("RSS_USER_AGENT", "MyBot/2.0")
        monkeypatch.delenv("RSS_FEEDS", raising=False)
        config = load_rss_config()
        assert config.user_agent == "MyBot/2.0"

    def test_invalid_when_enabled_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("RSS_ENABLED", "true")
        monkeypatch.setenv("RSS_FEEDS", "")
        monkeypatch.setenv("RSS_POLL_INTERVAL", "-1")
        with pytest.raises(ValueError, match="Invalid RSS configuration"):
            load_rss_config()
