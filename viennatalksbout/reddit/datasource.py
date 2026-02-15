"""Reddit polling datasource for ViennaTalksBout.

Periodically polls configured subreddits (r/wien, r/austria) for new
submissions and comments using PRAW, and emits normalized Post objects
via callback.  Follows the same daemon-thread polling pattern as
MastodonPollingDatasource and RssDatasource.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Callable

import praw
import praw.exceptions
import prawcore.exceptions

from viennatalksbout.config import RedditConfig
from viennatalksbout.datasource import BaseDatasource, Post

logger = logging.getLogger(__name__)

# Bots whose posts we skip
BOT_AUTHORS = frozenset({"AutoModerator", "[deleted]"})


def strip_markdown(text: str) -> str:
    """Strip Reddit Markdown formatting to plain text.

    Removes bold, italic, strikethrough, links, block quotes, headings,
    code blocks/spans, and normalizes whitespace.
    """
    # Remove fenced code blocks (```...```)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Remove inline code (`...`)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Remove images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Replace links [text](url) with text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove headings (# ... at start of lines)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold (**text** or __text__)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    # Remove italic (*text* or _text_)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)
    # Remove strikethrough (~~text~~)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    # Remove block quotes (> at start of lines)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    # Remove horizontal rules (---, ***, ___)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_author_name(obj: object) -> str:
    """Extract the author name from a PRAW object."""
    author = getattr(obj, "author", None)
    if author is None:
        return "[deleted]"
    return getattr(author, "name", str(author))


def validate_submission(submission: praw.models.Submission) -> bool:
    """Return True if a submission should be processed."""
    selftext = getattr(submission, "selftext", "")
    if selftext in ("[removed]", "[deleted]"):
        return False
    if getattr(submission, "stickied", False):
        return False
    if _get_author_name(submission) in BOT_AUTHORS:
        return False
    # Skip if both title and selftext are empty after stripping
    title = strip_markdown(getattr(submission, "title", ""))
    body = strip_markdown(selftext) if selftext else ""
    if not title and not body:
        return False
    return True


def validate_comment(comment: praw.models.Comment) -> bool:
    """Return True if a comment should be processed."""
    body = getattr(comment, "body", "")
    if body in ("[removed]", "[deleted]"):
        return False
    if _get_author_name(comment) in BOT_AUTHORS:
        return False
    stripped = strip_markdown(body)
    if len(stripped) < 10:
        return False
    return True


def parse_submission(submission: praw.models.Submission, source: str) -> Post:
    """Convert a PRAW Submission to a normalized Post."""
    title = strip_markdown(getattr(submission, "title", ""))
    selftext = strip_markdown(getattr(submission, "selftext", ""))

    if title and selftext:
        text = f"{title}. {selftext}"
    elif title:
        text = title
    else:
        text = selftext

    created_utc = getattr(submission, "created_utc", 0.0)
    created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

    fullname = getattr(submission, "fullname", f"t3_{submission.id}")

    return Post(
        id=f"reddit:{fullname}",
        text=text,
        created_at=created_at,
        language="de",
        source=source,
    )


def parse_comment(comment: praw.models.Comment, source: str) -> Post:
    """Convert a PRAW Comment to a normalized Post."""
    text = strip_markdown(getattr(comment, "body", ""))

    created_utc = getattr(comment, "created_utc", 0.0)
    created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)

    fullname = getattr(comment, "fullname", f"t1_{comment.id}")

    return Post(
        id=f"reddit:{fullname}",
        text=text,
        created_at=created_at,
        language="de",
        source=source,
    )


class RedditDatasource(BaseDatasource):
    """Polls Reddit subreddits for new submissions and comments.

    Follows the same daemon-thread pattern as ``MastodonPollingDatasource``
    and ``RssDatasource``.
    """

    def __init__(self, config: RedditConfig) -> None:
        self._config = config
        self._reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            username=config.username,
            password=config.password,
            user_agent=config.user_agent,
        )
        self._subreddit_str = "+".join(config.subreddits)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._newest_submission_fullname: str | None = None
        self._newest_comment_fullname: str | None = None

    @property
    def source_id(self) -> str:
        """Datasource identifier, e.g. ``"reddit:wien+austria"``."""
        return f"reddit:{self._subreddit_str}"

    def start(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start polling Reddit in a background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(on_post, on_error),
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Started Reddit polling for r/%s (comments=%s)",
            self._subreddit_str,
            self._config.include_comments,
        )

    def stop(self) -> None:
        """Stop the polling thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped Reddit polling for r/%s", self._subreddit_str)

    def _poll_loop(
        self,
        on_post: Callable[[Post], None],
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Main polling loop executed in the background thread."""
        while not self._stop_event.is_set():
            try:
                self._poll_submissions(on_post)
                if self._config.include_comments:
                    self._poll_comments(on_post)
            except Exception as exc:
                logger.error("Reddit polling error: %s", exc)
                if on_error is not None:
                    on_error(exc)
            self._stop_event.wait(timeout=self._config.poll_interval)

    def _poll_submissions(self, on_post: Callable[[Post], None]) -> None:
        """Fetch new submissions and emit Posts."""
        subreddit = self._reddit.subreddit(self._subreddit_str)
        submissions = list(subreddit.new(limit=100))

        # Filter to only items newer than what we've seen
        new_submissions = []
        for sub in submissions:
            if (
                self._newest_submission_fullname is not None
                and sub.fullname == self._newest_submission_fullname
            ):
                break
            new_submissions.append(sub)

        # Process oldest-first
        for sub in reversed(new_submissions):
            if validate_submission(sub):
                post = parse_submission(sub, self.source_id)
                on_post(post)

        # Track newest seen
        if submissions:
            self._newest_submission_fullname = submissions[0].fullname

    def _poll_comments(self, on_post: Callable[[Post], None]) -> None:
        """Fetch new comments and emit Posts."""
        subreddit = self._reddit.subreddit(self._subreddit_str)
        comments = list(subreddit.comments(limit=100))

        # Filter to only items newer than what we've seen
        new_comments = []
        for comment in comments:
            if (
                self._newest_comment_fullname is not None
                and comment.fullname == self._newest_comment_fullname
            ):
                break
            new_comments.append(comment)

        # Process oldest-first
        for comment in reversed(new_comments):
            if validate_comment(comment):
                post = parse_comment(comment, self.source_id)
                on_post(post)

        # Track newest seen
        if comments:
            self._newest_comment_fullname = comments[0].fullname
