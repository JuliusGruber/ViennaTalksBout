"""Tests for viennatalksbout.mastodon.auth — OAuth registration and instance verification."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
import requests

from viennatalksbout.config import MastodonConfig
from viennatalksbout.mastodon.auth import (
    OAuthApp,
    InstanceInfo,
    register_app,
    get_authorization_url,
    exchange_code_for_token,
    verify_instance,
    verify_credentials,
    OOB_REDIRECT_URI,
    DEFAULT_SCOPES,
)


def _make_config(**overrides: str) -> MastodonConfig:
    """Create a MastodonConfig with sensible test defaults."""
    defaults = {
        "instance_url": "https://wien.rocks",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "access_token": "test_access_token",
    }
    defaults.update(overrides)
    return MastodonConfig(**defaults)


class TestRegisterApp:
    """Tests for register_app()."""

    @patch("viennatalksbout.mastodon.auth.requests.post")
    def test_successful_registration(self, mock_post: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "client_id": "returned_client_id",
            "client_secret": "returned_client_secret",
            "id": "12345",
            "name": "ViennaTalksBout",
            "redirect_uri": OOB_REDIRECT_URI,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        app = register_app("https://wien.rocks")

        assert app.client_id == "returned_client_id"
        assert app.client_secret == "returned_client_secret"
        assert app.instance_url == "https://wien.rocks"

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://wien.rocks/api/v1/apps"
        assert call_args[1]["json"]["client_name"] == "ViennaTalksBout"
        assert call_args[1]["json"]["scopes"] == DEFAULT_SCOPES

    @patch("viennatalksbout.mastodon.auth.requests.post")
    def test_registration_with_custom_params(self, mock_post: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "client_id": "cid",
            "client_secret": "csec",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        register_app(
            "https://wien.rocks",
            app_name="CustomApp",
            scopes="read write",
            website="https://viennatalksbout.example.com",
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["client_name"] == "CustomApp"
        assert payload["scopes"] == "read write"
        assert payload["website"] == "https://viennatalksbout.example.com"

    @patch("viennatalksbout.mastodon.auth.requests.post")
    def test_registration_strips_trailing_slash(self, mock_post: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "client_id": "cid",
            "client_secret": "csec",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        app = register_app("https://wien.rocks/")
        assert app.instance_url == "https://wien.rocks"
        assert mock_post.call_args[0][0] == "https://wien.rocks/api/v1/apps"

    @patch("viennatalksbout.mastodon.auth.requests.post")
    def test_registration_http_error(self, mock_post: MagicMock):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("422 Unprocessable")
        mock_post.return_value = mock_response

        with pytest.raises(requests.HTTPError):
            register_app("https://wien.rocks")


class TestGetAuthorizationUrl:
    """Tests for get_authorization_url()."""

    def test_builds_correct_url(self):
        app = OAuthApp(
            client_id="my_client_id",
            client_secret="my_secret",
            instance_url="https://wien.rocks",
        )
        url = get_authorization_url(app)

        assert url.startswith("https://wien.rocks/oauth/authorize")
        assert "client_id=my_client_id" in url
        assert "scope=read" in url
        assert f"redirect_uri={OOB_REDIRECT_URI}" in url
        assert "response_type=code" in url

    def test_custom_scopes(self):
        app = OAuthApp(
            client_id="cid",
            client_secret="csec",
            instance_url="https://wien.rocks",
        )
        url = get_authorization_url(app, scopes="read write")
        assert "scope=read write" in url


class TestExchangeCodeForToken:
    """Tests for exchange_code_for_token()."""

    @patch("viennatalksbout.mastodon.auth.requests.post")
    def test_successful_exchange(self, mock_post: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "scope": "read",
            "created_at": 1700000000,
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        app = OAuthApp(
            client_id="cid",
            client_secret="csec",
            instance_url="https://wien.rocks",
        )
        token = exchange_code_for_token(app, "auth_code_123")

        assert token == "new_access_token"

        call_args = mock_post.call_args
        assert call_args[0][0] == "https://wien.rocks/oauth/token"
        payload = call_args[1]["json"]
        assert payload["client_id"] == "cid"
        assert payload["client_secret"] == "csec"
        assert payload["code"] == "auth_code_123"
        assert payload["grant_type"] == "authorization_code"
        assert payload["redirect_uri"] == OOB_REDIRECT_URI

    @patch("viennatalksbout.mastodon.auth.requests.post")
    def test_exchange_http_error(self, mock_post: MagicMock):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        mock_post.return_value = mock_response

        app = OAuthApp(
            client_id="cid",
            client_secret="csec",
            instance_url="https://wien.rocks",
        )
        with pytest.raises(requests.HTTPError):
            exchange_code_for_token(app, "bad_code")


class TestVerifyInstance:
    """Tests for verify_instance()."""

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_successful_verification(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "uri": "wien.rocks",
            "title": "Wien Rocks",
            "version": "4.5.5",
            "short_description": "Vienna's Mastodon instance",
            "description": "Full description here",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        config = _make_config()
        info = verify_instance(config)

        assert info.uri == "wien.rocks"
        assert info.title == "Wien Rocks"
        assert info.version == "4.5.5"
        assert info.description == "Vienna's Mastodon instance"

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://wien.rocks/api/v1/instance"
        assert "Bearer test_access_token" in call_args[1]["headers"]["Authorization"]

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_uses_full_description_as_fallback(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "uri": "wien.rocks",
            "title": "Wien Rocks",
            "version": "4.5.5",
            "description": "Fallback description",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        config = _make_config()
        info = verify_instance(config)
        assert info.description == "Fallback description"

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_handles_missing_fields(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        config = _make_config()
        info = verify_instance(config)
        assert info.uri == ""
        assert info.title == ""
        assert info.version == ""
        assert info.description == ""

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_verify_instance_http_error(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("503 Service Unavailable")
        mock_get.return_value = mock_response

        config = _make_config()
        with pytest.raises(requests.HTTPError):
            verify_instance(config)

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_strips_trailing_slash_from_url(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {"uri": "x", "title": "x", "version": "x"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        config = _make_config(instance_url="https://wien.rocks/")
        verify_instance(config)
        assert mock_get.call_args[0][0] == "https://wien.rocks/api/v1/instance"


class TestVerifyCredentials:
    """Tests for verify_credentials()."""

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_valid_credentials(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.json.return_value = {"name": "ViennaTalksBout", "vapid_key": "..."}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        config = _make_config()
        assert verify_credentials(config) is True

        call_args = mock_get.call_args
        assert call_args[0][0] == "https://wien.rocks/api/v1/apps/verify_credentials"

    @patch("viennatalksbout.mastodon.auth.requests.get")
    def test_invalid_credentials(self, mock_get: MagicMock):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        mock_get.return_value = mock_response

        config = _make_config()
        with pytest.raises(requests.HTTPError):
            verify_credentials(config)
