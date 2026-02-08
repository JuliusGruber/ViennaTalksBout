"""OAuth registration and instance verification for Mastodon.

Handles:
- Registering an OAuth application on a Mastodon instance
- Generating an authorization URL for the user
- Exchanging an authorization code for an access token
- Verifying instance connectivity
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from talkbout.config import MastodonConfig

# Redirect URI for local/CLI OAuth flow (out-of-band)
OOB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"

# Scopes needed for reading the public:local stream
DEFAULT_SCOPES = "read"

# Timeout for HTTP requests in seconds
REQUEST_TIMEOUT = 15


@dataclass(frozen=True)
class OAuthApp:
    """Represents a registered OAuth application on a Mastodon instance."""

    client_id: str
    client_secret: str
    instance_url: str


@dataclass(frozen=True)
class InstanceInfo:
    """Basic information about a Mastodon instance."""

    uri: str
    title: str
    version: str
    description: str


def register_app(
    instance_url: str,
    app_name: str = "TalkBout",
    scopes: str = DEFAULT_SCOPES,
    redirect_uri: str = OOB_REDIRECT_URI,
    website: str | None = None,
) -> OAuthApp:
    """Register a new OAuth application on a Mastodon instance.

    Args:
        instance_url: Base URL of the instance (e.g. "https://wien.rocks").
        app_name: Name for the application.
        scopes: Space-separated list of OAuth scopes.
        redirect_uri: Redirect URI for the OAuth flow.
        website: Optional URL for the application's website.

    Returns:
        An OAuthApp with the client_id and client_secret.

    Raises:
        requests.HTTPError: If the registration request fails.
    """
    url = f"{instance_url.rstrip('/')}/api/v1/apps"
    payload = {
        "client_name": app_name,
        "redirect_uris": redirect_uri,
        "scopes": scopes,
    }
    if website:
        payload["website"] = website

    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    return OAuthApp(
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        instance_url=instance_url.rstrip("/"),
    )


def get_authorization_url(
    app: OAuthApp,
    scopes: str = DEFAULT_SCOPES,
    redirect_uri: str = OOB_REDIRECT_URI,
) -> str:
    """Build the authorization URL that the user should visit in a browser.

    The user visits this URL, logs in, authorizes the app, and receives
    an authorization code to exchange for an access token.

    Args:
        app: The registered OAuth application.
        scopes: Space-separated list of OAuth scopes.
        redirect_uri: Redirect URI matching the one used during registration.

    Returns:
        The authorization URL string.
    """
    return (
        f"{app.instance_url}/oauth/authorize"
        f"?client_id={app.client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
    )


def exchange_code_for_token(
    app: OAuthApp,
    authorization_code: str,
    scopes: str = DEFAULT_SCOPES,
    redirect_uri: str = OOB_REDIRECT_URI,
) -> str:
    """Exchange an authorization code for an access token.

    Args:
        app: The registered OAuth application.
        authorization_code: The code received after user authorization.
        scopes: Space-separated list of OAuth scopes.
        redirect_uri: Redirect URI matching the one used during registration.

    Returns:
        The access token string.

    Raises:
        requests.HTTPError: If the token exchange request fails.
    """
    url = f"{app.instance_url}/oauth/token"
    payload = {
        "client_id": app.client_id,
        "client_secret": app.client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code": authorization_code,
        "scope": scopes,
    }

    response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    return data["access_token"]


def verify_instance(config: MastodonConfig) -> InstanceInfo:
    """Verify connectivity to a Mastodon instance by calling GET /api/v1/instance.

    Args:
        config: The Mastodon configuration with instance URL and credentials.

    Returns:
        An InstanceInfo with basic instance metadata.

    Raises:
        requests.HTTPError: If the instance is unreachable or returns an error.
    """
    url = f"{config.instance_url.rstrip('/')}/api/v1/instance"
    headers = {"Authorization": f"Bearer {config.access_token}"}

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    return InstanceInfo(
        uri=data.get("uri", ""),
        title=data.get("title", ""),
        version=data.get("version", ""),
        description=data.get("short_description", data.get("description", "")),
    )


def verify_credentials(config: MastodonConfig) -> bool:
    """Verify that the access token is valid by calling GET /api/v1/apps/verify_credentials.

    Args:
        config: The Mastodon configuration with credentials.

    Returns:
        True if the credentials are valid.

    Raises:
        requests.HTTPError: If the credentials are invalid or the request fails.
    """
    url = f"{config.instance_url.rstrip('/')}/api/v1/apps/verify_credentials"
    headers = {"Authorization": f"Bearer {config.access_token}"}

    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return True
