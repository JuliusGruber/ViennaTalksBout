"""Tests for viennatalksbout.wien_gv.datasource — Wien.gv petitions datasource.

Unit tests covering:
- BaseDatasource interface compliance
- source_id property
- _parse_date helper
- validate_petition filter
- parse_petition converter
- scrape_petitions HTML parser
- start() delivering posts via on_post callback
- Deduplication across poll cycles
- Error handling
- stop() terminating the poll thread
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from viennatalksbout.config import WienGvConfig
from viennatalksbout.datasource import BaseDatasource, Post
from viennatalksbout.wien_gv.datasource import (
    WienGvPetitionsDatasource,
    _parse_date,
    parse_petition,
    scrape_petitions,
    validate_petition,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> WienGvConfig:
    """Create a WienGvConfig with test defaults."""
    defaults = dict(
        url="https://petitionen.wien.gv.at",
        poll_interval=3600,
        user_agent="ViennaTalksBout/1.0 (test)",
        enabled=True,
    )
    defaults.update(overrides)
    return WienGvConfig(**defaults)


def _make_petition(
    id: str = "abc123",
    title: str = "Mehr Grünflächen im 7. Bezirk",
    date: str = "15.03.2026",
    supporters: str = "42",
    status: str = "Freigegeben",
) -> dict:
    """Create a mock petition dict as returned by scrape_petitions."""
    return {
        "id": id,
        "title": title,
        "date": date,
        "supporters": supporters,
        "status": status,
    }


_SAMPLE_HTML = """\
<html><body>
<table>
  <tr>
    <td>15.03.2026</td>
    <td><a href="PetitionDetail.aspx?PetID=abc123">Mehr Grünflächen im 7. Bezirk</a></td>
    <td>42</td>
    <td>Freigegeben</td>
  </tr>
  <tr>
    <td>10.01.2026</td>
    <td><a href="PetitionDetail.aspx?PetID=def456">Radweg Ringstraße ausbauen</a></td>
    <td>128</td>
    <td>Ausgezählt</td>
  </tr>
