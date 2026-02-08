"""Integration tests for talkbout.mastodon.auth — real calls to wien.rocks."""

from __future__ import annotations

import pytest

from talkbout.config import MastodonConfig
from talkbout.mastodon.auth import verify_instance


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
