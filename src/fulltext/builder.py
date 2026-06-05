"""
Build the per-section fine-tuning dataset from A* conference papers.

Pipeline per paper:
    record → resolve_pdf_url → download → GROBID TEI → segment into 7 buckets
           → emit one (input → output) training row per section found.

Input shape "B" (context-conditioned): the agent is given the paper's title,
venue, year and abstract, PLUS the real text of every preceding section, then
learns to produce the target section. This trains each agent to write in
coherent continuation of what came before (e.g. Method sees Introduction +
Related Work). Filter rows by `section` to get a clean per-agent corpus.

Quality gating uses signals already on the record: conference_rank (always A*
here), paper_score and citations.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path
from typing import Iterable, Iterator

from src.fulltext import CANONICAL_SECTIONS
from src.fulltext.grobid_client import is_alive, process_fulltext
from src.fulltext.pdf_resolver import resolve_pdf_url
from src.fulltext.segmenter import segment

log = logging.getLogger(__name__)

_SECTION_PROMPT = {
    "abstract":     "Write the Abstract for this paper.",
    "introduction": "Write the Introduction section for this paper.",
    "related_work": "Write the Related Work section for this paper.",
    "method":       "Write the Method section for this paper.",
    "experiments":  "Write the Experiments section for this paper.",
    "results":      "Write the Results section for this paper.",
    "conclusion":   "Write the Conclusion section for this paper.",
}

# Human-readable headings used to label preceding sections in the context.
_SECTION_TITLE = {
    "introduction": "Introduction",
    "related_work": "Related Work",
    "method":       "Method",
    "experiments":  "Experiments",
    "results":      "Results",
    "conclusion":   "Conclusion",
}

# Drop sections shorter than this — too small to teach a pattern.
_MIN_SECTION_CHARS = 200
# Per-section cap when used as *preceding context* (keeps input rows bounded).
_CONTEXT_CHARS_PER_SECTION = 2500
# Skip PDFs larger than this. Image-heavy PDFs (e.g. some CVF papers) push a
# memory-constrained GROBID into OOM; with thousands of candidates available we
# can afford to skip the few giant ones. Override via build_dataset(max_pdf_mb=).
_MAX_PDF_BYTES = 5 * 1024 * 1024
_DOWNLOAD_TIMEOUT = 60
_UA = "ResearchScope/1.0 (+https://github.com/kishormorol/ResearchScope)"


def select_papers(
    db_path: str | Path,
    *,
    min_score: float = 0.0,
    min_citations: int = 0,
    limit: int | None = None,
) -> list[dict]:
    """Load and rank A* papers, best-scored first, applying quality gates."""
    papers = json.loads(Path(db_path).read_text(encoding="utf-8"))
    papers = [
        p for p in papers
        if p.get("conference_rank") == "A*"
        and float(p.get("paper_score") or 0) >= min_score
        and int(p.get("citations") or 0) >= min_citations
        and resolve_pdf_url(p) is not None
    ]
    papers.sort(key=lambda p: float(p.get("paper_score") or 0), reverse=True)
    return papers[:limit] if limit else papers


def _pdf_size(url: str) -> int | None:
    """HEAD the PDF to read Content-Length without downloading the body.

    Returns the size in bytes, or None if it can't be determined (caller then
    falls back to downloading and enforcing the cap post-hoc).
    """
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:
        return None


def _download_pdf(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as r:
            return r.read()
    except Exception as exc:
        log.warning("[fulltext] download failed %s: %s", url, exc)
        return None


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " […]"


def _make_input(paper: dict, section: str, preceding: str) -> str:
    title = paper.get("title") or ""
    venue = paper.get("venue") or ""
    year  = paper.get("year") or ""
    abstract = paper.get("abstract") or ""
    parts = [
        f"Title: {title}",
        f"Venue: {venue} {year}",
        f"Abstract: {abstract}",
    ]
    if preceding:
        parts.append("\nThe paper so far:\n\n" + preceding)
    parts.append("\n" + _SECTION_PROMPT[section])
    return "\n".join(parts).strip()


def build_rows(paper: dict, max_pdf_bytes: int = _MAX_PDF_BYTES) -> list[dict]:
    """Resolve, fetch, parse and segment one paper into section rows."""
    url = resolve_pdf_url(paper)
    if not url:
        return []
    # Cheap HEAD pre-check: skip giant PDFs before downloading the body.
    head_size = _pdf_size(url)
    if head_size is not None and head_size > max_pdf_bytes:
        log.info("[fulltext] skip oversized PDF (%d bytes, HEAD): %s",
                 head_size, paper.get("id"))
        return []
    pdf = _download_pdf(url)
    if not pdf:
        return []
    if len(pdf) > max_pdf_bytes:
        log.info("[fulltext] skip oversized PDF (%d bytes): %s",
                 len(pdf), paper.get("id"))
        return []
    tei = process_fulltext(pdf)
    if not tei:
        return []
    sections = segment(tei)

    rows: list[dict] = []
    context_blocks: list[str] = []   # preceding sections, in canonical order
    for section in CANONICAL_SECTIONS:
        text = sections.get(section, "")
        # Emit a training row when the section is long enough to teach a pattern.
        if len(text) >= _MIN_SECTION_CHARS:
            preceding = "\n\n".join(context_blocks)
            rows.append({
                "section":     section,
                "paper_id":    str(paper.get("id", "")),
                "venue":       str(paper.get("venue", "")),
                "year":        int(paper.get("year") or 0),
                "tags":        [str(t) for t in (paper.get("tags") or [])],
                "paper_score": float(paper.get("paper_score") or 0),
                "citations":   int(paper.get("citations") or 0),
                "input":       _make_input(paper, section, preceding),
                "output":      text,
            })
        # Add this section to the running context for later sections. Abstract
        # is skipped — it already appears in the metadata header of every input.
        if text and section != "abstract":
            block = f"## {_SECTION_TITLE[section]}\n{_truncate(text, _CONTEXT_CHARS_PER_SECTION)}"
            context_blocks.append(block)
    return rows


def build_dataset(
    papers: Iterable[dict],
    out_path: str | Path,
    *,
    grobid_required: bool = True,
    delay: float = 0.0,
    max_pdf_mb: float = 5.0,
) -> dict:
    """Stream section rows for all papers to a JSONL file. Returns stats."""
    if grobid_required and not is_alive():
        raise RuntimeError(
            "GROBID is not reachable. Start it with:\n"
            "  docker run --rm -p 8070:8070 lfoppiano/grobid:0.8.0\n"
            "or set GROBID_URL to a running server."
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    max_pdf_bytes = int(max_pdf_mb * 1024 * 1024)
    stats = {"papers": 0, "ok": 0, "skipped": 0, "rows": 0,
             "by_section": {s: 0 for s in CANONICAL_SECTIONS}}

    with out_path.open("w", encoding="utf-8") as fh:
        for paper in papers:
            stats["papers"] += 1
            rows = build_rows(paper, max_pdf_bytes=max_pdf_bytes)
            if not rows:
                stats["skipped"] += 1
            else:
                stats["ok"] += 1
                for row in rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stats["rows"] += 1
                    stats["by_section"][row["section"]] += 1
                fh.flush()
            if stats["papers"] % 25 == 0:
                log.info("[fulltext] %(papers)d papers · %(rows)d rows · "
                         "%(skipped)d skipped", stats)
            if delay:
                time.sleep(delay)

    return stats
