"""Offline regression tests for the Semantic Scholar connector."""
from __future__ import annotations

from src.connectors.semantic_scholar_connector import _FIELDS, SemanticScholarConnector
from src.normalization.schema import Paper


def test_fetch_caps_results_across_venues(monkeypatch):
    """The connector-wide result limit applies after merging venue results."""
    connector = SemanticScholarConnector(venues=["ICLR", "ICML"])

    def venue_results(_query, venue_key, _max_results):
        return [
            Paper(id=f"s2:{venue_key}:{index}", title="Paper")
            for index in range(3)
        ]

    monkeypatch.setattr(connector, "_fetch_venue", venue_results)

    result = connector.fetch("attention", max_results=3)

    assert len(result) == 3


def test_record_maps_citation_count():
    connector = SemanticScholarConnector(venues=[])
    paper = connector._record_to_paper(
        {
            "paperId": "paper-1",
            "title": "A cited paper",
            "citationCount": 123,
        },
        "ICLR",
        "A*",
    )

    assert paper is not None
    assert paper.citations == 123
    assert "citationCount" in _FIELDS
