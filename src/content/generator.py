"""
Content engine: generates creator-ready outputs for selected papers
and builds the daily editorial queue.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.content.llm_cache import LLMFieldCache
from src.normalization.schema import Author, Lab, Paper, ResearchGap, Topic


def _first_sentences(text: str, n: int = 2) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(sentences[:n])


def _truncate(text: str, max_chars: int = 300) -> str:
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


class ContentGenerator:
    """Generate paper text and editorial fields.

    Five paper text fields prefer cached model output. Missing entries use
    excerpts or explicit notices.
    """

    def __init__(self, llm_cache: LLMFieldCache | None = None):
        self.llm = llm_cache if llm_cache is not None else LLMFieldCache.load()

    def _cached(self, paper: Paper, field: str) -> str | None:
        return self.llm.get(paper.id, paper.title or "", paper.abstract or "", field)

    def enrich(self, paper: Paper) -> Paper:
        paper.summary = self._summary(paper)
        paper.key_contribution = self._key_contribution(paper)
        paper.why_it_matters = self._why_it_matters(paper)
        paper.content_hook = self._hook(paper)
        paper.plain_english_explanation = self._plain_english(paper)
        paper.technical_summary = self._technical_summary(paper)
        paper.one_line_takeaway = self._one_liner(paper)
        paper.biggest_caveat = self._biggest_caveat(paper)
        paper.read_this_if = self._read_this_if(paper)
        paper.tweet_thread = self._tweet_thread(paper)
        paper.linkedin_post = self._linkedin_post(paper)
        paper.newsletter_blurb = self._newsletter_blurb(paper)
        paper.video_script_outline = self._video_script(paper)
        return paper

    # ── Backward compat ───────────────────────────────────────────────────────

    def generate_summary(self, paper: Paper) -> str:
        return self._summary(paper)

    def generate_why_it_matters(self, paper: Paper) -> str:
        return self._why_it_matters(paper)

    # ── Fields ────────────────────────────────────────────────────────────────

    def _summary(self, paper: Paper) -> str:
        if cached := self._cached(paper, "summary"):
            return cached
        return _first_sentences(paper.abstract, 2) if paper.abstract else ""

    def _key_contribution(self, paper: Paper) -> str:
        if cached := self._cached(paper, "key_contribution"):
            return cached
        if not paper.abstract:
            return ""
        # Find the sentence with the strongest novelty signal
        sentences = re.split(r"(?<=[.!?])\s+", paper.abstract.strip())
        novelty_re = re.compile(
            r"\b(propose|introduce|present|show|demonstrate|achieve|outperform|novel)\b",
            re.IGNORECASE,
        )
        for sent in sentences:
            if novelty_re.search(sent):
                return sent.strip()
        return sentences[0].strip() if sentences else ""

    def _why_it_matters(self, paper: Paper) -> str:
        if cached := self._cached(paper, "why_it_matters"):
            return cached
        return "The significance of this paper has not been verified from the available text."

    def _hook(self, paper: Paper) -> str:
        return paper.title or "Paper title unavailable."

    def _plain_english(self, paper: Paper) -> str:
        if cached := self._cached(paper, "plain_english_explanation"):
            return cached
        if not paper.abstract:
            return ""
        summary = _first_sentences(paper.abstract, 3)
        return f"Abstract excerpt, not a simplified explanation: {summary}"

    def _technical_summary(self, paper: Paper) -> str:
        if not paper.abstract:
            return ""
        return _truncate(paper.abstract, 500)

    def _one_liner(self, paper: Paper) -> str:
        if cached := self._cached(paper, "one_line_takeaway"):
            return cached
        contribution = self._key_contribution(paper)
        if contribution:
            return _truncate(contribution, 120)
        return _truncate(paper.title, 120)

    def _biggest_caveat(self, paper: Paper) -> str:
        if paper.limitations:
            return f"Provided limitation text: {paper.limitations[0]}"
        # try to extract from abstract
        caveat_re = re.compile(
            r"\b(?:limitations?|caveats?|however|but|note that|does not|cannot)\b[^.!?]{5,150}[.!?]",
            re.IGNORECASE,
        )
        if paper.abstract:
            m = caveat_re.search(paper.abstract)
            if m:
                return f"Abstract excerpt: {m.group(0).strip()}"
        return "No paper specific caveat was verified from the available text. Check the full paper."

    def _read_this_if(self, paper: Paper) -> str:
        level = {"L1": "a beginner", "L2": "familiar with ML", "L3": "an advanced practitioner",
                 "L4": "a researcher at the frontier"}.get(paper.difficulty_level, "interested in AI")
        tag = paper.tags[0] if paper.tags else "this area"
        return f"Read this if you are {level} and want to understand recent progress in {tag}."

    # ── Creator formats ───────────────────────────────────────────────────────

    def _tweet_thread(self, paper: Paper) -> str:
        hook = self._hook(paper)
        one_liner = self._one_liner(paper)
        caveat = self._biggest_caveat(paper)
        authors_str = ", ".join(paper.authors[:3]) + (" et al." if len(paper.authors) > 3 else "")
        url = paper.paper_url or paper.pdf_url or ""
        return (
            f"🧵 1/ {hook}\n\n"
            f"2/ Key finding: {one_liner}\n\n"
            f"3/ Why it matters: {self._why_it_matters(paper)}\n\n"
            f"4/ Main caveat: {caveat}\n\n"
            f"5/ Paper: {paper.title}\n"
            f"Authors: {authors_str}\n"
            f"{url}"
        )

    def _linkedin_post(self, paper: Paper) -> str:
        hook = self._hook(paper)
        why = self._why_it_matters(paper)
        url = paper.paper_url or paper.pdf_url or ""
        tags = " ".join(f"#{t.replace(' ', '').replace('/', '')}" for t in paper.tags[:4])
        return (
            f"{hook}\n\n"
            f"{why}\n\n"
            f"Key contribution: {self._one_liner(paper)}\n\n"
            f"Read the paper: {paper.title}\n{url}\n\n"
            f"{tags}"
        )

    def _newsletter_blurb(self, paper: Paper) -> str:
        summary = _first_sentences(paper.abstract, 2) if paper.abstract else ""
        url = paper.paper_url or paper.pdf_url or ""
        venue_year = f"{paper.venue}, {paper.year}" if paper.venue else str(paper.year)
        return (
            f"**{paper.title}** ({venue_year})\n\n"
            f"{summary}\n\n"
            f"*Why it matters:* {self._why_it_matters(paper)}\n\n"
            f"[Read the paper →]({url})"
        )

    def _video_script(self, paper: Paper) -> str:
        return (
            f"## Video Script Outline: {paper.title}\n\n"
            f"**Hook (0–15s):** {self._hook(paper)}\n\n"
            f"**Problem (15–45s):** What gap does this paper address?\n"
            f"{self._biggest_caveat(paper)}\n\n"
            f"**Solution (45–90s):** {self._key_contribution(paper)}\n\n"
            f"**Why it matters (90–120s):** {self._why_it_matters(paper)}\n\n"
            f"**Key result (120–150s):** {self._one_liner(paper)}\n\n"
            f"**Caveats (150–180s):** {self._biggest_caveat(paper)}\n\n"
            f"**Call to action (180–210s):** Read the full paper and try it yourself.\n"
            f"Link: {paper.paper_url or paper.pdf_url or ''}"
        )


# ── Editorial queue ───────────────────────────────────────────────────────────

class EditorialQueue:
    """Build the daily editorial queue from processed data."""

    # Paper of the Day and Weekly Digest are arXiv-only —
    # conference papers are historical proceedings, not "new" discoveries.
    _ARXIV_VENUES = {"arXiv", "Unknown", "", None}

    def build(
        self,
        papers: list[Paper],
        authors: list[Author],
        labs: list[Lab],
        topics: list[Topic],
        gaps: list[ResearchGap],
    ) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Only arXiv papers for editorial — conference papers are historical proceedings
        arxiv_papers = [p for p in papers if p.venue in self._ARXIV_VENUES]
        pool = arxiv_papers if arxiv_papers else papers  # fallback if empty

        # Sort for selection
        by_score    = sorted(pool, key=lambda p: -p.paper_score)
        by_content  = sorted(pool, key=lambda p: -p.content_potential_score)
        by_surprise = sorted(pool, key=lambda p: -(p.score_breakdown.get("content_potential", {}).get("surprise", 0)))

        top5 = [self._paper_stub(p) for p in by_score[:5]]
        underrated = self._pick_underrated(pool)
        breakout_author = self._pick_breakout_author(authors)
        rising_lab = self._pick_rising_lab(labs)
        emerging_trend = self._pick_emerging_trend(topics)
        gap = self._pick_gap(gaps)

        return {
            "date": today,
            "top_papers": top5,
            "underrated_paper": underrated,
            "breakout_author": breakout_author,
            "rising_lab": rising_lab,
            "emerging_trend": emerging_trend,
            "research_gap": gap,
        }

    @staticmethod
    def _paper_stub(p: Paper) -> dict:
        return {
            "id": p.id,
            "title": p.title,
            "authors": p.authors[:3],
            "venue": p.venue,
            "year": p.year,
            "tags": p.tags[:4],
            "paper_score": p.paper_score,
            "read_first_score": p.read_first_score,
            "content_potential_score": p.content_potential_score,
            "difficulty_level": p.difficulty_level,
            "why_it_matters": p.why_it_matters,
            "one_line_takeaway": p.one_line_takeaway,
            "content_hook": p.content_hook,
            "paper_url": p.paper_url,
        }

    @staticmethod
    def _pick_underrated(papers: list[Paper]) -> dict | None:
        # Underrated: high paper_score but lower citation count (ratio)
        candidates = [
            p for p in papers
            if p.paper_score >= 5 and p.citations <= 10
        ]
        if not candidates:
            candidates = papers
        best = max(candidates, key=lambda p: p.paper_score, default=None)
        if not best:
            return None
        return {
            "id": best.id,
            "title": best.title,
            "paper_score": best.paper_score,
            "citations": best.citations,
            "reason": "Strong paper score with low citation count — possibly underexposed.",
            "paper_url": best.paper_url,
        }

    @staticmethod
    def _pick_breakout_author(authors: list[Author]) -> dict | None:
        # Rising author: high momentum, fewer total papers (not established)
        candidates = [a for a in authors if 2 <= len(a.paper_ids) <= 10]
        if not candidates:
            candidates = authors
        best = max(candidates, key=lambda a: a.momentum_score, default=None)
        if not best:
            return None
        return {
            "author_id": best.author_id,
            "name": best.name,
            "momentum_score": best.momentum_score,
            "paper_count": len(best.paper_ids),
            "topics": best.topics[:3],
            "reason": f"Rising researcher with momentum score {best.momentum_score:.1f}/10.",
        }

    @staticmethod
    def _pick_rising_lab(labs: list[Lab]) -> dict | None:
        if not labs:
            return None
        best = max(labs, key=lambda l: l.momentum_score, default=None)
        if not best:
            return None
        return {
            "lab_id": best.lab_id,
            "name": best.name,
            "momentum_score": best.momentum_score,
            "paper_count": len(best.paper_ids),
            "topics": best.topics[:3],
        }

    @staticmethod
    def _pick_emerging_trend(topics: list[Topic]) -> dict | None:
        if not topics:
            return None
        best = max(topics, key=lambda t: t.trend_score, default=None)
        if not best:
            return None
        return {
            "topic_id": best.id,
            "name": best.name,
            "trend_score": best.trend_score,
            "paper_count": len(best.paper_ids),
            "gap_summary": best.gap_summary,
        }

    @staticmethod
    def _pick_gap(gaps: list[ResearchGap]) -> dict | None:
        # Prefer explicit evidence without treating coverage as calibrated confidence.
        explicit = [g for g in gaps if g.gap_type == "explicit"]
        pool = explicit or gaps
        if not pool:
            return None
        best = max(pool, key=lambda g: g.frequency, default=None)
        if not best:
            return None
        return {
            "gap_id": best.gap_id,
            "topic": best.topic,
            "title": best.title,
            "description": best.description,
            "frequency": best.frequency,
            "starter_idea": best.starter_idea,
            "gap_type": best.gap_type,
        }
