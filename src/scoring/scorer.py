"""
Multi-score system for ResearchScope.

Four independent scores, each 0–10 with a breakdown dict and plain-English reason:

  1. paper_score            — "how significant is this paper" (impact + quality)
  2. read_first_score       — "what should I read first" (clarity + accessibility)
  3. content_potential_score — "worth discussing publicly" (outreach / creator value)
  4. author_momentum_score  — used by aggregator, not stored on paper

v2 algorithm changes vs v1:
  - Recency weight cut from 0.35 → 0.12; exponential decay instead of linear
  - Completeness removed (metadata presence ≠ paper quality)
  - citation_velocity added (0.15): rewards fast-rising papers independent of age
  - contribution_depth added (0.15): abstract structure completeness check
  - quality_hint (0.25): now source-type aware (preprint / conference / journal)
  - novelty (0.12): length-normalized, capped at 4 unique signals, tighter regexes
  - practical/surprise regexes narrowed to cut false positives on common vocab
  - paper_type adjustments: survey/replication reduce score; dataset/negative boost
  - author_momentum gains recent_velocity component
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.normalization.schema import Author, Paper

_CURRENT_YEAR = datetime.now(timezone.utc).year

# ── Weight config ─────────────────────────────────────────────────────────────

def _load_weights() -> dict[str, Any]:
    cfg = Path(__file__).resolve().parents[2] / "config" / "weights.yaml"
    try:
        import yaml  # type: ignore
        with open(cfg, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}

_WEIGHTS: dict[str, Any] = _load_weights()

def _w(score_name: str, component: str, default: float) -> float:
    return float((_WEIGHTS.get(score_name) or {}).get(component, default))

def _rank_score(rank: str) -> float:
    return {"A*": 10.0, "A": 7.5, "B": 5.0, "C": 3.0}.get(rank, 0.0)

# Oral/spotlight acceptance marks the top decile of accepted work — a strong
# peer-review quality signal beyond the venue rank. Posters get no bonus
# (an accepted poster is already credited via conference_rank).
_PRESENTATION_BONUS = {"oral": 1.5, "spotlight": 1.0, "poster": 0.0}


# ── Novelty regex (phrase-level, not single words) ────────────────────────────

_NOVELTY_POSITIVE = re.compile(
    r"\b("
    r"we propose|we introduce|we present a novel|we develop a|"
    r"for the first time|first to (apply|train|use|show|propose|achieve)|"
    r"novel (approach|method|framework|architecture|algorithm|technique)|"
    r"outperform(s|ed)? (all |existing |prior |state.of.the.art|sota)|"
    r"state.of.the.art (results?|performance|accuracy)|"
    r"surpass(es|ed)? (all |existing |previous |prior )|"
    r"significant(ly)? (improve|outperform|advance|surpass|reduce|exceed)|"
    r"achieves? (state.of.the.art|sota|the best|new (high|low|record))|"
    r"(new|best) (state.of.the.art|sota|benchmark record)"
    r")\b",
    re.IGNORECASE,
)
_NOVELTY_NEGATIVE = re.compile(
    r"\b(survey of|overview of|tutorial on|review of|we compare existing|"
    r"we replicate|replication study|systematic review|meta.analysis|"
    r"we summarize|we categorize|literature review)\b",
    re.IGNORECASE,
)

# ── Contribution depth (abstract structure) ───────────────────────────────────

_CD_PROBLEM = re.compile(
    r"\b(we address|we tackle|the (challenge|problem|issue|limitation) of|"
    r"existing (methods|approaches|systems|models) (fail|lack|struggle|cannot|suffer)|"
    r"prior (work|methods|approaches) (cannot|do not|fail to|lack)|"
    r"it (is|remains) (unclear|unknown|challenging|difficult) (how|whether|to))\b",
    re.IGNORECASE,
)
_CD_METHOD = re.compile(
    r"\b(we propose|we introduce|we present|we develop|we design|we build|"
    r"our (method|approach|model|framework|system|algorithm|architecture|pipeline)|"
    r"this (paper|work) (proposes|introduces|presents|develops|describes))\b",
    re.IGNORECASE,
)
_CD_EVALUATION = re.compile(
    r"\b(we (evaluate|demonstrate|validate|benchmark|test|assess|verify)|"
    r"(evaluated?|tested?) on [\w\-\s]+(dataset|benchmark|corpus|task|collection)|"
    r"experiment(s|al) (show|demonstrate|confirm|reveal|suggest|indicate)|"
    r"on \d+ (dataset|benchmark|task|language|domain))\b",
    re.IGNORECASE,
)
_CD_QUANTITATIVE = re.compile(
    r"(\b\d+\.?\d*\s*(%|percent|pp)\s*(improvement|gain|increase|accuracy|f1|bleu|rouge)|"
    r"outperform(s|ed)?\s+(by\s+)?\d|"
    r"\+\s*\d+\.?\d*\s*(point|pp|bleu|rouge|f1|accuracy|%)|"
    r"\d+\.?\d*[x×]\s*(faster|speedup|better|improvement)|"
    r"reduce(s|d)?\s+\w+\s+by\s+\d+)",
    re.IGNORECASE,
)
_CD_LIMITATIONS = re.compile(
    r"\b(limitation|we note that|however,? (our|this)|future work|future direction|"
    r"we leave (this|it|the)|does not (handle|support|address|consider)|"
    r"not yet applicable|cannot generalize)\b",
    re.IGNORECASE,
)

# ── Practical / surprise / explain / broad (narrowed to cut false positives) ──

_SURPRISE_KWORDS = re.compile(
    r"\b(surprisingly\b|counter.intuitive|counterintuitive|"
    r"contrary to (expectation|prior work|conventional wisdom|common belief)|"
    r"challenge(s|d)? (the|existing|conventional) (assumption|belief|wisdom|understanding)|"
    r"we find (that|this) (surprisingly|unexpectedly)|"
    r"paradox(ically)?|unexpected(ly)? (effective|strong|poor|fail|succeed))\b",
    re.IGNORECASE,
)
_PRACTICAL_KWORDS = re.compile(
    r"\b(deployed? (in|at|on|to)\b|in production\b|production (system|deployment|environment)\b|"
    r"real.world (deployment|application|use case|scenario|setting|system)\b|"
    r"million.s? (user|request|query|call)\b|"
    r"latency of \d|inference (latency|speed|time|throughput)\b|serving \d+|"
    r"on.device\b|edge (inference|deployment|device|computing)\b|"
    r"industrial (setting|deployment|application|use)\b|"
    r"industry (adoption|use|application)\b)\b",
    re.IGNORECASE,
)
_EXPLAIN_KWORDS = re.compile(
    r"\b(simple(r|st)? than|requires (no|only a?)|without (training|fine.tuning|labels)\b|"
    r"(easily|straightforwardly) (extendable|applicable|interpretable)\b|"
    r"intuitive(ly)?\b|interpretable\b|explainable\b|plug.and.play\b|"
    r"drop.in replacement\b|out.of.the.box\b)\b",
    re.IGNORECASE,
)
_BROAD_KWORDS = re.compile(
    r"\b(across (domains?|tasks?|languages?|modalities?|dataset)\b|"
    r"domain.agnostic\b|task.agnostic\b|language.agnostic\b|"
    r"zero.shot (generali[sz]|transfer|on)\b|few.shot (generali[sz]|on)\b|"
    r"general.purpose\b|multi.task (learning|model|framework)\b|"
    r"generali[sz](es?|ation) (well|to|across)\b|broadly applicable\b)\b",
    re.IGNORECASE,
)
_FOUNDATIONAL_KWORDS = re.compile(
    r"\b(foundational|seminal|widely (used|adopted|cited)|"
    r"standard (benchmark|approach|architecture|practice)|"
    r"introduced (by|in)|pioneered|built on top of|"
    r"transformer|attention (is all|mechanism)|bert\b|gpt\b|resnet\b|"
    r"imagenet|word2vec|backpropagation)\b",
    re.IGNORECASE,
)
_CLARITY_INDICATORS = re.compile(
    r"\b(we propose|we present|in this (paper|work)|we show|we demonstrate|"
    r"our (approach|method|model)|we introduce|this (work|paper) (proposes?|presents?|introduces?))\b",
    re.IGNORECASE,
)

# ── Hot tags ──────────────────────────────────────────────────────────────────

_HOT_TAGS = {
    "Large Language Models", "Transformer Architectures", "Diffusion Models",
    "Retrieval-Augmented Generation", "Multimodal Learning",
    "Code Generation & Synthesis", "AI Safety & Alignment", "AI Agents & Tool Use",
}

# ── Paper-type score adjustments (added after base score, then clamped 0–10) ──

_TYPE_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "survey":          {"paper": -0.5, "read": +1.5, "content": +0.5},
    "tutorial":        {"paper": -0.5, "read": +2.0, "content": +0.5},
    "replication":     {"paper": -1.5, "read": +0.5, "content": -0.5},
    "negative_result": {"paper": -0.5, "read": +0.5, "content": +2.0},
    "dataset":         {"paper":  0.0, "read": +0.5, "content": +1.5},
    "benchmark":       {"paper":  0.0, "read": +0.5, "content": +1.5},
    "theory":          {"paper": +0.5, "read": +1.0, "content": -0.5},
    "systems":         {"paper": +0.5, "read":  0.0, "content": +1.0},
    "position":        {"paper": -0.5, "read": +0.5, "content": +1.0},
}


# ── Renowned-author lists ─────────────────────────────────────────────────────
# Tier 1: Turing Award winners, lab co-founders, seminal-paper authors
# Tier 2: prominent researchers at top labs / universities
# Tier 3: well-known contributors
# Ambiguous names (East Asian) require institution confirmation to avoid false positives.

_T1_UNAMBIGUOUS: frozenset[str] = frozenset({
    "Geoffrey Hinton", "Yann LeCun", "Yoshua Bengio",
    "Ilya Sutskever", "Demis Hassabis", "Shane Legg",
    "Ian Goodfellow", "Andrej Karpathy", "Alex Krizhevsky",
    "Diederik Kingma", "John Schulman", "Alec Radford",
    "Tom B. Brown", "Jacob Devlin", "Ashish Vaswani",
    "Noam Shazeer", "Niki Parmar", "David Silver",
    "Oriol Vinyals", "Jeff Dean", "Andrew Ng", "Fei-Fei Li",
    "Jürgen Schmidhuber",
})
_T1_AMBIGUOUS: frozenset[str] = frozenset({"Jimmy Lei Ba"})
_T2_UNAMBIGUOUS: frozenset[str] = frozenset({
    "Pieter Abbeel", "Sergey Levine", "Chelsea Finn",
    "Percy Liang", "Christopher Manning", "Dan Jurafsky",
    "Michael I. Jordan", "Trevor Darrell", "Jitendra Malik",
    "Stuart Russell", "Daphne Koller", "Bernhard Schölkopf",
    "Zoubin Ghahramani", "Max Welling", "Hugo Larochelle",
    "Aaron Courville", "Graham Neubig", "Luke Zettlemoyer",
    "Jason Weston", "Kyunghyun Cho", "Richard Socher",
    "Thomas Wolf", "Sebastian Ruder", "Roger Grosse",
    "Prafulla Dhariwal", "Samy Bengio", "Noam Brown",
    "Jakob Foerster", "Koray Kavukcuoglu", "Raia Hadsell",
    "Nando de Freitas", "Marc Lanctot",
})
_T2_AMBIGUOUS: frozenset[str] = frozenset({"Yejin Choi", "Quoc V. Le"})
_T3_UNAMBIGUOUS: frozenset[str] = frozenset({
    "Mike Lewis", "Omer Levy", "Veselin Stoyanov",
    "Kenton Lee", "Ming-Wei Chang", "Tim Salimans",
    "Alex Graves", "Ross Girshick", "Tomas Mikolov",
    "Barret Zoph", "Lukasz Kaiser", "Sam Bowman",
    "Noah A. Smith", "Regina Barzilay", "Tommi Jaakkola",
    "Ruslan Salakhutdinov", "George Dahl", "Laurent Dinh",
    "Vinod Nair", "Dragomir Radev", "Leslie Kaelbling",
})
_T3_AMBIGUOUS: frozenset[str] = frozenset({"Kaiming He", "Danqi Chen", "Jimmy Ba"})

_T1_UNAMB_LOWER = frozenset(n.lower() for n in _T1_UNAMBIGUOUS)
_T1_AMB_LOWER   = frozenset(n.lower() for n in _T1_AMBIGUOUS)
_T2_UNAMB_LOWER = frozenset(n.lower() for n in _T2_UNAMBIGUOUS)
_T2_AMB_LOWER   = frozenset(n.lower() for n in _T2_AMBIGUOUS)
_T3_UNAMB_LOWER = frozenset(n.lower() for n in _T3_UNAMBIGUOUS)
_T3_AMB_LOWER   = frozenset(n.lower() for n in _T3_AMBIGUOUS)

_TIER1_INSTITUTIONS = re.compile(
    r"\b(openai|deepmind|google\s*(?:brain|research|deepmind)?|anthropic|"
    r"meta\s*(?:ai|research|fair)?|microsoft\s*research|mit\b|"
    r"stanford|carnegie\s*mellon|cmu\b)\b",
    re.IGNORECASE,
)
_TIER2_INSTITUTIONS = re.compile(
    r"\b(berkeley|caltech|cambridge|oxford|princeton|harvard|"
    r"toronto|montreal|mila\b|vector\s*institute|"
    r"nvidia\s*research|apple\s*(?:ml|research)?|amazon\s*(?:science|research)?|"
    r"ibm\s*research|samsung\s*research|adobe\s*research|"
    r"eth\s*zurich|epfl|tsinghua|peking\s*university|pku\b|"
    r"national\s*university\s*of\s*singapore|nus\b)\b",
    re.IGNORECASE,
)
_TIER3_INSTITUTIONS = re.compile(
    r"\b(yale|columbia|cornell|michigan|ucsd|ucla|usc|georgia\s*tech|"
    r"university\s*of\s*washington|uw\b|edinburgh|imperial\s*college|"
    r"bytedance|tencent\s*(?:ai|research)?|baidu\s*(?:research)?|"
    r"huawei\s*(?:noah|research)?|alibaba\s*(?:damo)?|jd\.ai|"
    r"kakao|naver|kaist\b|postech|technion|inria\b|max\s*planck)\b",
    re.IGNORECASE,
)


# ── PaperScorer ───────────────────────────────────────────────────────────────

class PaperScorer:
    """Compute all paper scores and attach breakdowns. v2 algorithm."""

    def score(self, paper: Paper) -> Paper:
        adj = _TYPE_ADJUSTMENTS.get(paper.paper_type or "", {})

        ps  = self._paper_score(paper)
        rfs = self._read_first_score(paper)
        cps = self._content_potential_score(paper)

        paper.paper_score             = round(max(min(ps  + adj.get("paper",   0.0), 10.0), 0.0), 2)
        paper.read_first_score        = round(max(min(rfs + adj.get("read",    0.0), 10.0), 0.0), 2)
        paper.content_potential_score = round(max(min(cps + adj.get("content", 0.0), 10.0), 0.0), 2)
        paper.interestingness_score   = round(
            0.5 * paper.paper_score + 0.5 * paper.content_potential_score, 2
        )
        return paper

    # ── 1. Paper score ────────────────────────────────────────────────────────

    def _paper_score(self, paper: Paper) -> float:
        text = f"{paper.title} {paper.abstract}"

        recency  = self._recency(paper.year)
        novelty  = self._novelty(text)
        quality  = self._quality_hint(paper)
        velocity = self._citation_velocity(paper)
        depth    = self._contribution_depth(paper.abstract)
        inst     = self._institution_prestige(paper)
        author_p = self._author_prestige(paper)

        w_re = _w("paper_score", "recency",              0.12)
        w_no = _w("paper_score", "novelty",              0.12)
        w_qu = _w("paper_score", "quality_hint",         0.25)
        w_ve = _w("paper_score", "citation_velocity",    0.15)
        w_de = _w("paper_score", "contribution_depth",   0.15)
        w_in = _w("paper_score", "institution_prestige", 0.12)
        w_au = _w("paper_score", "author_prestige",      0.09)

        raw = (recency  * w_re + novelty   * w_no + quality  * w_qu
               + velocity * w_ve + depth   * w_de + inst     * w_in
               + author_p * w_au)
        score = round(min(max(raw, 0.0), 10.0), 2)

        paper.score_breakdown["paper_score"] = {
            "score":              score,
            "recency":            round(recency,  2),
            "novelty":            round(novelty,  2),
            "quality_hint":       round(quality,  2),
            "citation_velocity":  round(velocity, 2),
            "contribution_depth": round(depth,    2),
            "institution":        round(inst,     2),
            "author_prestige":    round(author_p, 2),
            "reason": self._paper_reason(
                score, recency, novelty, quality, velocity, depth, inst, author_p
            ),
        }
        return score

    @staticmethod
    def _paper_reason(score: float, recency: float, novelty: float,
                      quality: float, velocity: float, depth: float,
                      inst: float, author_p: float) -> str:
        parts = []
        if recency >= 8:   parts.append("very recent")
        elif recency <= 3: parts.append("older work")
        if novelty >= 7:   parts.append("strong contribution language")
        if quality >= 7:   parts.append("high-quality venue / citations")
        if velocity >= 6:  parts.append("fast-rising citations")
        if depth >= 7:     parts.append("well-structured contribution")
        if author_p >= 8:  parts.append("renowned author")
        elif inst >= 8:    parts.append("top-tier institution")
        if not parts:      parts.append("average across all dimensions")
        return f"Paper scores {score:.1f}/10 — {', '.join(parts)}."

    # ── 2. Read-first score ───────────────────────────────────────────────────

    def _read_first_score(self, paper: Paper) -> float:
        clarity       = self._clarity(paper.abstract)
        abstract_qual = self._abstract_quality(paper.abstract)
        foundational  = self._foundational(f"{paper.title} {paper.abstract}")
        accessibility = self._accessibility(paper.difficulty_level)
        topic_central = self._topic_centrality(paper.tags)

        w_cl = _w("read_first_score", "clarity",          0.25)
        w_aq = _w("read_first_score", "abstract_quality", 0.20)
        w_fo = _w("read_first_score", "foundational",     0.20)
        w_ac = _w("read_first_score", "accessibility",    0.20)
        w_tc = _w("read_first_score", "topic_centrality", 0.15)

        raw = (clarity * w_cl + abstract_qual * w_aq + foundational * w_fo
               + accessibility * w_ac + topic_central * w_tc)
        score = round(min(max(raw, 0.0), 10.0), 2)

        paper.score_breakdown["read_first_score"] = {
            "score":            score,
            "clarity":          round(clarity,       2),
            "abstract_quality": round(abstract_qual, 2),
            "foundational":     round(foundational,  2),
            "accessibility":    round(accessibility, 2),
            "topic_centrality": round(topic_central, 2),
            "reason": self._read_reason(score, clarity, foundational, accessibility),
        }
        return score

    @staticmethod
    def _read_reason(score: float, clarity: float, foundational: float,
                     access: float) -> str:
        parts = []
        if clarity >= 7:      parts.append("well-structured abstract")
        if foundational >= 6: parts.append("foundational concepts")
        if access >= 8:       parts.append("accessible to most readers")
        elif access <= 3:     parts.append("requires significant background")
        if not parts:         parts.append("average readability")
        return f"Read-first {score:.1f}/10 — {', '.join(parts)}."

    # ── 3. Content potential score ────────────────────────────────────────────

    def _content_potential_score(self, paper: Paper) -> float:
        text = f"{paper.title} {paper.abstract}"

        practical = self._practical(text)
        broad     = self._broad_relevance(text)
        surprise  = self._surprise(text)
        trend     = self._trend_alignment(paper.tags)
        explain   = self._explainability(text)

        w_pr = _w("content_potential_score", "practical_value", 0.28)
        w_br = _w("content_potential_score", "broad_relevance", 0.22)
        w_su = _w("content_potential_score", "surprise",        0.18)
        w_tr = _w("content_potential_score", "trend_alignment", 0.18)
        w_ex = _w("content_potential_score", "explainability",  0.14)

        raw = (practical * w_pr + broad * w_br + surprise * w_su
               + trend * w_tr + explain * w_ex)
        score = round(min(max(raw, 0.0), 10.0), 2)

        paper.score_breakdown["content_potential"] = {
            "score":           score,
            "practical":       round(practical, 2),
            "broad_relevance": round(broad,     2),
            "surprise":        round(surprise,  2),
            "trend_alignment": round(trend,     2),
            "explainability":  round(explain,   2),
            "reason": self._content_reason(score, surprise, practical, trend),
        }
        paper.content_potential_score = score
        return score

    @staticmethod
    def _content_reason(score: float, surprise: float, practical: float,
                        trend: float) -> str:
        parts = []
        if surprise >= 5:  parts.append("surprising or counter-intuitive results")
        if practical >= 6: parts.append("real-world deployment value")
        if trend >= 7:     parts.append("hot topic right now")
        if not parts:      parts.append("solid but niche audience")
        return f"Content potential {score:.1f}/10 — {', '.join(parts)}."

    # ── Component implementations ─────────────────────────────────────────────

    @staticmethod
    def _recency(year: int) -> float:
        """Exponential decay: age=0→10, age=2→6.9, age=5→3.2, age=10→1.0."""
        if not year:
            return 0.0
        age = _CURRENT_YEAR - year
        if age < 0:
            return 10.0
        if age >= 15:
            return 0.0
        return round(10.0 * math.exp(-0.185 * age), 2)

    @staticmethod
    def _novelty(text: str) -> float:
        """
        Phrase-level novelty, length-normalized.
        Caps at 4 unique signals; divides by abstract-length factor so
        long papers can't inflate score by repeating the same phrases.
        Survey/review markers subtract strongly.
        """
        pos_matches = list(_NOVELTY_POSITIVE.finditer(text))
        neg_matches = _NOVELTY_NEGATIVE.findall(text)
        words = max(len(text.split()), 1)

        pos_capped    = min(len({m.group(0).lower()[:30] for m in pos_matches}), 4)
        length_factor = max(1.0, words / 80.0)
        pos_norm      = (pos_capped / length_factor) * 2.5   # 0–10 range

        neg_penalty = min(len(neg_matches) * 2.5, 5.0)
        return round(max(min(pos_norm - neg_penalty, 10.0), 0.0), 2)

    @staticmethod
    def _quality_hint(paper: Paper) -> float:
        """
        Source-type aware quality.
        Preprints: citations only (no peer-review signal available).
        Conference: venue rank dominates, citations confirm.
        Journal: balanced between rank and citations.
        """
        rank_s = _rank_score(paper.conference_rank)
        cite_s = 0.0
        if paper.citations and paper.citations > 0:
            cite_s = min(10.0 * math.log1p(paper.citations) / math.log1p(2000), 10.0)

        src = (paper.source_type or "").lower()
        if src == "preprint":
            return round(cite_s, 2)
        if src in ("conference", "workshop"):
            tier_bonus = _PRESENTATION_BONUS.get(paper.presentation_type or "", 0.0)
            base = rank_s * 0.65 + cite_s * 0.35 if rank_s > 0 else cite_s * 0.8
            return round(min(base + tier_bonus, 10.0), 2)
        if src == "journal":
            return round(rank_s * 0.55 + cite_s * 0.45, 2)
        return round(rank_s * 0.6 + cite_s * 0.4, 2)

    @staticmethod
    def _citation_velocity(paper: Paper) -> float:
        """
        Citations per year, log-normalized to 0–10.
        150 cites/year → 10. Age floor of 0.5 years prevents divide-by-zero
        on brand-new papers and inflated scores on papers fetched within days.
        """
        if not paper.citations or paper.citations <= 0:
            return 0.0
        age = max(_CURRENT_YEAR - (paper.year or _CURRENT_YEAR), 0.5)
        velocity = paper.citations / age
        return round(min(10.0 * math.log1p(velocity) / math.log1p(150), 10.0), 2)

    @staticmethod
    def _contribution_depth(abstract: str) -> float:
        """
        Structural completeness of the abstract.
        Five elements × 2 points each = 10 max.
        Rewards abstracts that describe problem → method → evaluation →
        quantitative results → scope/limitations.
        """
        if not abstract:
            return 0.0
        score = 0.0
        if _CD_PROBLEM.search(abstract):      score += 2.0
        if _CD_METHOD.search(abstract):       score += 2.0
        if _CD_EVALUATION.search(abstract):   score += 2.0
        if _CD_QUANTITATIVE.search(abstract): score += 2.0
        if _CD_LIMITATIONS.search(abstract):  score += 2.0
        return round(min(score, 10.0), 2)

    @staticmethod
    def _abstract_quality(abstract: str) -> float:
        """Word-count adequacy + structural-indicator count."""
        if not abstract:
            return 0.0
        words = len(abstract.split())
        if words < 30:    length_s = 0.0
        elif words < 80:  length_s = 3.0
        elif words < 300: length_s = min(7.0, 3.0 + (words - 80) / 40)
        else:             length_s = max(3.0, 7.0 - (words - 300) / 200)

        struct_s = min(len(_CLARITY_INDICATORS.findall(abstract)) * 1.5, 3.0)
        return round(min(length_s + struct_s, 10.0), 2)

    @classmethod
    def _author_prestige(cls, paper: Paper) -> float:
        authors_lower = {a.lower() for a in (paper.authors or [])}
        inst_ok = cls._institution_prestige(paper) > 0

        if authors_lower & _T1_UNAMB_LOWER:              return 10.0
        if inst_ok and (authors_lower & _T1_AMB_LOWER):  return 10.0
        if authors_lower & _T2_UNAMB_LOWER:              return 7.0
        if inst_ok and (authors_lower & _T2_AMB_LOWER):  return 7.0
        if authors_lower & _T3_UNAMB_LOWER:              return 4.0
        if inst_ok and (authors_lower & _T3_AMB_LOWER):  return 4.0
        return 0.0

    @staticmethod
    def _institution_prestige(paper: Paper) -> float:
        """
        Affiliations_raw checked first; falls back to abstract only when no
        affiliation data is available (prevents crediting a paper that merely
        cites a top lab in its text).
        """
        sources = list(paper.affiliations_raw or [])
        combined = " ".join(sources) if sources else (paper.abstract or "")
        if _TIER1_INSTITUTIONS.search(combined): return 10.0
        if _TIER2_INSTITUTIONS.search(combined): return 7.0
        if _TIER3_INSTITUTIONS.search(combined): return 4.0
        return 0.0

    @staticmethod
    def _clarity(abstract: str) -> float:
        words  = len(abstract.split()) if abstract else 0
        struct = len(_CLARITY_INDICATORS.findall(abstract or ""))
        return round(min(words / 30.0, 5.0) + min(struct * 1.5, 5.0), 2)

    @staticmethod
    def _foundational(text: str) -> float:
        return round(min(len(_FOUNDATIONAL_KWORDS.findall(text)) * 2.5, 10.0), 2)

    @staticmethod
    def _accessibility(difficulty_level: str) -> float:
        return {"L1": 10.0, "L2": 7.0, "L3": 4.0, "L4": 1.5}.get(difficulty_level, 5.0)

    @staticmethod
    def _topic_centrality(tags: list[str]) -> float:
        return round(min(sum(1 for t in (tags or []) if t in _HOT_TAGS) * 2.5, 10.0), 2)

    @staticmethod
    def _surprise(text: str) -> float:
        return round(min(len(_SURPRISE_KWORDS.findall(text)) * 4.0, 10.0), 2)

    @staticmethod
    def _practical(text: str) -> float:
        return round(min(len(_PRACTICAL_KWORDS.findall(text)) * 3.0, 10.0), 2)

    @staticmethod
    def _explainability(text: str) -> float:
        return round(min(len(_EXPLAIN_KWORDS.findall(text)) * 3.0, 10.0), 2)

    @staticmethod
    def _broad_relevance(text: str) -> float:
        return round(min(len(_BROAD_KWORDS.findall(text)) * 2.5, 10.0), 2)

    @staticmethod
    def _trend_alignment(tags: list[str]) -> float:
        return round(min(sum(1 for t in (tags or []) if t in _HOT_TAGS) * 2.5, 10.0), 2)


# ── AuthorMomentumScorer ──────────────────────────────────────────────────────

class AuthorMomentumScorer:
    """Score an author's momentum given their papers."""

    def score(self, author: Author, papers_by_id: dict[str, Paper]) -> Author:
        author_papers = [papers_by_id[pid] for pid in author.paper_ids if pid in papers_by_id]
        if not author_papers:
            author.momentum_score = 0.0
            return author

        recent = [p for p in author_papers if _CURRENT_YEAR - p.year <= 2]
        prior  = [p for p in author_papers if 2 < _CURRENT_YEAR - p.year <= 4]

        recent_output    = min(len(recent) * 1.5, 10.0)
        avg_quality      = sum(p.paper_score for p in author_papers) / len(author_papers)
        acceleration     = min((len(recent) / max(len(prior), 1)) * 5.0, 10.0)
        topic_strength   = self._topic_strength(author_papers)
        conf_strength    = self._conference_strength(author_papers)
        recent_velocity  = (
            sum(PaperScorer._citation_velocity(p) for p in recent) / len(recent)
            if recent else 0.0
        )

        w_ro = _w("author_momentum", "recent_output",        0.25)
        w_aq = _w("author_momentum", "avg_quality",          0.25)
        w_ac = _w("author_momentum", "acceleration",         0.15)
        w_ts = _w("author_momentum", "topic_strength",       0.15)
        w_cs = _w("author_momentum", "conference_strength",  0.10)
        w_rv = _w("author_momentum", "recent_velocity",      0.10)

        raw = (recent_output * w_ro + avg_quality * w_aq + acceleration * w_ac
               + topic_strength * w_ts + conf_strength * w_cs + recent_velocity * w_rv)
        author.momentum_score = round(min(max(raw, 0.0), 10.0), 2)
        author.avg_paper_score = round(avg_quality, 2)
        author.momentum_breakdown = {
            "recent_output":      round(recent_output,    2),
            "avg_quality":        round(avg_quality,      2),
            "acceleration":       round(acceleration,     2),
            "topic_strength":     round(topic_strength,   2),
            "conference_strength":round(conf_strength,    2),
            "recent_velocity":    round(recent_velocity,  2),
        }
        return author

    @staticmethod
    def _topic_strength(papers: list[Paper]) -> float:
        hot = sum(1 for p in papers for t in (p.tags or []) if t in _HOT_TAGS)
        return round(min(hot * 0.8, 10.0), 2)

    @staticmethod
    def _conference_strength(papers: list[Paper]) -> float:
        if not papers:
            return 0.0
        ranked = sum(1 for p in papers if p.conference_rank in ("A*", "A"))
        return round(min(ranked / len(papers) * 10.0, 10.0), 2)
