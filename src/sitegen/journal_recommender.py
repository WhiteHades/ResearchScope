"""Build static data for the Journal Recommender.

Uses the same TF-IDF engine as conference_recommender.py but targets
journal papers from journals_db.json / journals.json.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

ROOT           = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "site" / "data" / "journal_recommender.json"

log = logging.getLogger(__name__)

STOP_WORDS = {
    "a","an","and","are","as","at","be","by","can","for","from","has","have",
    "in","into","is","it","its","may","method","model","models","of","on","or",
    "our","paper","propose","show","study","that","the","their","these","this",
    "to","use","using","via","we","with","which","new","novel","methods","task",
    "tasks","achieve","achieves","approach","approaches","based","different",
    "first","however","results",
}

# Journals that are too generic or are conference venues misclassified
IGNORED_JOURNALS = {"", "arxiv", "corr", "unknown", "openreview"}

JOURNAL_METADATA: dict[str, dict[str, Any]] = {
    "JMLR":     {"website": "https://jmlr.org",                               "impact_factor": 6.3,  "review_weeks": "8–16",  "open_access": True,  "publisher": "JMLR Inc."},
    "TMLR":     {"website": "https://jmlr.org/tmlr",                          "impact_factor": None, "review_weeks": "4–8",   "open_access": True,  "publisher": "JMLR Inc."},
    "TACL":     {"website": "https://aclanthology.org/venues/tacl",            "impact_factor": 9.3,  "review_weeks": "8–12",  "open_access": True,  "publisher": "MIT Press"},
    "TPAMI":    {"website": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=34",   "impact_factor": 23.6, "review_weeks": "12–24", "open_access": False, "publisher": "IEEE"},
    "IJCV":     {"website": "https://link.springer.com/journal/11263",         "impact_factor": 19.5, "review_weeks": "12–20", "open_access": False, "publisher": "Springer"},
    "AIJ":      {"website": "https://www.sciencedirect.com/journal/artificial-intelligence", "impact_factor": 14.4, "review_weeks": "8–16",  "open_access": False, "publisher": "Elsevier"},
    "Artificial Intelligence": {"website": "https://www.sciencedirect.com/journal/artificial-intelligence", "impact_factor": 14.4, "review_weeks": "8–16", "open_access": False, "publisher": "Elsevier"},
    "TNNLS":    {"website": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=5962385", "impact_factor": 14.3, "review_weeks": "8–16", "open_access": False, "publisher": "IEEE"},
    "NMI":      {"website": "https://www.nature.com/natmachintell",            "impact_factor": 23.8, "review_weeks": "4–12",  "open_access": False, "publisher": "Nature Portfolio"},
    "Nature Machine Intelligence": {"website": "https://www.nature.com/natmachintell", "impact_factor": 23.8, "review_weeks": "4–12", "open_access": False, "publisher": "Nature Portfolio"},
    "CSUR":     {"website": "https://dl.acm.org/journal/csur",                "impact_factor": 23.8, "review_weeks": "12–20", "open_access": False, "publisher": "ACM"},
    "ACM Computing Surveys": {"website": "https://dl.acm.org/journal/csur",   "impact_factor": 23.8, "review_weeks": "12–20", "open_access": False, "publisher": "ACM"},
    "TIP":      {"website": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=83", "impact_factor": 10.6, "review_weeks": "8–16", "open_access": False, "publisher": "IEEE"},
    "IEEE Transactions on Image Processing": {"website": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=83", "impact_factor": 10.6, "review_weeks": "8–16", "open_access": False, "publisher": "IEEE"},
    "MLJ":      {"website": "https://link.springer.com/journal/10994",        "impact_factor": 7.9,  "review_weeks": "8–16",  "open_access": False, "publisher": "Springer"},
    "Machine Learning": {"website": "https://link.springer.com/journal/10994","impact_factor": 7.9,  "review_weeks": "8–16",  "open_access": False, "publisher": "Springer"},
    "TKDE":     {"website": "https://ieeexplore.ieee.org/xpl/RecentIssue.jsp?punumber=69", "impact_factor": 8.9, "review_weeks": "8–16", "open_access": False, "publisher": "IEEE"},
    "DAMI":     {"website": "https://link.springer.com/journal/10618",        "impact_factor": 4.8,  "review_weeks": "8–16",  "open_access": False, "publisher": "Springer"},
    "Data Mining and Knowledge Discovery": {"website": "https://link.springer.com/journal/10618", "impact_factor": 4.8, "review_weeks": "8–16", "open_access": False, "publisher": "Springer"},
    "NN":       {"website": "https://www.sciencedirect.com/journal/neural-networks", "impact_factor": 7.8, "review_weeks": "6–12", "open_access": False, "publisher": "Elsevier"},
    "Neural Networks": {"website": "https://www.sciencedirect.com/journal/neural-networks", "impact_factor": 7.8, "review_weeks": "6–12", "open_access": False, "publisher": "Elsevier"},
    "PR":       {"website": "https://www.sciencedirect.com/journal/pattern-recognition", "impact_factor": 8.0, "review_weeks": "6–12", "open_access": False, "publisher": "Elsevier"},
    "Pattern Recognition": {"website": "https://www.sciencedirect.com/journal/pattern-recognition", "impact_factor": 8.0, "review_weeks": "6–12", "open_access": False, "publisher": "Elsevier"},
    "CL":       {"website": "https://aclanthology.org/venues/cl",              "impact_factor": 8.1,  "review_weeks": "8–16",  "open_access": True,  "publisher": "MIT Press"},
    "Computational Linguistics": {"website": "https://aclanthology.org/venues/cl", "impact_factor": 8.1, "review_weeks": "8–16", "open_access": True, "publisher": "MIT Press"},
    "IPM":      {"website": "https://www.sciencedirect.com/journal/information-processing-and-management", "impact_factor": 7.4, "review_weeks": "6–12", "open_access": False, "publisher": "Elsevier"},
    "Information Processing & Management": {"website": "https://www.sciencedirect.com/journal/information-processing-and-management", "impact_factor": 7.4, "review_weeks": "6–12", "open_access": False, "publisher": "Elsevier"},
    "JACM":     {"website": "https://dl.acm.org/journal/jacm",                "impact_factor": 4.5,  "review_weeks": "16–24", "open_access": False, "publisher": "ACM"},
    "Journal of the ACM": {"website": "https://dl.acm.org/journal/jacm",      "impact_factor": 4.5,  "review_weeks": "16–24", "open_access": False, "publisher": "ACM"},
    "NatComms": {"website": "https://www.nature.com/ncomms",                  "impact_factor": 16.6, "review_weeks": "4–12",  "open_access": True,  "publisher": "Nature Portfolio"},
    "Nature Communications": {"website": "https://www.nature.com/ncomms",     "impact_factor": 16.6, "review_weeks": "4–12",  "open_access": True,  "publisher": "Nature Portfolio"},
    "TOIS":     {"website": "https://dl.acm.org/journal/tois",                "impact_factor": 5.6,  "review_weeks": "8–16",  "open_access": False, "publisher": "ACM"},
    "ACM Transactions on Information Systems": {"website": "https://dl.acm.org/journal/tois", "impact_factor": 5.6, "review_weeks": "8–16", "open_access": False, "publisher": "ACM"},
}

FIELD_LABELS = {
    "any": "Any field",
    "ML":  "Machine Learning",
    "NLP": "NLP / Language",
    "CV":  "Computer Vision",
    "AI":  "AI / Agents / Reasoning",
    "HCI": "HCI / Human-AI Interaction",
    "IR":  "Information Retrieval",
    "DM":  "Data Mining",
    "General": "General / Multidisciplinary",
}

FIELD_HINTS = {
    "ML":  {"machine","learning","optimization","representation","bayesian","reinforcement","generalization","training","gradient"},
    "NLP": {"language","nlp","translation","linguistic","multilingual","summarization","dialogue","question","answering","llm"},
    "CV":  {"vision","image","video","visual","segmentation","detection","recognition","3d","geometry","diffusion"},
    "AI":  {"agent","planning","reasoning","knowledge","search","decision","autonomous","logic","artificial"},
    "HCI": {"human","user","interface","interaction","usability","study","participants","design","qualitative"},
    "IR":  {"retrieval","search","ranking","query","relevance","recommendation","recommendations","rag"},
    "DM":  {"mining","graph","graphs","knowledge","discovery","anomaly","causal","large","scale"},
    "General": {"survey","review","benchmark","dataset","analysis","empirical","application"},
}

JOURNAL_EXPECTATIONS: dict[str, list[str]] = {
    "ML": [
        "Broader scope than a conference paper — include extended theory, additional experiments, or a new application domain.",
        "Thorough related work section situating the contribution among journal-length prior art.",
        "Reproducibility: open code, detailed hyperparameters, and discussion of failure modes.",
        "Journals expect polished writing and self-contained exposition for a broad readership.",
    ],
    "NLP": [
        "Extended empirical analysis across multiple datasets, languages, or model families.",
        "Deeper error analysis and discussion of linguistic phenomena beyond conference scope.",
        "Responsible AI considerations: bias, safety, and limitations of language models.",
        "Journal revision cycles allow thorough reviewer response — budget time for 2–3 rounds.",
    ],
    "CV": [
        "Strong visual benchmarks with extended qualitative analysis beyond conference figures.",
        "Ablations covering architecture choices, training regimes, and failure cases.",
        "Discussion of real-world applicability, dataset biases, and scope of visual claims.",
        "Extended supplementary with implementation details and reproducibility artefacts.",
    ],
    "AI": [
        "A complete formalization of the AI problem with proofs or extended formal results.",
        "Evaluation in realistic or deployed settings beyond toy domains.",
        "Thorough positioning against knowledge representation, planning, and agent literature.",
    ],
    "HCI": [
        "A rigorous study design with appropriate participant count and statistical reporting.",
        "Discussion of ecological validity, participant diversity, and generalizability.",
        "Design implications grounded in evidence, not speculation.",
    ],
    "IR": [
        "Extended retrieval evaluation: multiple collections, query types, and efficiency analysis.",
        "Comparison against recent dense, sparse, and hybrid retrieval baselines.",
        "Discussion of robustness, out-of-domain transfer, and deployment constraints.",
    ],
    "DM": [
        "Large-scale experiments on realistic datasets with scalability analysis.",
        "Comparison against predictive modeling and specialized DM baselines.",
        "Robustness analysis and discussion of practical deployment.",
    ],
    "General": [
        "Journal submissions require broader framing: situate within multiple research communities.",
        "Extended experiments, ablations, and analysis beyond what fits a conference paper.",
        "High-quality writing for a multidisciplinary audience — avoid assuming domain expertise.",
    ],
}

CONTRIBUTION_TYPES = [
    {"id": "any",       "label": "Any / not sure"},
    {"id": "original",  "label": "Original research"},
    {"id": "extended",  "label": "Extended conference paper"},
    {"id": "survey",    "label": "Survey / review"},
    {"id": "empirical", "label": "Empirical / benchmark study"},
]


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+-]{2,}", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) <= 32]


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


def _load_journal_sources() -> list[dict]:
    paths = [
        ROOT / "site" / "data" / "journals_db.json",
        ROOT / "site" / "data" / "journals.json",
    ]
    papers: dict[str, dict] = {}
    for path in paths:
        for paper in _load_json(path):
            if not isinstance(paper, dict):
                continue
            venue = str(paper.get("venue") or "").strip()
            if not venue or venue.lower() in IGNORED_JOURNALS:
                continue
            if str(paper.get("source_type", "")).lower() not in {"journal", ""}:
                continue
            key = str(paper.get("id") or paper.get("paper_url") or f"{venue}:{paper.get('title','')}")
            papers[key] = paper
    return list(papers.values())


def _paper_text(paper: dict) -> str:
    tags = " ".join(str(t) for t in (paper.get("tags") or []) if t)
    return " ".join([
        str(paper.get("title", "")),
        str(paper.get("abstract", "")),
        str(paper.get("summary", "")),
        str(paper.get("key_contribution", "")),
        tags,
    ])


def _infer_field(papers: list[dict]) -> str:
    counter: Counter = Counter()
    for paper in papers[:120]:
        counter.update(_tokenize(_paper_text(paper)))
    scores = {f: sum(counter[t] for t in hints) for f, hints in FIELD_HINTS.items()}
    best, best_score = max(scores.items(), key=lambda x: x[1])
    return best if best_score > 0 else "ML"


def _derive_keywords(papers: list[dict], field: str, limit: int = 85) -> list[str]:
    term_counter: Counter = Counter()
    phrase_counter: Counter = Counter()
    for paper in papers:
        text   = _paper_text(paper)
        tokens = _tokenize(text)
        term_counter.update(tokens)
        for tag in (paper.get("tags") or []):
            phrase_counter[str(tag).strip().lower()] += 3
        for a, b in zip(tokens, tokens[1:]):
            if a != b:
                phrase_counter[f"{a} {b}"] += 1

    keywords = list(FIELD_HINTS.get(field, set()))
    for phrase, _ in phrase_counter.most_common(45):
        if 3 <= len(phrase) <= 56 and phrase not in keywords:
            keywords.append(phrase)
    for term, _ in term_counter.most_common(55):
        if term not in keywords:
            keywords.append(term)
    return keywords[:limit]


def _build_tfidf_profiles(
    venue_docs: dict[str, list[str]],
    fallback: dict[str, list[str]],
    limit: int = 85,
) -> dict[str, list[dict]]:
    shorts = list(venue_docs)
    if not shorts:
        return {}
    documents, doc_venues = [], []
    for short in shorts:
        for doc in venue_docs[short]:
            if doc.strip():
                documents.append(doc)
                doc_venues.append(short)
    if not documents:
        return {s: [{"term": t, "weight": 0.35} for t in fallback.get(s, [])[:limit]] for s in shorts}

    vec = TfidfVectorizer(
        tokenizer=_tokenize, token_pattern=None, ngram_range=(1, 2),
        min_df=1, max_df=0.92, sublinear_tf=True, norm="l2", max_features=4000,
    )
    matrix      = vec.fit_transform(documents)
    feat_names  = vec.get_feature_names_out()
    scores_map: dict[str, Counter] = {s: Counter() for s in shorts}
    for i, short in enumerate(doc_venues):
        row = matrix.getrow(i)
        for fi, sc in zip(row.indices, row.data):
            scores_map[short][str(feat_names[fi])] += float(sc)

    profiles = {}
    for short in shorts:
        sc = scores_map[short]
        if not sc:
            profiles[short] = [{"term": t, "weight": 0.35} for t in fallback.get(short, [])[:limit]]
            continue
        max_sc = sc.most_common(1)[0][1] or 1.0
        items, seen = [], set()
        for term, val in sc.most_common(limit):
            term = term.strip()
            if term and term not in seen:
                seen.add(term)
                items.append({"term": term, "weight": round(val / max_sc, 4)})
        for t in fallback.get(short, []):
            if t not in seen and len(items) < limit:
                items.append({"term": t, "weight": 0.2})
                seen.add(t)
        profiles[short] = items
    return profiles


def _sample_papers(papers: list[dict], limit: int = 18) -> list[dict]:
    ranked = sorted(papers, key=lambda p: (float(p.get("paper_score") or 0), int(p.get("year") or 0)), reverse=True)
    return [{
        "id":       p.get("id", ""),
        "title":    p.get("title", ""),
        "year":     p.get("year", ""),
        "venue":    p.get("venue", ""),
        "url":      p.get("paper_url") or p.get("url") or "",
        "tags":     (p.get("tags") or [])[:6],
        "abstract": str(p.get("abstract") or p.get("summary") or "")[:260],
        "terms":    [t for t, _ in Counter(_tokenize(_paper_text(p))).most_common(32)],
    } for p in ranked[:limit]]


def _expectations(field: str, papers: list[dict]) -> list[str]:
    base = list(JOURNAL_EXPECTATIONS.get(field, JOURNAL_EXPECTATIONS["General"]))
    types = Counter(str(p.get("paper_type", "")).strip() for p in papers if p.get("paper_type"))
    if types:
        dominant = types.most_common(1)[0][0].replace("_", " ")
        base.append(f"Recent accepted work skews toward {dominant} — make your contribution type explicit.")
    return base[:4]


def build_index() -> dict:
    papers = _load_journal_sources()
    log.info("Loaded %d journal papers", len(papers))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for paper in papers:
        venue = str(paper.get("venue") or "").strip()
        if venue and venue.lower() not in IGNORED_JOURNALS:
            grouped[venue].append(paper)

    venue_docs: dict[str, list[str]] = {}
    fallback_kw: dict[str, list[str]] = {}
    prepared = []

    for venue, vpaps in sorted(grouped.items()):
        if len(vpaps) < 3:
            continue
        ranked = sorted(vpaps, key=lambda p: (float(p.get("paper_score") or 0), int(p.get("year") or 0)), reverse=True)
        field  = _infer_field(ranked)
        kw     = _derive_keywords(ranked[:250], field)
        venue_docs[venue]  = [_paper_text(p).strip() for p in ranked[:250]]
        fallback_kw[venue] = kw

        meta = JOURNAL_METADATA.get(venue, {})
        core_rank = str(ranked[0].get("conference_rank") or "A*")
        q_rank = "Q1" if core_rank == "A*" else ("Q2" if core_rank == "A" else core_rank)
        prepared.append({
            "id":           re.sub(r"[^a-z0-9]+", "-", venue.lower()).strip("-"),
            "short":        venue,
            "name":         venue,
            "type":         "journal",
            "field":        field,
            "rank":         q_rank,
            "paper_count":  len(vpaps),
            "fallback_keywords": kw,
            "expectations": _expectations(field, ranked),
            "sample_papers": _sample_papers(ranked),
            "website":      meta.get("website", ""),
            "impact_factor": meta.get("impact_factor"),
            "review_weeks": meta.get("review_weeks", "8–16"),
            "open_access":  meta.get("open_access", False),
            "publisher":    meta.get("publisher", ""),
        })

    profiles = _build_tfidf_profiles(venue_docs, fallback_kw)

    venue_rows = []
    for v in prepared:
        wk = profiles.get(v["short"], [])
        venue_rows.append({k: val for k, val in v.items() if k not in {"fallback_keywords"}} | {
            "keywords": [i["term"] for i in wk],
            "weighted_keywords": wk,
        })

    venue_rows.sort(key=lambda v: (-v.get("impact_factor") or 0, -v["paper_count"]))

    return {
        "schema_version": 1,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "type":           "journal",
        "fields":         [{"id": k, "label": l} for k, l in FIELD_LABELS.items()],
        "contribution_types": CONTRIBUTION_TYPES,
        "venues":         venue_rows,
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def maybe_stage(path: Path) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    try:
        subprocess.run(["git", "add", str(path.relative_to(ROOT))], cwd=ROOT, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Build Journal Recommender static JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = build_index()
    write_json(args.output, data)
    print(f"wrote {args.output} ({len(data['venues'])} journal profiles)")
    maybe_stage(args.output)


if __name__ == "__main__":
    main()
