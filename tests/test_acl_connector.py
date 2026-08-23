"""Offline regression tests for the ACL Anthology connector."""
from __future__ import annotations

from src.connectors.acl_connector import ACLAnthologyConnector
from src.normalization.schema import Paper


def test_fetch_caps_fallback_results(monkeypatch):
    """A fallback response cannot exceed the caller's requested result limit."""
    connector = ACLAnthologyConnector(search_venues=["acl"])
    fallback = [Paper(id=f"acl:{index}", title="Paper") for index in range(5)]

    def fail_search(_query, _max_results):
        raise RuntimeError("search unavailable")

    monkeypatch.setattr(connector, "_search", fail_search)
    monkeypatch.setattr(
        connector, "_fallback_venue_json", lambda _max_results: fallback
    )

    assert len(connector.fetch("attention", max_results=2)) == 2


def test_bibtex_parser_accepts_non_four_space_indentation():
    bibtex = """@inproceedings{2024.acl-long.1,
  title = {A paper with two-space fields},
  author = {Doe, Jane},
  year = {2024},
  url = {https://aclanthology.org/2024.acl-long.1/},
}
"""

    records = ACLAnthologyConnector._parse_bibtex(bibtex)

    assert len(records) == 1
    assert records[0]["title"] == "A paper with two-space fields"
    assert records[0]["year"] == "2024"
    assert records[0]["url"].endswith("2024.acl-long.1/")
