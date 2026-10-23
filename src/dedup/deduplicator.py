"""Merge repeated records and likely paper versions.

Pass one matches exact nonempty record IDs or shared arXiv IDs. Pass two
compares title word overlap among records that share a title bigram.

The representative uses a metadata completeness heuristic. Venue and rank
contribute to that heuristic but do not override every other field. Title
matching does not verify version relationships.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from src.normalization.dates import normalize_publication_date
from src.normalization.schema import Paper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", title).lower()
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


_ARXIV_URL_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", re.IGNORECASE)
_ARXIV_ID_RE  = re.compile(r"^arxiv:(\d{4}\.\d{4,5})", re.IGNORECASE)


def _arxiv_id(paper: Paper) -> str | None:
    """Extract a bare arXiv ID (e.g. '2501.12345') from a paper, if available."""
    # arXiv-sourced papers: id = "arxiv:2501.12345v2"
    m = _ARXIV_ID_RE.match(paper.id)
    if m:
        return m.group(1)
    # S2/conference papers whose paper_url points to arXiv
    if paper.paper_url:
        m = _ARXIV_URL_RE.search(paper.paper_url)
        if m:
            return m.group(1)
    return None


def _completeness(paper: Paper) -> int:
    """Score how much useful metadata a paper has (higher = keep this one)."""
    score = 0
    for value in (paper.abstract, paper.pdf_url, paper.summary, paper.why_it_matters):
        if value:
            score += 1
    score += len(paper.authors)
    score += len(paper.tags)
    score += len(paper.limitations)
    score += len(paper.future_work)
    if paper.citations:
        score += 1
    # Prefer accepted conference version over bare arXiv preprint
    if paper.venue and paper.venue.lower() not in ("arxiv", ""):
        score += 5
    if paper.conference_rank:
        score += 3
    return score


def _similarity(a: str, b: str) -> float:
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _merge(winner: Paper, loser: Paper) -> Paper:
    """Fill missing fields in winner from loser where winner is empty."""
    scalar_fields = (
        "abstract", "pdf_url", "summary", "key_contribution", "why_it_matters",
        "content_hook", "plain_english_explanation", "technical_summary",
        "tweet_thread", "linkedin_post", "newsletter_blurb", "video_script_outline",
        "one_line_takeaway", "biggest_caveat", "read_this_if", "difficulty_reason",
    )
    for field in scalar_fields:
        if not getattr(winner, field) and getattr(loser, field):
            setattr(winner, field, getattr(loser, field))

    list_fields = (
        "authors", "author_ids", "affiliations_raw", "lab_ids", "university_ids",
        "topics", "tags", "prerequisites", "limitations", "future_work",
        "research_gap_signals",
    )
    for field in list_fields:
        values = [*getattr(winner, field), *getattr(loser, field)]
        combined = list(dict.fromkeys(values))
        setattr(winner, field, combined)

    winner.citations = max(winner.citations, loser.citations)
    return winner


# ── Deduplicator ──────────────────────────────────────────────────────────────

class Deduplicator:
    """Remove duplicate / near-duplicate papers from a list."""

    def __init__(self, threshold: float = 0.85) -> None:
        self.threshold = threshold

    def deduplicate(self, papers: list[Paper]) -> list[Paper]:
        # Pass 1: exact record ID or arXiv ID match
        arxiv_index: dict[str, int] = {}   # arXiv ID → index in `result`
        record_index: dict[str, int] = {}  # exact nonempty record ID to result index
        result: list[Paper] = []

        for paper in papers:
            record_id = paper.id if paper.id and paper.id.strip() else ""
            aid = _arxiv_id(paper)
            match_idx = record_index.get(record_id) if record_id else None
            if match_idx is None and aid:
                match_idx = arxiv_index.get(aid)

            if match_idx is not None:
                existing = result[match_idx]
                same_record = bool(record_id and record_id == existing.id)
                # Fresh records precede archives; dates must not cross publication versions.
                source_date = (
                    normalize_publication_date(existing.published_date)
                    or normalize_publication_date(paper.published_date)
                ) if same_record else None
                if _completeness(paper) > _completeness(existing):
                    result[match_idx] = _merge(paper, existing)
                else:
                    _merge(existing, paper)
                if source_date is not None:
                    result[match_idx].published_date = source_date
                if record_id:
                    record_index[record_id] = match_idx
                if aid:
                    arxiv_index[aid] = match_idx
                continue

            idx = len(result)
            result.append(paper)
            if record_id:
                record_index[record_id] = idx
            if aid:
                arxiv_index[aid] = idx

        # ── Pass 2: title Jaccard similarity via bigram inverted index ────────
        # O(n²) linear scan is too slow at >10k papers.  Instead, build an
        # inverted index: title-bigram → [kept paper indices].  For each new
        # paper we only compare against kept papers that share ≥1 bigram with
        # it — typically ≪1% of the corpus, giving near-O(n) performance.
        normalised = [_normalise_title(p.title) for p in result]

        # bigram → list of indices already in `kept`
        bigram_idx: dict[tuple[str, str], list[int]] = defaultdict(list)
        kept: list[int] = []

        for i in range(len(result)):
            words = normalised[i].split()
            # Build bigrams; fall back to unigrams for very short titles
            bigrams: list[tuple[str, str]] = (
                [(words[k], words[k + 1]) for k in range(len(words) - 1)]
                if len(words) >= 2
                else [(w, "") for w in words]
            )

            # Gather candidate kept-paper indices sharing ≥1 bigram
            candidates: set[int] = set()
            for bg in bigrams:
                candidates.update(bigram_idx.get(bg, []))

            # Check Jaccard only against candidates
            best_match: int | None = None
            for j in sorted(candidates):
                if _similarity(normalised[i], normalised[j]) >= self.threshold:
                    best_match = j
                    break

            if best_match is None:
                kept.append(i)
                for bg in set(bigrams):
                    bigram_idx[bg].append(i)
            else:
                existing = result[best_match]
                if _completeness(result[i]) > _completeness(existing):
                    result[best_match] = _merge(result[i], existing)
                    previous_words = normalised[best_match].split()
                    previous_bigrams = (
                        [(previous_words[k], previous_words[k + 1])
                         for k in range(len(previous_words) - 1)]
                        if len(previous_words) >= 2
                        else [(w, "") for w in previous_words]
                    )
                    normalised[best_match] = normalised[i]
                    for bg in set(previous_bigrams):
                        bigram_idx[bg].remove(best_match)
                    for bg in set(bigrams):
                        bigram_idx[bg].append(best_match)
                else:
                    _merge(existing, result[i])

        return [result[i] for i in kept]
