"""Integration tests for viennatalksbout.mastodon.auth — real calls to wien.rocks."""

from __future__ import annotations

import pytest
import requests

from viennatalksbout.config import MastodonConfig
from viennatalksbout.mastodon.auth import verify_instance, REQUEST_TIMEOUT


@pytest.mark.integration
class TestVerifyInstanceLive:
    """Hit the real wien.rocks /api/v1/instance endpoint."""

    def test_returns_real_instance_info(self):
        # The /api/v1/instance endpoint is public; the token is ignored.
        config = MastodonConfig(
            instance_url="https://wien.rocks",
            client_id="unused",
            client_secret="unused",
            access_token="unused",
        )

        info = verify_instance(config)

        assert info.uri, "uri should not be empty"
        assert info.title, "title should not be empty"
        assert info.version, "version should not be empty"


@pytest.mark.integration
class TestPublicTimelineLive:
    """Fetch real posts from the wien.rocks public:local timeline."""

    def test_receives_user_post_content(self):
        url = "https://wien.rocks/api/v1/timelines/public"
        params = {"local": "true", "limit": 5}

        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        posts = response.json()

        assert isinstance(posts, list), "response should be a list"
        assert len(posts) > 0, "should receive at least one post"

        for post in posts:
            # Every post must have an id and a created_at timestamp
            assert post["id"], "post should have a non-empty id"
            assert post["created_at"], "post should have a created_at timestamp"

            # Content is HTML — it should be present on original posts
            if post["reblog"] is None:
                assert "content" in post, "original post should have a content field"

            # Visibility must be public (we requested the public timeline)
            assert post["visibility"] == "public"

            # Account info should be present
            account = post["account"]
            assert account["id"], "account should have an id"
            assert account["username"], "account should have a username"
