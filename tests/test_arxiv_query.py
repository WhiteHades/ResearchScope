"""Tests for the arXiv search-query tightening logic."""

from researchscope.collectors.arxiv import _build_search_query


def test_plain_multiword_query_becomes_and_of_all_terms():
    assert (
        _build_search_query("large language models")
        == "all:large AND all:language AND all:models"
    )


def test_single_word_query_is_scoped_to_all():
    assert _build_search_query("transformers") == "all:transformers"


def test_query_is_stripped():
    assert _build_search_query("  graph networks  ") == "all:graph AND all:networks"


def test_field_prefixed_query_passes_through():
    assert _build_search_query("ti:transformer") == "ti:transformer"
    assert _build_search_query("cat:cs.CL") == "cat:cs.CL"


def test_boolean_query_passes_through():
    q = "all:diffusion AND cat:cs.CV"
    assert _build_search_query(q) == q
    assert _build_search_query("robots OR agents") == "robots OR agents"


def test_quoted_phrase_is_scoped_to_all_verbatim():
    assert _build_search_query('"chain of thought"') == 'all:"chain of thought"'


def test_empty_query_returns_empty():
    assert _build_search_query("   ") == ""