</table>
</body></html>
"""


# ===========================================================================
# Interface
# ===========================================================================


class TestInterface:
    """Test that WienGvPetitionsDatasource satisfies BaseDatasource."""

    def test_is_subclass(self):
        assert issubclass(WienGvPetitionsDatasource, BaseDatasource)

    def test_instance(self):
        ds = WienGvPetitionsDatasource(config=_make_config())
        assert isinstance(ds, BaseDatasource)


# ===========================================================================
# source_id
# ===========================================================================


class TestSourceId:
    def test_source_id(self):
        ds = WienGvPetitionsDatasource(config=_make_config())
        assert ds.source_id == "wien-gv:petitions"


# ===========================================================================
# _parse_date
# ===========================================================================


class TestParseDate:
    def test_valid_date(self):
        dt = _parse_date("15.03.2026")
        assert dt == datetime(2026, 3, 15, tzinfo=timezone.utc)

    def test_another_date(self):
        dt = _parse_date("01.01.2024")
        assert dt == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_empty_string_returns_now(self):
        dt = _parse_date("")
        assert dt.tzinfo == timezone.utc

    def test_whitespace_stripped(self):
        dt = _parse_date("  15.03.2026  ")
        assert dt == datetime(2026, 3, 15, tzinfo=timezone.utc)

    def test_invalid_format_returns_now(self):
        dt = _parse_date("not-a-date")
        assert dt.tzinfo == timezone.utc


# ===========================================================================
# validate_petition
# ===========================================================================


class TestValidatePetition:
    def test_valid_petition(self):
        assert validate_petition(_make_petition()) is True

    def test_empty_title(self):
        assert validate_petition(_make_petition(title="")) is False

    def test_very_short_title(self):
        assert validate_petition(_make_petition(title="ab")) is False

    def test_exactly_four_chars(self):
        assert validate_petition(_make_petition(title="abcd")) is True

    def test_whitespace_title(self):
        assert validate_petition(_make_petition(title="   ")) is False


# ===========================================================================
# parse_petition
# ===========================================================================


class TestParsePetition:
    def test_full_petition(self):
        pet = _make_petition(
            title="Mehr Grünflächen",
            supporters="42",
            status="Freigegeben",
        )
        post = parse_petition(pet, "wien-gv:petitions")
        assert "Mehr Grünflächen" in post.text
        assert "(42 Unterstützungen)" in post.text
        assert "[Freigegeben]" in post.text

    def test_id_format(self):
        pet = _make_petition(id="abc123")
        post = parse_petition(pet, "wien-gv:petitions")
        assert post.id == "wien-gv:abc123"

    def test_timestamp(self):
        pet = _make_petition(date="15.03.2026")
        post = parse_petition(pet, "wien-gv:petitions")
        assert post.created_at == datetime(2026, 3, 15, tzinfo=timezone.utc)

    def test_language_is_de(self):
        post = parse_petition(_make_petition(), "wien-gv:petitions")
        assert post.language == "de"

    def test_source(self):
        post = parse_petition(_make_petition(), "wien-gv:petitions")
        assert post.source == "wien-gv:petitions"

    def test_no_supporters(self):
        pet = _make_petition(supporters="")
        post = parse_petition(pet, "wien-gv:petitions")
        assert "Unterstützungen" not in post.text

    def test_no_status(self):
        pet = _make_petition(status="")
        post = parse_petition(pet, "wien-gv:petitions")
        assert "[" not in post.text


# ===========================================================================
# scrape_petitions
# ===========================================================================


class TestScrapePetitions:
    def test_parses_sample_html(self):
        petitions = scrape_petitions(_SAMPLE_HTML)
        assert len(petitions) == 2

    def test_extracts_ids(self):
        petitions = scrape_petitions(_SAMPLE_HTML)
        ids = {p["id"] for p in petitions}
        assert ids == {"abc123", "def456"}

    def test_extracts_titles(self):
        petitions = scrape_petitions(_SAMPLE_HTML)
        titles = {p["title"] for p in petitions}
        assert "Mehr Grünflächen im 7. Bezirk" in titles
        assert "Radweg Ringstraße ausbauen" in titles

    def test_extracts_dates(self):
        petitions = scrape_petitions(_SAMPLE_HTML)
        dates = {p["date"] for p in petitions}
        assert "15.03.2026" in dates
        assert "10.01.2026" in dates

    def test_extracts_supporters(self):
        petitions = scrape_petitions(_SAMPLE_HTML)
        supporters = {p["supporters"] for p in petitions}
        assert "42" in supporters
        assert "128" in supporters

    def test_extracts_status(self):
        petitions = scrape_petitions(_SAMPLE_HTML)
        statuses = {p["status"] for p in petitions}
        assert "Freigegeben" in statuses
        assert "Ausgezählt" in statuses

    def test_empty_html(self):
        assert scrape_petitions("<html></html>") == []

    def test_no_table(self):
        html = "<html><body><p>No petitions here</p></body></html>"
        assert scrape_petitions(html) == []

    def test_link_without_petid(self):
        html = '<html><body><a href="other.aspx">Not a petition</a></body></html>'
        assert scrape_petitions(html) == []

    def test_link_with_empty_title(self):
        html = '<html><body><table><tr><td><a href="PetitionDetail.aspx?PetID=xyz"></a></td></tr></table></body></html>'
        assert scrape_petitions(html) == []

    def test_non_table_layout(self):
        """Petitions in div-based layout should still be parsed."""
        html = """\
        <html><body>
        <div class="petition">
            <a href="PetitionDetail.aspx?PetID=aaa111">Petition in Div</a>
        </div>
        </body></html>
        """
        petitions = scrape_petitions(html)
        assert len(petitions) == 1
        assert petitions[0]["title"] == "Petition in Div"


# ===========================================================================
# start delivers posts
# ===========================================================================


class TestStartDeliversPosts:
    """Test that start() polls and calls on_post."""

    @patch("viennatalksbout.wien_gv.datasource.requests.Session")
    def test_delivers_posts(self, mock_session_cls):
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = WienGvPetitionsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_post.call_count >= 2
        post = on_post.call_args_list[0][0][0]
        assert isinstance(post, Post)
        assert post.language == "de"


# ===========================================================================
# Deduplication
# ===========================================================================


class TestDeduplication:
    """Test that second poll cycle skips already-seen petitions."""

    @patch("viennatalksbout.wien_gv.datasource.requests.Session")
    def test_petitions_not_re_emitted(self, mock_session_cls):
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.return_value = mock_response

        ds = WienGvPetitionsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        # First poll
        ds._poll_once(on_post)
        first_count = on_post.call_count
        assert first_count == 2

        # Second poll with same HTML
        ds._poll_once(on_post)
        assert on_post.call_count == 2  # Still 2 — dedup

    @patch("viennatalksbout.wien_gv.datasource.requests.Session")
    def test_new_petitions_emitted(self, mock_session_cls):
        html1 = """\
<html><body><table>
  <tr>
    <td>15.03.2026</td>
    <td><a href="PetitionDetail.aspx?PetID=abc123">Erste Petition</a></td>
    <td>42</td>
    <td>Freigegeben</td>
  </tr>
</table></body></html>
"""
        html2 = """\
