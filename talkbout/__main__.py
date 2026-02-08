"""TalkBout CLI — fetch posts from Mastodon and print them to the terminal."""

import signal
import time

import requests

from talkbout.datasource import Post
from talkbout.mastodon.stream import (
    MastodonDatasource,
    filter_status,
    parse_status,
    validate_status,
)

INSTANCE_URL = "https://wien.rocks"
POLL_INTERVAL = 5  # seconds between polls
PAGE_SIZE = 20


def print_post(post: Post) -> None:
    """Print a post to stdout."""
    print(f"[{post.created_at:%H:%M:%S}] ({post.source}) [{post.language or '??'}]")
    print(f"  {post.text}")
    print()


def poll_public_timeline(instance_url: str, source: str) -> None:
    """Poll the public local timeline REST API and print posts."""
    api_url = f"{instance_url}/api/v1/timelines/public"
    seen_ids: set[str] = set()
    running = True

    def on_signal(sig, frame):
        nonlocal running
        print("\nStopping...")
        running = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    print(f"Polling posts from {source}... (Ctrl+C to stop)\n")

    while running:
        try:
            resp = requests.get(
                api_url,
                params={"local": "true", "limit": PAGE_SIZE},
                timeout=10,
            )
            resp.raise_for_status()
            statuses = resp.json()
        except Exception as e:
            print(f"  [error] {e}")
            time.sleep(POLL_INTERVAL)
            continue

        new_count = 0
        for status in statuses:
            sid = str(status.get("id", ""))
            if sid in seen_ids:
                continue
            seen_ids.add(sid)

            validated = validate_status(status)
            if validated is None:
                continue
            if not filter_status(validated):
                continue

            post = parse_status(validated, source)
            print_post(post)
            new_count += 1

        if new_count == 0 and seen_ids:
            # No new posts this cycle — just wait
            pass

        time.sleep(POLL_INTERVAL)


def main() -> None:
    # Try loading credentials from .env for SSE streaming
    try:
        from talkbout.config import load_config

        config = load_config()
        ds = MastodonDatasource(config.instance_url, config.access_token)
        print(f"Streaming posts from {ds.source_id}... (Ctrl+C to stop)\n")
        import threading

        stop_event = threading.Event()

        def on_signal(sig, frame):
            print("\nStopping stream...")
            ds.stop()
            stop_event.set()

        signal.signal(signal.SIGINT, on_signal)
        signal.signal(signal.SIGTERM, on_signal)

        ds.start(print_post)
        stop_event.wait()
    except (ValueError, Exception):
        # No credentials — fall back to REST API polling
        instance = INSTANCE_URL
        domain = instance.replace("https://", "").replace("http://", "")
        source = f"mastodon:{domain}"
        print(f"No .env credentials found — polling public timeline from {instance}")
        poll_public_timeline(instance, source)


if __name__ == "__main__":
    main()
