"""Tests for the OpenReview connector — offline (no network).

Exercises note → Paper mapping using synthetic notes shaped like the real
api2.openreview.net responses, focusing on the acceptance-tier signal that
distinguishes oral/spotlight/poster acceptances.
"""
from __future__ import annotations

from src.connectors.openreview_connector import (
    OpenReviewConnector,
    _epoch_ms_to_iso_date,
    _parse_presentation_type,
)


def _note(venue: str, *, title: str = "A Paper", pdate: int | None = None,
          pdf: str = "", note_id: str = "abc123") -> dict:
    """Build a synthetic OpenReview note (api2 'value'-wrapped content)."""
    content = {
        "title":    {"value": title},
        "abstract": {"value": "We propose a thing.\nIt works well."},
        "authors":  {"value": ["Ada Lovelace", "Alan Turing"]},
        "venue":    {"value": venue},
        "venueid":  {"value": "ICLR.cc/2024/Conference"},
    }
    if pdf:
        content["pdf"] = {"value": pdf}
    note: dict = {"id": note_id, "content": content}
    if pdate is not None:
        note["pdate"] = pdate
    return note


# ── tier parsing ───────────────────────────────────────────────────────────────

class TestParsePresentationType:
    def test_poster_lowercase(self):
        assert _parse_presentation_type("ICLR 2024 poster") == "poster"

    def test_oral_capitalized(self):
        assert _parse_presentation_type("ICLR 2025 Oral") == "oral"

    def test_spotlight(self):
        assert _parse_presentation_type("NeurIPS 2025 spotlight") == "spotlight"

    def test_unknown_returns_empty(self):
        assert _parse_presentation_type("ICLR 2024 Conference") == ""
        assert _parse_presentation_type("") == ""


# ── date conversion ──────────────────────────────────────────────────────────

class TestEpochToIso:
    def test_known_timestamp(self):
        # 1705411064826 ms → 2024-01-16 UTC
        assert _epoch_ms_to_iso_date(1705411064826) == "2024-01-16"

    def test_zero_and_none(self):
        assert _epoch_ms_to_iso_date(0) == ""
        assert _epoch_ms_to_iso_date(None) == ""


# ── note → Paper mapping ─────────────────────────────────────────────────────

class TestNoteToPaper:
    def setup_method(self):
        self.conn = OpenReviewConnector(venues=[])  # no network in __init__

    def _map(self, note: dict):
        return self.conn._note_to_paper(note, "ICLR", "A*", 2024)

    def test_basic_fields(self):
        p = self._map(_note("ICLR 2024 poster"))
        assert p is not None
        assert p.id == "openreview:abc123"
        assert p.source == "openreview"
        assert p.source_type == "conference"
        assert p.venue == "ICLR"
        assert p.conference_rank == "A*"
        assert p.authors == ["Ada Lovelace", "Alan Turing"]
        assert p.paper_url == "https://openreview.net/forum?id=abc123"

    def test_presentation_type_captured(self):
        assert self._map(_note("ICLR 2024 poster")).presentation_type == "poster"
        assert self._map(_note("ICLR 2025 Oral")).presentation_type == "oral"
        assert self._map(_note("NeurIPS 2025 spotlight")).presentation_type == "spotlight"

    def test_pdate_used_for_published_date(self):
        p = self._map(_note("ICLR 2024 poster", pdate=1705411064826))
        assert p.published_date == "2024-01-16"

    def test_published_date_falls_back_to_year(self):
        p = self._map(_note("ICLR 2024 poster"))  # no pdate/odate/cdate
        assert p.published_date == "2024-01-01"

    def test_pdf_url_built_from_path(self):
        p = self._map(_note("ICLR 2024 poster", pdf="/pdf/deadbeef.pdf"))
        assert p.pdf_url == "https://openreview.net/pdf/deadbeef.pdf"

    def test_missing_title_dropped(self):
        note = _note("ICLR 2024 poster")
        note["content"]["title"] = {"value": ""}
        assert self._map(note) is None

    def test_tags_not_polluted(self):
        # Raw OpenReview keywords must NOT become tags (the tagger owns that).
        assert self._map(_note("ICLR 2024 poster")).tags == []
