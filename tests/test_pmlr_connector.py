"""Offline regression tests for the PMLR connector."""
from __future__ import annotations

from src.connectors.pmlr_connector import _PMLRParser


def test_parser_waits_for_outer_paper_div_before_finalizing():
    html = """
    <div class="paper">
      <p class="title"><a href="/v235/one24.html">Nested div paper</a></p>
      <div class="metadata"><p class="authors">Ada Lovelace, Alan Turing</p></div>
      <p class="abstract">The abstract remains part of the paper.</p>
    </div>
    """

    parser = _PMLRParser()
    parser.feed(html)

    assert len(parser.papers) == 1
    assert parser.papers[0]["title"] == "Nested div paper"
    assert parser.papers[0]["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert parser.papers[0]["abstract"] == " The abstract remains part of the paper."
