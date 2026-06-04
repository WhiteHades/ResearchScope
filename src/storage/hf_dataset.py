"""
Hugging Face Hub dataset pusher.

Exports all ResearchScope papers to JSONL and pushes to
kishormorol/researchscope-papers on the HF Hub.

Two splits are uploaded:
  papers.jsonl         — raw metadata (all fields, good for pretraining)
  instruct.jsonl       — instruction-tuning format (summary, key contribution,
                         why_it_matters tasks)

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

    # ── Raw split ─────────────────────────────────────────────────────────────
    raw_rows = [_to_raw(p) for p in papers if p.get("title")]
    log.info("[hf] pushing %d raw paper records …", len(raw_rows))
    _upload_with_retry(
        api,
        path_or_fileobj=_jsonl_bytes(raw_rows),
        path_in_repo="data/papers.jsonl",
        commit_message=f"update papers.jsonl ({len(raw_rows):,} papers) [{today}]",
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
    _push_card(api, len(raw_rows), len(instruct_rows))

    log.info("[hf] push complete → https://huggingface.co/datasets/%s", _REPO_ID)
    return True


def _push_card(api: Any, n_papers: int, n_instruct: int) -> None:
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
  - config_name: instruct
    data_files:
      - split: train
        path: data/instruct.jsonl
---

# ResearchScope Papers

Open CS research paper dataset maintained by [ResearchScope](https://github.com/kishormorol/ResearchScope).

Updated automatically via GitHub Actions.

## Stats

- **{n_papers:,}** papers (raw metadata)
- **{n_instruct:,}** instruction-tuning rows
- Sources: arXiv, OpenAlex, ACL Anthology, OpenReview, PMLR, CVF, Semantic Scholar
- Venues: NeurIPS, ICML, ICLR, ACL, EMNLP, CVPR, AAAI, IJCAI, JMLR, TMLR, TACL, TPAMI, NMI and more

## Files

| File | Description |
|------|-------------|
| `data/papers.jsonl` | Raw paper metadata — title, abstract, authors, venue, year, tags, scores |
| `data/instruct.jsonl` | Instruction-tuning pairs — summarize, key contribution, why it matters, plain English |

## Usage

```python
from datasets import load_dataset

# Raw papers
papers = load_dataset("kishormorol/researchscope-papers", "papers", split="train")

# Instruction tuning
instruct = load_dataset("kishormorol/researchscope-papers", "instruct", split="train")
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
