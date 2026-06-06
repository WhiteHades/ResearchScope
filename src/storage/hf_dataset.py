"""
Hugging Face Hub dataset pusher.

Exports all ResearchScope papers to JSONL and pushes to
kishormorol/researchscope-papers on the HF Hub.

Three splits are uploaded:
  papers.jsonl         — raw metadata (all fields, good for pretraining)
  instruct.jsonl       — instruction-tuning format (summary, key contribution,
                         why_it_matters tasks)
  sections.jsonl       — per-section fine-tuning rows for A* papers (real
                         introduction / related_work / method / … body text),
                         produced by scripts/build_sections.py

Run automatically when HF_TOKEN env var is set.
"""
from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ID   = "kishormorol/researchscope-papers"
_REPO_TYPE = "dataset"

# Fields kept in the raw training split
_RAW_FIELDS = {
    "id", "source", "source_type", "title", "abstract",
    "authors", "year", "published_date", "venue", "conference_rank",
    "paper_url", "pdf_url", "citations", "tags", "topics",
    "paper_score", "paper_type", "difficulty_level",
    "summary", "key_contribution", "why_it_matters",
    "one_line_takeaway", "plain_english_explanation",
}

# Per-column types for the raw split. The HF dataset viewer infers an Arrow
# schema across all rows, so every column MUST hold one consistent type —
# otherwise parquet generation fails ("dataset generation failed" 500).
_LIST_FIELDS  = {"authors", "tags", "topics"}
_INT_FIELDS   = {"year", "citations"}
_FLOAT_FIELDS = {"paper_score"}

# Instruction tasks generated per paper (skipped when field is empty)
_INSTRUCT_TASKS = [
    ("summarize",    "Summarize this research paper in 2-3 sentences.",   "summary"),
    ("contribution", "What is the key contribution of this paper?",        "key_contribution"),
    ("importance",   "Why does this paper matter to the research community?", "why_it_matters"),
    ("plain",        "Explain this paper in plain English for a non-expert.", "plain_english_explanation"),
    ("takeaway",     "Give a one-line takeaway from this paper.",           "one_line_takeaway"),
]


def _input_text(paper: dict) -> str:
    title    = paper.get("title") or ""
    abstract = paper.get("abstract") or ""
    venue    = paper.get("venue") or ""
    year     = paper.get("year") or ""
    return f"Title: {title}\nVenue: {venue} {year}\nAbstract: {abstract}".strip()


def _to_raw(paper: dict) -> dict:
    """Project a paper onto the raw split with coerced, type-stable columns."""
    out: dict[str, Any] = {}
    for k in _RAW_FIELDS:
        if k not in paper:
            continue
        v = paper[k]
        if v in (None, "", [], {}):
            continue
        if k in _LIST_FIELDS:
            v = [str(x) for x in v] if isinstance(v, list) else [str(v)]
        elif k in _INT_FIELDS:
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
        elif k in _FLOAT_FIELDS:
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
        else:
            v = str(v)
        out[k] = v
    return out


def _bucket(row: dict) -> str:
    """Classify a paper into arxiv / conference / journal for per-source splits."""
    st = str(row.get("source_type") or "").lower()
    if st == "journal":
        return "journal"
    if st in ("conference", "workshop"):
        return "conference"
    # preprint / unknown → treat as arXiv (source is arxiv/openalex preprints)
    return "arxiv"


def _to_instruct_rows(paper: dict) -> list[dict]:
    rows = []
    inp  = _input_text(paper)
    for task_id, instruction, field in _INSTRUCT_TASKS:
        output = str(paper.get(field) or "").strip()
        if not output or len(output) < 10:
            continue
        try:
            year = int(paper.get("year") or 0)
        except (TypeError, ValueError):
            year = 0
        rows.append({
            "task":        task_id,
            "instruction": instruction,
            "input":       inp,
            "output":      output,
            "paper_id":    str(paper.get("id", "")),
            "venue":       str(paper.get("venue", "")),
            "year":        year,
            "source_type": str(paper.get("source_type", "")),
        })
    return rows


def _load_all_papers() -> list[dict]:
    root  = Path(__file__).resolve().parents[2] / "site" / "data"
    files = ["papers_db.json", "conferences_db.json", "journals_db.json"]
    seen: dict[str, dict] = {}
    for fname in files:
        path = root / fname
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as fh:
            papers = json.load(fh)
        for p in (papers if isinstance(papers, list) else []):
            pid = p.get("id")
            if pid and pid not in seen:
                seen[pid] = p
    log.info("[hf] loaded %d unique papers from local DB", len(seen))
    return list(seen.values())


