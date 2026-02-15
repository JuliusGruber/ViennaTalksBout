"""Integration tests for the Reddit datasource.

These tests make real HTTP calls to the Reddit API and require valid
REDDIT_* environment variables to be set.

Run with: python -m pytest tests/test_reddit_integration.py -v -m integration
"""

from __future__ import annotations

import os

import pytest

from viennatalksbout.config import RedditConfig, load_reddit_config
from viennatalksbout.datasource import Post


@pytest.mark.integration
class TestRedditIntegration:
    """Integration tests that make real calls to the Reddit API."""

    @pytest.fixture(autouse=True)
    def _require_credentials(self):
        """Skip if Reddit credentials are not available."""
        required = [
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
            "REDDIT_USERNAME",
            "REDDIT_PASSWORD",
        ]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            pytest.skip(
                f"Reddit credentials not set: {', '.join(missing)}"
            )

    def test_fetch_submissions_from_wien(self):
        """Verify we can connect and fetch posts from r/wien."""
        import praw

        config = RedditConfig(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            username=os.environ["REDDIT_USERNAME"],
            password=os.environ["REDDIT_PASSWORD"],
            subreddits=("wien",),
            enabled=True,
        )

        reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            username=config.username,
            password=config.password,
            user_agent=config.user_agent,
        )

        subreddit = reddit.subreddit("wien")
        submissions = list(subreddit.new(limit=5))

        assert len(submissions) > 0
        for sub in submissions:
            assert sub.title  # Submissions should have titles
            assert sub.fullname.startswith("t3_")

    def test_parse_real_submissions(self):
        """Verify parse_submission works with real PRAW objects."""
        import praw

        from viennatalksbout.reddit.datasource import (
            parse_submission,
            validate_submission,
        )

        config = RedditConfig(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            username=os.environ["REDDIT_USERNAME"],
            password=os.environ["REDDIT_PASSWORD"],
            subreddits=("wien",),
            enabled=True,
        )

        reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            username=config.username,
            password=config.password,
            user_agent=config.user_agent,
        )

        subreddit = reddit.subreddit("wien")
        submissions = list(subreddit.new(limit=5))
        parsed_count = 0

        for sub in submissions:
            if validate_submission(sub):
                post = parse_submission(sub, "reddit:wien")
                assert isinstance(post, Post)
                assert post.id.startswith("reddit:t3_")
                assert post.text
                assert post.language == "de"
                assert post.source == "reddit:wien"
                assert post.created_at is not None
                parsed_count += 1

        assert parsed_count > 0, "Expected at least one valid submission"
