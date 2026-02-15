"""Tests for viennatalksbout.reddit.datasource — Reddit polling datasource.

Unit tests covering:
- BaseDatasource interface compliance
- source_id property
- strip_markdown helper
- validate_submission / validate_comment filters
- parse_submission / parse_comment converters
- start() delivering posts via on_post callback
- ID tracking across poll cycles
- Error handling
- stop() terminating the poll thread
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from viennatalksbout.config import RedditConfig
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.reddit.datasource import (
    RedditDatasource,
    parse_comment,
    parse_submission,
    strip_markdown,
    validate_comment,
    validate_submission,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> RedditConfig:
    """Create a RedditConfig with test defaults."""
    defaults = dict(
        client_id="test_cid",
        client_secret="test_csec",
        username="test_user",
        password="test_pass",
        subreddits=("wien", "austria"),
        poll_interval=60,
        enabled=True,
        include_comments=True,
    )
    defaults.update(overrides)
    return RedditConfig(**defaults)


def _make_submission(
    id: str = "abc123",
    fullname: str = "t3_abc123",
    title: str = "Test Title",
    selftext: str = "Test body text",
    created_utc: float = 1718452800.0,  # 2024-06-15 12:00:00 UTC
    stickied: bool = False,
    author: str = "test_user",
) -> SimpleNamespace:
    """Create a mock PRAW Submission."""
    return SimpleNamespace(
        id=id,
        fullname=fullname,
        title=title,
        selftext=selftext,
        created_utc=created_utc,
        stickied=stickied,
        author=SimpleNamespace(__str__=lambda self: author, name=author)
        if author != "[deleted]"
        else None,
    )


def _make_comment(
    id: str = "xyz789",
    fullname: str = "t1_xyz789",
    body: str = "This is a test comment with enough characters",
    created_utc: float = 1718452800.0,
    author: str = "test_user",
) -> SimpleNamespace:
    """Create a mock PRAW Comment."""
    return SimpleNamespace(
        id=id,
        fullname=fullname,
        body=body,
        created_utc=created_utc,
        author=SimpleNamespace(__str__=lambda self: author, name=author)
        if author != "[deleted]"
        else None,
    )


# ===========================================================================
# Interface
# ===========================================================================


class TestInterface:
    """Test that RedditDatasource satisfies BaseDatasource."""

    def test_is_subclass(self):
        assert issubclass(RedditDatasource, BaseDatasource)

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_instance(self, mock_reddit):
        ds = RedditDatasource(config=_make_config())
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_default_subreddits(self, mock_reddit):
        ds = RedditDatasource(config=_make_config())
        assert ds.source_id == "reddit:wien+austria"

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_custom_subreddits(self, mock_reddit):
        ds = RedditDatasource(config=_make_config(subreddits=("vienna",)))
        assert ds.source_id == "reddit:vienna"

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_three_subreddits(self, mock_reddit):
        ds = RedditDatasource(
            config=_make_config(subreddits=("wien", "austria", "vienna"))
        )
        assert ds.source_id == "reddit:wien+austria+vienna"


# ===========================================================================
# strip_markdown
# ===========================================================================


class TestStripMarkdown:
    def test_bold(self):
        assert strip_markdown("**bold text**") == "bold text"

    def test_italic(self):
        assert strip_markdown("*italic text*") == "italic text"

    def test_strikethrough(self):
        assert strip_markdown("~~removed~~") == "removed"

    def test_links(self):
        assert strip_markdown("[click here](https://example.com)") == "click here"

    def test_headings(self):
        assert strip_markdown("# Heading\nText") == "Heading Text"

    def test_block_quotes(self):
        assert strip_markdown("> quoted text") == "quoted text"

    def test_inline_code(self):
        assert strip_markdown("use `code` here") == "use code here"

    def test_code_blocks(self):
        result = strip_markdown("```\ncode block\n```")
        assert "```" not in result

    def test_images(self):
        assert strip_markdown("![alt](https://img.png)") == "alt"

    def test_mixed(self):
        text = "**Bold** and *italic* with [link](url)"
        result = strip_markdown(text)
        assert result == "Bold and italic with link"

    def test_empty(self):
        assert strip_markdown("") == ""

    def test_plain_text_unchanged(self):
        assert strip_markdown("plain text") == "plain text"

    def test_whitespace_normalized(self):
        assert strip_markdown("  too   many   spaces  ") == "too many spaces"


# ===========================================================================
# validate_submission
# ===========================================================================


class TestValidateSubmission:
    def test_valid_submission(self):
        sub = _make_submission()
        assert validate_submission(sub) is True

    def test_removed(self):
        sub = _make_submission(selftext="[removed]")
        assert validate_submission(sub) is False

    def test_deleted(self):
        sub = _make_submission(selftext="[deleted]")
        assert validate_submission(sub) is False

    def test_stickied(self):
        sub = _make_submission(stickied=True)
        assert validate_submission(sub) is False

    def test_automoderator(self):
        sub = _make_submission(author="AutoModerator")
        assert validate_submission(sub) is False

    def test_deleted_author(self):
        sub = _make_submission(author="[deleted]")
        assert validate_submission(sub) is False

    def test_empty_title_and_body(self):
        sub = _make_submission(title="", selftext="")
        assert validate_submission(sub) is False

    def test_link_post_with_title(self):
        sub = _make_submission(title="Interesting article", selftext="")
        assert validate_submission(sub) is True


# ===========================================================================
# validate_comment
# ===========================================================================


class TestValidateComment:
    def test_valid_comment(self):
        c = _make_comment()
        assert validate_comment(c) is True

    def test_removed(self):
        c = _make_comment(body="[removed]")
        assert validate_comment(c) is False

    def test_deleted(self):
        c = _make_comment(body="[deleted]")
        assert validate_comment(c) is False

    def test_automoderator(self):
        c = _make_comment(author="AutoModerator")
        assert validate_comment(c) is False

    def test_deleted_author(self):
        c = _make_comment(author="[deleted]")
        assert validate_comment(c) is False

    def test_too_short(self):
        c = _make_comment(body="hi")
        assert validate_comment(c) is False

    def test_exactly_10_chars(self):
        c = _make_comment(body="1234567890")
        assert validate_comment(c) is True


# ===========================================================================
# parse_submission
# ===========================================================================


class TestParseSubmission:
    def test_text_post(self):
        sub = _make_submission(title="Title", selftext="Body text")
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.text == "Title. Body text"

    def test_link_post_title_only(self):
        sub = _make_submission(title="Link title", selftext="")
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.text == "Link title"

    def test_id_format(self):
        sub = _make_submission(fullname="t3_abc123")
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.id == "reddit:t3_abc123"

    def test_timestamp(self):
        sub = _make_submission(created_utc=1718452800.0)
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.created_at.tzinfo == timezone.utc
        assert post.created_at == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_language_default_de(self):
        sub = _make_submission()
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.language == "de"

    def test_source(self):
        sub = _make_submission()
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.source == "reddit:wien+austria"

    def test_markdown_stripped(self):
        sub = _make_submission(
            title="**Bold Title**", selftext="Check [this](url) out"
        )
        post = parse_submission(sub, "reddit:wien+austria")
        assert post.text == "Bold Title. Check this out"


# ===========================================================================
# parse_comment
# ===========================================================================


class TestParseComment:
    def test_body_text(self):
        c = _make_comment(body="This is a comment body")
        post = parse_comment(c, "reddit:wien+austria")
        assert post.text == "This is a comment body"

    def test_id_format(self):
        c = _make_comment(fullname="t1_xyz789")
        post = parse_comment(c, "reddit:wien+austria")
        assert post.id == "reddit:t1_xyz789"

    def test_timestamp(self):
        c = _make_comment(created_utc=1718452800.0)
        post = parse_comment(c, "reddit:wien+austria")
        assert post.created_at == datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_language_default_de(self):
        c = _make_comment()
        post = parse_comment(c, "reddit:wien+austria")
        assert post.language == "de"

    def test_markdown_stripped(self):
        c = _make_comment(body="**bold** and *italic*")
        post = parse_comment(c, "reddit:wien+austria")
        assert post.text == "bold and italic"


# ===========================================================================
# start delivers posts
# ===========================================================================


class TestStartDeliversPosts:
    """Test that start() polls subreddits and calls on_post."""

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_delivers_submission_posts(self, mock_reddit_cls):
        sub = _make_submission(title="Wien Post", selftext="Content")

        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = [sub]
        mock_subreddit.comments.return_value = []
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert "Wien Post" in post.text

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_delivers_comment_posts(self, mock_reddit_cls):
        comment = _make_comment(body="A detailed comment about Vienna life")

        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = []
        mock_subreddit.comments.return_value = [comment]
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        ds.start(on_post)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 1
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert "Vienna life" in post.text

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_comments_disabled(self, mock_reddit_cls):
        sub = _make_submission(title="Wien Post", selftext="Content")
        comment = _make_comment(body="A detailed comment about Vienna")

        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = [sub]
        mock_subreddit.comments.return_value = [comment]
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(
            config=_make_config(poll_interval=9999, include_comments=False)
        )
        on_post = MagicMock()

        ds.start(on_post)
        time.sleep(0.3)
        ds.stop()

        # Should only get the submission, not the comment
        posts = [call[0][0] for call in on_post.call_args_list]
        assert all("reddit:t3_" in p.id for p in posts)


# ===========================================================================
# ID tracking
# ===========================================================================


class TestIdTracking:
    """Test that second poll cycle skips already-seen items."""

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_submissions_not_re_emitted(self, mock_reddit_cls):
        sub = _make_submission(fullname="t3_aaa")

        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = [sub]
        mock_subreddit.comments.return_value = []
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        # First poll
        ds._poll_submissions(on_post)
        assert on_post.call_count == 1

        # Second poll with same submission
        ds._poll_submissions(on_post)
        assert on_post.call_count == 1  # Still 1 — dedup

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_new_submissions_emitted(self, mock_reddit_cls):
        sub1 = _make_submission(id="aaa", fullname="t3_aaa")
        sub2 = _make_submission(id="bbb", fullname="t3_bbb", title="New post")

        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        # First poll
        mock_subreddit.new.return_value = [sub1]
        ds._poll_submissions(on_post)
        assert on_post.call_count == 1

        # Second poll with new item first (newest-first order)
        mock_subreddit.new.return_value = [sub2, sub1]
        ds._poll_submissions(on_post)
        assert on_post.call_count == 2

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_comments_not_re_emitted(self, mock_reddit_cls):
        comment = _make_comment(fullname="t1_aaa")

        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.comments.return_value = [comment]
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        ds._poll_comments(on_post)
        assert on_post.call_count == 1

        ds._poll_comments(on_post)
        assert on_post.call_count == 1  # Still 1 — dedup


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Test error resilience."""

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_api_error_calls_on_error(self, mock_reddit_cls):
        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.new.side_effect = Exception("API error")
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_error_continues_polling(self, mock_reddit_cls):
        """After an error, the next poll cycle should still run."""
        sub = _make_submission()
        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()

        call_count = 0

        def new_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("API error")
            return [sub]

        mock_subreddit.new.side_effect = new_side_effect
        mock_subreddit.comments.return_value = []
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=0.05))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1
        assert on_post.call_count >= 1


# ===========================================================================
# Stop
# ===========================================================================


class TestStop:
    """Test stop behavior."""

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_thread_terminates(self, mock_reddit_cls):
        mock_reddit = mock_reddit_cls.return_value
        mock_subreddit = MagicMock()
        mock_subreddit.new.return_value = []
        mock_subreddit.comments.return_value = []
        mock_reddit.subreddit.return_value = mock_subreddit

        ds = RedditDatasource(config=_make_config(poll_interval=9999))
        ds.start(MagicMock())
        assert ds._thread is not None
        assert ds._thread.is_alive()

        ds.stop()
        assert ds._thread is None

    @patch("viennatalksbout.reddit.datasource.praw.Reddit")
    def test_stop_idempotent(self, mock_reddit_cls):
        ds = RedditDatasource(config=_make_config())
        ds.stop()  # Should not raise even without start
        ds.stop()
