#!/usr/bin/env python3
"""Interactive script to register a TalkBout OAuth application on a Mastodon instance.

Usage:
    python scripts/register_app.py [--instance INSTANCE_URL]

This script will:
1. Register an OAuth application on the specified Mastodon instance
2. Print an authorization URL for you to visit in your browser
3. Prompt you to enter the authorization code you receive
4. Exchange the code for an access token
5. Print the credentials to add to your .env file

Default instance: https://wien.rocks
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add the project root to the path so we can import talkbout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from talkbout.mastodon.auth import register_app, get_authorization_url, exchange_code_for_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Register TalkBout on a Mastodon instance")
    parser.add_argument(
        "--instance",
        default="https://wien.rocks",
        help="Mastodon instance URL (default: https://wien.rocks)",
    )
    args = parser.parse_args()
    instance_url: str = args.instance

    print(f"Registering TalkBout on {instance_url}...")
    print()

    try:
        app = register_app(instance_url)
    except Exception as e:
        print(f"Failed to register application: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Application registered successfully.")
    print(f"  Client ID:     {app.client_id}")
    print(f"  Client Secret: {app.client_secret}")
    print()

    auth_url = get_authorization_url(app)
    print("Open this URL in your browser to authorize the application:")
    print()
    print(f"  {auth_url}")
    print()

    authorization_code = input("Enter the authorization code: ").strip()
    if not authorization_code:
        print("No code entered. Exiting.", file=sys.stderr)
        sys.exit(1)

    print()
    print("Exchanging authorization code for access token...")

    try:
        access_token = exchange_code_for_token(app, authorization_code)
    except Exception as e:
        print(f"Failed to exchange code: {e}", file=sys.stderr)
        print()
        print("You can still use the client credentials above.")
        print("Try the authorization flow again manually.")
        sys.exit(1)

    print()
    print("Add the following to your .env file:")
    print()
    print(f"MASTODON_INSTANCE_URL={instance_url}")
    print(f"MASTODON_CLIENT_ID={app.client_id}")
    print(f"MASTODON_CLIENT_SECRET={app.client_secret}")
    print(f"MASTODON_ACCESS_TOKEN={access_token}")


if __name__ == "__main__":
    main()
