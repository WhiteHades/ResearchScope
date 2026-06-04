"""
OpenAlex connector.

Fetches CS/ML/AI/NLP/CV papers from the OpenAlex open catalogue.
No API key required; polite-pool header raises rate limit significantly.

Docs: https://docs.openalex.org/api-entities/works/filter-works
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import BaseConnector
from src.normalization.schema import Paper

log = logging.getLogger(__name__)

_BASE   = "https://api.openalex.org"
_EMAIL  = "mdkishor.morol@stonybrook.edu"   # polite-pool identifier
_AGENT  = f"ResearchScope/1.0 (mailto:{_EMAIL})"
_DELAY  = 0.12   # ~8 req/s — well within polite-pool limits
_PAGE   = 200    # max per page

# Fields we need — keeps response payload small
_SELECT = (
    "id,doi,title,abstract_inverted_index,authorships,"
    "primary_location,publication_year,cited_by_count,"
    "open_access,concepts,type"
)

# OpenAlex concept IDs for CS subfields (OR-combined per request)
_CONCEPT_GROUPS: dict[str, list[str]] = {
    "ML":  ["C119857082", "C48824518", "C108827166"],   # ML, Deep Learning, RL
    "NLP": ["C204321447"],                                # NLP
    "CV":  ["C31972630",  "C2908793557"],                # AI, CV
    "IR":  ["C143998085", "C2371838"],                   # Info Retrieval, Rec Sys
}

# Source display names → canonical short name + rank
_VENUE_MAP: dict[str, tuple[str, str]] = {
    "Journal of Machine Learning Research": ("JMLR",    "A*"),
    "Transactions on Machine Learning Research": ("TMLR", "A*"),
    "Transactions of the Association for Computational Linguistics": ("TACL", "A*"),
    "IEEE Transactions on Pattern Analysis and Machine Intelligence": ("TPAMI","A*"),
    "International Journal of Computer Vision": ("IJCV",  "A*"),
    "Artificial Intelligence": ("AIJ",    "A*"),
    "Nature Machine Intelligence": ("NMI", "A*"),
    "Neural Information Processing Systems": ("NeurIPS","A*"),
    "International Conference on Machine Learning": ("ICML","A*"),
    "International Conference on Learning Representations": ("ICLR","A*"),
    "Computer Vision and Pattern Recognition": ("CVPR", "A*"),
    "Annual Meeting of the Association for Computational Linguistics": ("ACL","A*"),
    "Conference on Empirical Methods in Natural Language Processing": ("EMNLP","A*"),
    "AAAI Conference on Artificial Intelligence": ("AAAI","A*"),
    "International Joint Conference on Artificial Intelligence": ("IJCAI","A*"),
    "ACM Computing Surveys": ("CSUR",   "A*"),
    "Nature Communications": ("NatComms","A*"),
    "IEEE Transactions on Neural Networks and Learning Systems": ("TNNLS", "A*"),
    "IEEE Transactions on Image Processing": ("TIP",  "A*"),
    "Machine Learning": ("MLJ",   "A*"),
    "IEEE Transactions on Knowledge and Data Engineering": ("TKDE", "A*"),
    "Data Mining and Knowledge Discovery": ("DAMI",  "A*"),
    "Neural Networks": ("NN",     "A"),
    "Pattern Recognition": ("PR",     "A"),
    "Computational Linguistics": ("CL",     "A*"),
    "Information Processing & Management": ("IPM",    "A"),
    "Journal of the ACM": ("JACM",   "A*"),
    "ACM Transactions on Information Systems": ("TOIS",   "A*"),
}

# OpenAlex source IDs for the top CS journals → (canonical short name, rank).
# Used by fetch_journals() to pull every paper from a journal by venue, the
# keyless counterpart to SemanticScholarConnector.fetch_journals().
# Resolved via the OpenAlex /sources endpoint (display-name search).
# Note: JMLR and TMLR are indexed poorly by OpenAlex for recent years
# (they publish open-access / on OpenReview); coverage there is sparse.
_JOURNAL_SOURCES: dict[str, tuple[str, str]] = {
    "S118988714":  ("JMLR",     "A*"),
    "S4393919742": ("TMLR",     "A*"),
    "S2729999759": ("TACL",     "A*"),
    "S199944782":  ("TPAMI",    "A*"),
    "S25538012":   ("IJCV",     "A*"),
    "S196139623":  ("AIJ",      "A*"),
    "S4210175523": ("TNNLS",    "A*"),
    "S2912241403": ("NMI",      "A*"),
    "S157921468":  ("CSUR",     "A*"),
    "S4210173141": ("TIP",      "A*"),
    "S62148650":   ("MLJ",      "A*"),
    "S30698027":   ("TKDE",     "A*"),
    "S121920818":  ("DAMI",     "A*"),
    "S123019304":  ("NN",       "A"),
    "S414566":     ("PR",       "A"),
    "S155526855":  ("CL",       "A*"),
    "S174847851":  ("IPM",      "A"),
    "S118992489":  ("JACM",     "A*"),
    "S64187185":   ("NatComms", "A*"),
    "S4394735545": ("TOIS",     "A*"),
}


def _reconstruct_abstract(inv: dict[str, list[int]] | None) -> str:
    """Reconstruct abstract from OpenAlex inverted index."""
    if not inv:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in inv.items():
        for pos in positions:
            pairs.append((pos, word))
    pairs.sort()
    return " ".join(w for _, w in pairs)


def _map_venue(source: dict[str, Any]) -> tuple[str, str]:
    """Return (canonical_name, rank) for an OpenAlex source dict."""
    name = str(source.get("display_name") or "").strip()
    if name in _VENUE_MAP:
        return _VENUE_MAP[name]
    for key, val in _VENUE_MAP.items():
        if key.lower() in name.lower():
            return val
    return (name, "")


def _work_to_paper(work: dict[str, Any]) -> Paper | None:
    title = str(work.get("title") or "").strip()
    if not title or title.lower() == "null":
        return None
    if work.get("type") not in {"article", "preprint", None, ""}:
        return None

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    # Authors + affiliations
    authors: list[str] = []
    affiliations: list[str] = []
    for auth in (work.get("authorships") or []):
        author = auth.get("author") or {}
        name   = str(author.get("display_name") or "").strip()
        if name:
            authors.append(name)
        for inst in (auth.get("institutions") or []):
            inst_name = str(inst.get("display_name") or "").strip()
            if inst_name and inst_name not in affiliations:
                affiliations.append(inst_name)

    year = int(work.get("publication_year") or 0)

    # Venue
    loc    = work.get("primary_location") or {}
    source = loc.get("source") or {}
    venue_name, rank = _map_venue(source)

    # URLs
    doi      = str(work.get("doi") or "").replace("https://doi.org/", "")
    oa       = work.get("open_access") or {}
    pdf_url  = str(oa.get("oa_url") or "")
    paper_url = f"https://doi.org/{doi}" if doi else str(loc.get("landing_page_url") or "")

    # Tags from concepts
    tags = [
        str(c.get("display_name") or "")
        for c in sorted(work.get("concepts") or [], key=lambda x: -(x.get("score") or 0))
        if c.get("score", 0) > 0.3
    ][:6]

    oa_id = str(work.get("id") or "").replace("https://openalex.org/", "")

    source_type = "journal" if source.get("type") in {"journal"} else (
        "conference" if source.get("type") in {"conference"} else "preprint"
    )

    return Paper(
        id=f"openalex:{oa_id}",
        source="openalex",
        source_type=source_type,
        title=title,
        abstract=abstract,
        authors=authors,
        affiliations_raw=affiliations,
        year=year,
        published_date=f"{year}-01-01" if year else "",
        venue=venue_name,
        conference_rank=rank,
        paper_url=paper_url,
        pdf_url=pdf_url,
        citations=int(work.get("cited_by_count") or 0),
        tags=tags,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


class OpenAlexConnector(BaseConnector):
    """Fetches CS/ML/AI/NLP papers from OpenAlex."""

    def __init__(
        self,
        concept_groups: list[str] | None = None,
        from_year: int = 2022,
    ) -> None:
        self._groups    = concept_groups or list(_CONCEPT_GROUPS.keys())
        self._from_year = from_year

    @property
    def source_name(self) -> str:
        return "openalex"

    # ── Full bulk fetch ───────────────────────────────────────────────────────

    def fetch_all(self) -> list[Paper]:
        """Fetch ALL papers for configured concept groups."""
        all_papers: list[Paper] = []
        seen: set[str] = set()
        for group in self._groups:
            concept_ids = _CONCEPT_GROUPS.get(group, [])
            if not concept_ids:
                continue
            log.info("[openalex] fetching %s (concepts: %s) …", group, concept_ids)
            try:
                papers = self._fetch_concept_group(concept_ids)
                log.info("[openalex] %s → %d papers", group, len(papers))
                for p in papers:
                    if p.id not in seen:
                        seen.add(p.id)
                        all_papers.append(p)
            except Exception as exc:
                log.warning("[openalex] %s failed: %s", group, exc)
        return all_papers

    # ── Journal bulk fetch (keyless S2 fetch_journals replacement) ───────────

    def fetch_journals(
        self,
        sources: dict[str, tuple[str, str]] | None = None,
        from_year: int | None = None,
        to_year: int | None = None,
        max_per_source: int | None = None,
    ) -> list[Paper]:
        """Bulk-fetch every paper from the top CS journals, by venue.

        Paginates OpenAlex works filtered to each journal's source id, so
        coverage of a given journal is systematic — unlike fetch_all(), which
        ranks by citations across a whole concept. Sets source_type='journal'
        and stamps the canonical venue/rank. Requires no API key.
        """
        target   = sources or _JOURNAL_SOURCES
        from_y   = from_year if from_year is not None else self._from_year
        to_y     = to_year if to_year is not None else datetime.now(timezone.utc).year
        year_flt = f"{from_y}-{to_y}"

        all_papers: list[Paper] = []
        seen: set[str] = set()

        for source_id, (short, rank) in target.items():
            try:
                papers = self._fetch_journal_source(source_id, year_flt, max_per_source)
                log.info("[openalex] journal %s (%s) → %d papers", short, source_id, len(papers))
                for p in papers:
                    if p.id in seen:
                        continue
                    seen.add(p.id)
                    # Stamp canonical venue/rank — OpenAlex display names vary
                    # and several of these journals are missing from _VENUE_MAP.
                    p.venue           = short
                    p.conference_rank = rank
                    p.source_type     = "journal"
                    all_papers.append(p)
            except Exception as exc:
                log.warning("[openalex] journal %s failed: %s", short, exc)

        return all_papers

    def _fetch_journal_source(
        self, source_id: str, year_flt: str, max_per_source: int | None
    ) -> list[Paper]:
        base_filter = (
            f"primary_location.source.id:{source_id},"
            f"publication_year:{year_flt},type:article"
        )
        papers: list[Paper] = []
        cursor = "*"
        while cursor:
            params = urllib.parse.urlencode({
                "filter":   base_filter,
                "select":   _SELECT,
                "per-page": _PAGE,
                "cursor":   cursor,
            })
            data    = self._get(f"{_BASE}/works?{params}")
            results = data.get("results", [])
            for work in results:
                p = self._to_paper(work)
                if p:
                    papers.append(p)
            if max_per_source and len(papers) >= max_per_source:
                return papers[:max_per_source]

            cursor = data.get("meta", {}).get("next_cursor") or data.get("next_cursor") or ""
            if not results or not cursor:
                break
            time.sleep(_DELAY)

        return papers

    # ── Keyword search (daily pipeline mode) ─────────────────────────────────

    def fetch(self, query: str, max_results: int = 50) -> list[Paper]:
        """Keyword search across OpenAlex works."""
        params = urllib.parse.urlencode({
            "search":   query,
            "filter":   f"type:article,publication_year:>={self._from_year}",
            "select":   _SELECT,
            "per-page": min(max_results, _PAGE),
        })
        try:
            data   = self._get(f"{_BASE}/works?{params}")
            works  = data.get("results", [])
            papers = [p for p in (self._to_paper(w) for w in works) if p]
            log.info("[openalex] '%s' → %d papers", query, len(papers))
            return papers[:max_results]
        except Exception as exc:
            log.warning("[openalex] search '%s' failed: %s", query, exc)
            return []

    # ── internals ─────────────────────────────────────────────────────────────

    def _fetch_concept_group(self, concept_ids: list[str]) -> list[Paper]:
        concept_filter = "|".join(concept_ids)
        base_filter    = f"concepts.id:{concept_filter},type:article,publication_year:>={self._from_year}"

        papers: list[Paper] = []
        cursor = "*"
        while cursor:
            params = urllib.parse.urlencode({
                "filter":   base_filter,
                "select":   _SELECT,
                "per-page": _PAGE,
                "cursor":   cursor,
                "sort":     "cited_by_count:desc",
            })
            data    = self._get(f"{_BASE}/works?{params}")
            results = data.get("results", [])
            for work in results:
                p = self._to_paper(work)
                if p:
                    papers.append(p)

            meta   = data.get("meta", {})
            cursor = data.get("next_cursor") or meta.get("next_cursor") or ""
            if not results or not cursor:
                break
            time.sleep(_DELAY)

        return papers

    @staticmethod
    def _to_paper(work: dict) -> Paper | None:
        return _work_to_paper(work)

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": _AGENT})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