<html><body><table>
  <tr>
    <td>15.03.2026</td>
    <td><a href="PetitionDetail.aspx?PetID=abc123">Erste Petition</a></td>
    <td>42</td>
    <td>Freigegeben</td>
  </tr>
  <tr>
    <td>20.03.2026</td>
    <td><a href="PetitionDetail.aspx?PetID=aef789">Neue Petition</a></td>
    <td>5</td>
    <td>Freigegeben</td>
  </tr>
</table></body></html>
"""

        mock_response1 = MagicMock()
        mock_response1.text = html1
        mock_response1.raise_for_status = MagicMock()

        mock_response2 = MagicMock()
        mock_response2.text = html2
        mock_response2.raise_for_status = MagicMock()

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = [mock_response1, mock_response2]

        ds = WienGvPetitionsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()

        ds._poll_once(on_post)
        assert on_post.call_count == 1

        ds._poll_once(on_post)
        assert on_post.call_count == 2  # Only the new one


# ===========================================================================
# Error handling
# ===========================================================================


class TestErrorHandling:
    """Test error resilience."""

    @patch("viennatalksbout.wien_gv.datasource.requests.Session")
    def test_http_error_calls_on_error(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = Exception("Connection refused")

        ds = WienGvPetitionsDatasource(config=_make_config(poll_interval=9999))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.3)
        ds.stop()

        assert on_error.call_count >= 1

    @patch("viennatalksbout.wien_gv.datasource.requests.Session")
    def test_error_continues_polling(self, mock_session_cls):
        """After an error, the next poll cycle should still run."""
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_HTML
        mock_response.raise_for_status = MagicMock()

        call_count = 0

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary error")
            return mock_response

        mock_session = mock_session_cls.return_value
        mock_session.get.side_effect = get_side_effect

        ds = WienGvPetitionsDatasource(config=_make_config(poll_interval=0.05))
        on_post = MagicMock()
        on_error = MagicMock()

        ds.start(on_post, on_error)
        time.sleep(0.5)
        ds.stop()

        assert on_error.call_count >= 1
        assert on_post.call_count >= 1


# ===========================================================================
# Stop
# ===========================================================================


class TestStop:
    """Test stop behavior."""

    def test_thread_terminates(self):
        ds = WienGvPetitionsDatasource(config=_make_config(poll_interval=9999))

        with patch("viennatalksbout.wien_gv.datasource.requests.Session"):
            ds.start(MagicMock())
            assert ds._thread is not None
            assert ds._thread.is_alive()

            ds.stop()
            assert ds._thread is None

    def test_stop_idempotent(self):
        ds = WienGvPetitionsDatasource(config=_make_config())
        ds.stop()  # Should not raise even without start
        ds.stop()


# ===========================================================================
# Config
# ===========================================================================


class TestWienGvConfig:
    """Test WienGvConfig loading and validation."""

    def test_load_defaults(self):
        import os
        from viennatalksbout.config import load_wien_gv_config

        env_vars = [
            "WIEN_GV_ENABLED", "WIEN_GV_URL",
            "WIEN_GV_POLL_INTERVAL", "WIEN_GV_USER_AGENT",
        ]
        old_vals = {k: os.environ.pop(k, None) for k in env_vars}
        try:
            config = load_wien_gv_config()
            assert config.enabled is False
            assert config.url == "https://petitionen.wien.gv.at"
            assert config.poll_interval == 3600
            assert config.user_agent == "ViennaTalksBout/1.0"
        finally:
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_load_custom(self):
        import os
        from viennatalksbout.config import load_wien_gv_config

        env = {
            "WIEN_GV_ENABLED": "true",
            "WIEN_GV_URL": "https://custom.wien.gv.at",
            "WIEN_GV_POLL_INTERVAL": "1800",
            "WIEN_GV_USER_AGENT": "TestBot/2.0",
        }
        old_vals = {k: os.environ.pop(k, None) for k in env}
        os.environ.update(env)
        try:
            config = load_wien_gv_config()
            assert config.enabled is True
            assert config.url == "https://custom.wien.gv.at"
            assert config.poll_interval == 1800
            assert config.user_agent == "TestBot/2.0"
        finally:
            for k in env:
                os.environ.pop(k, None)
            for k, v in old_vals.items():
                if v is not None:
                    os.environ[k] = v

    def test_validation_empty_url(self):
        config = WienGvConfig(url="", enabled=True)
        errors = config.validate()
        assert any("WIEN_GV_URL" in e for e in errors)

    def test_validation_negative_interval(self):
        config = WienGvConfig(poll_interval=-1, enabled=True)
        errors = config.validate()
        assert any("WIEN_GV_POLL_INTERVAL" in e for e in errors)

    def test_validation_disabled_skips(self):
        config = WienGvConfig(url="", poll_interval=-1, enabled=False)
        errors = config.validate()
        assert errors == []