def _jsonl_bytes(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    for row in rows:
        buf.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    return buf.getvalue()


def _upload_with_retry(api: Any, *, path_or_fileobj, path_in_repo: str, commit_message: str) -> None:
    """Upload a file to HF Hub with one retry on 429."""
    import time
    for attempt in range(2):
        try:
            api.upload_file(
                path_or_fileobj=path_or_fileobj,
                path_in_repo=path_in_repo,
                repo_id=_REPO_ID,
                repo_type=_REPO_TYPE,
                commit_message=commit_message,
            )
            return
        except Exception as exc:
            if "429" in str(exc) and attempt == 0:
                log.warning("[hf] rate-limited, waiting 60s before retry…")
                time.sleep(60)
                continue
            raise


def push(papers: list[dict] | None = None) -> bool:
    """Push papers to HF Hub. Returns True if pushed, False if skipped."""
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        log.info("[hf] HF_TOKEN not set — skipping HF dataset push.")
        return False

    try:
        from huggingface_hub import HfApi
    except ImportError:
        log.warning("[hf] huggingface_hub not installed — skipping.")
        return False

    if papers is None:
        papers = _load_all_papers()

    if not papers:
        log.warning("[hf] no papers to push.")
        return False

    api = HfApi(token=token)

    # Ensure dataset repo exists
    try:
        api.create_repo(repo_id=_REPO_ID, repo_type=_REPO_TYPE, exist_ok=True, private=False)
    except Exception as exc:
        log.warning("[hf] could not create repo: %s", exc)

    today = datetime.now(timezone.utc).date()

    # ── Raw split — combined `train` + per-source arxiv/conference/journal ──────
    raw_rows = [_to_raw(p) for p in papers if p.get("title")]
    log.info("[hf] pushing %d raw paper records …", len(raw_rows))
    _upload_with_retry(
        api,
        path_or_fileobj=_jsonl_bytes(raw_rows),
        path_in_repo="data/papers.jsonl",
        commit_message=f"update papers.jsonl ({len(raw_rows):,} papers) [{today}]",
    )

    # Per-source splits so users can load just arXiv, conference, or journal
    # papers — `load_dataset(repo, "papers", split="journal")`. The combined
    # `train` split above stays for backward compatibility.
    buckets: dict[str, list[dict]] = {"arxiv": [], "conference": [], "journal": []}
    for row in raw_rows:
        buckets[_bucket(row)].append(row)
    for name, rows in buckets.items():
        log.info("[hf]   %s split → %d papers", name, len(rows))
        _upload_with_retry(
            api,
            path_or_fileobj=_jsonl_bytes(rows),
            path_in_repo=f"data/papers_{name}.jsonl",
            commit_message=f"update papers_{name}.jsonl ({len(rows):,} papers) [{today}]",
        )

    # ── Instruction split ─────────────────────────────────────────────────────
    instruct_rows = []
    for p in papers:
        instruct_rows.extend(_to_instruct_rows(p))
    log.info("[hf] pushing %d instruction rows …", len(instruct_rows))
    _upload_with_retry(
        api,
        path_or_fileobj=_jsonl_bytes(instruct_rows),
        path_in_repo="data/instruct.jsonl",
        commit_message=f"update instruct.jsonl ({len(instruct_rows):,} rows) [{datetime.now(timezone.utc).date()}]",
    )

    # ── Dataset card ──────────────────────────────────────────────────────────
    _push_card(api, len(raw_rows), len(instruct_rows),
               {k: len(v) for k, v in buckets.items()})

    log.info("[hf] push complete → https://huggingface.co/datasets/%s", _REPO_ID)
    return True


def push_sections(jsonl_path: str | Path = "data/sections.jsonl") -> bool:
    """Upload the per-section fine-tuning split (built by build_sections.py)."""
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        log.info("[hf] HF_TOKEN not set — skipping sections push.")
        return False

    path = Path(jsonl_path)
    if not path.exists() or path.stat().st_size == 0:
        log.info("[hf] %s missing/empty — skipping sections push.", path)
        return False

    try:
        from huggingface_hub import HfApi
    except ImportError:
        log.warning("[hf] huggingface_hub not installed — skipping.")
        return False

    api = HfApi(token=token)
    try:
        api.create_repo(repo_id=_REPO_ID, repo_type=_REPO_TYPE, exist_ok=True, private=False)
    except Exception as exc:
        log.warning("[hf] could not create repo: %s", exc)

    n_rows = sum(1 for _ in path.open(encoding="utf-8"))
    today = datetime.now(timezone.utc).date()
    log.info("[hf] pushing %d section rows …", n_rows)
    _upload_with_retry(
        api,
        path_or_fileobj=str(path),
        path_in_repo="data/sections.jsonl",
        commit_message=f"update sections.jsonl ({n_rows:,} rows) [{today}]",
    )
    _ensure_sections_config(api)
    log.info("[hf] sections push complete.")
    return True


def _ensure_sections_config(api: Any) -> None:
    """Register the `sections` config in the dataset card if not already there.

    push_sections() runs standalone (the CI sections job), so the card — which
    is only fully regenerated by the main push() — won't list the sections
    config and `load_dataset(..., "sections")` would fail. This surgically
    inserts the config block, preserving the card's existing stats.
    """
    import urllib.request

    url = f"https://huggingface.co/datasets/{_REPO_ID}/raw/main/README.md"
    try:
        readme = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
    except Exception as exc:
        log.warning("[hf] could not fetch card to register sections config: %s", exc)
        return

    if "config_name: sections" in readme:
        return  # already registered

    anchor = "        path: data/instruct.jsonl\n"
    block = (
        "  - config_name: sections\n"
        "    data_files:\n"
        "      - split: train\n"
        "        path: data/sections.jsonl\n"
    )
    if anchor not in readme:
        log.warning("[hf] card layout unexpected — skipping sections config registration.")
        return

    readme = readme.replace(anchor, anchor + block, 1)
    _upload_with_retry(
        api,
        path_or_fileobj=readme.encode("utf-8"),
        path_in_repo="README.md",
        commit_message="register sections config in dataset card",
    )
    log.info("[hf] registered sections config in dataset card.")


def _push_card(api: Any, n_papers: int, n_instruct: int,
               by_source: dict[str, int] | None = None) -> None:
    by_source = by_source or {}
    n_arxiv = by_source.get("arxiv", 0)
    n_conf  = by_source.get("conference", 0)
    n_journal = by_source.get("journal", 0)
    card = f"""---
license: cc-by-4.0
language:
  - en
task_categories:
  - text-generation
  - summarization
  - feature-extraction
tags:
  - research
  - papers
  - cs
  - machine-learning
  - nlp
  - computer-vision
  - ai
size_categories:
  - 100K<n<1M
configs:
  - config_name: papers
    data_files:
      - split: train
        path: data/papers.jsonl
      - split: arxiv
        path: data/papers_arxiv.jsonl
      - split: conference
        path: data/papers_conference.jsonl
      - split: journal
        path: data/papers_journal.jsonl
  - config_name: instruct
    data_files:
      - split: train
        path: data/instruct.jsonl
  - config_name: sections
    data_files:
      - split: train
        path: data/sections.jsonl
---

# ResearchScope Papers

Open CS research paper dataset maintained by [ResearchScope](https://github.com/kishormorol/ResearchScope).

Updated automatically via GitHub Actions.

## Stats

- **{n_papers:,}** papers (raw metadata) — **{n_arxiv:,}** arXiv · **{n_conf:,}** conference · **{n_journal:,}** journal
- **{n_instruct:,}** instruction-tuning rows
- Sources: arXiv, OpenAlex, ACL Anthology, OpenReview, PMLR, CVF, Semantic Scholar
- Venues: NeurIPS, ICML, ICLR, ACL, EMNLP, CVPR, AAAI, IJCAI, JMLR, TMLR, TACL, TPAMI, NMI and more

## Files

| File | Description |
|------|-------------|
| `data/papers.jsonl` | Raw paper metadata — title, abstract, authors, venue, year, tags, scores (all sources combined) |
| `data/papers_arxiv.jsonl` | arXiv / preprint papers only |
| `data/papers_conference.jsonl` | Conference papers only (NeurIPS, ICML, ICLR, ACL, CVPR, …) |
| `data/papers_journal.jsonl` | Journal papers only (JMLR, TPAMI, NMI, TACL, …) |
| `data/instruct.jsonl` | Instruction-tuning pairs — summarize, key contribution, why it matters, plain English |
| `data/sections.jsonl` | Per-section fine-tuning rows for A* papers — real body text of `abstract`, `introduction`, `related_work`, `method`, `experiments`, `results`, `conclusion`. Filter by the `section` field to train a per-section writing agent. |

## Usage

```python
from datasets import load_dataset

# All papers (combined)
papers = load_dataset("kishormorol/researchscope-papers", "papers", split="train")

# Just one source — arXiv, conference, or journal papers
arxiv      = load_dataset("kishormorol/researchscope-papers", "papers", split="arxiv")
conference = load_dataset("kishormorol/researchscope-papers", "papers", split="conference")
journal    = load_dataset("kishormorol/researchscope-papers", "papers", split="journal")

# Instruction tuning
instruct = load_dataset("kishormorol/researchscope-papers", "instruct", split="train")

# Per-section fine-tuning (A* papers) — e.g. train an Introduction-writing agent
sections = load_dataset("kishormorol/researchscope-papers", "sections", split="train")
intros = sections.filter(lambda r: r["section"] == "introduction")
```

## License

Paper metadata is aggregated from open sources. Text content follows the original licenses of each source (arXiv CC0, ACL CC BY, etc.).
Dataset schema: CC BY 4.0.
"""
    _upload_with_retry(
        api,
        path_or_fileobj=card.encode("utf-8"),
        path_in_repo="README.md",
        commit_message="update dataset card",
    )
