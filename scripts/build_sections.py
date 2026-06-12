#!/usr/bin/env python3
"""
Build the per-section fine-tuning dataset from A* conference papers.

Requires a running GROBID server (for PDF → structured TEI):
    docker run --rm -p 8070:8070 lfoppiano/grobid:0.8.0

Examples:
    # Smoke test: 20 top-scored A* papers
    python scripts/build_sections.py --limit 20

    # Real backfill: top 5,000 A* papers with at least 5 citations
    python scripts/build_sections.py --min-citations 5 --limit 5000

Output: data/sections.jsonl  (one row per paper × section)

By default the build is incremental: it seeds the output with the sections
split currently published on the HF Hub and only processes papers not yet
covered, so the dataset grows monotonically — a run hit by PDF-host rate
limits (e.g. OpenReview 429s) adds fewer new papers instead of shrinking
the published file. Use --fresh to rebuild from scratch.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fulltext.builder import build_dataset, select_papers
from src.storage.hf_dataset import _REPO_ID

logging.basicConfig(level=logging.INFO, format="%(message)s")

_HUB_SECTIONS_URL = (
    f"https://huggingface.co/datasets/{_REPO_ID}/resolve/main/data/sections.jsonl"
)


def _seed_from_hub(out_path: Path) -> tuple[set[str], int]:
    """Seed the output file with the published sections split.

    Returns (paper_ids already covered, row count). On any failure returns
    an empty seed and the build falls back to a from-scratch rebuild.
    """
    try:
        req = urllib.request.Request(
            _HUB_SECTIONS_URL,
            headers={"User-Agent": "ResearchScope/1.0 (+https://github.com/kishormorol/ResearchScope)"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as exc:
        logging.warning("Could not fetch published sections split (%s) — "
                        "building from scratch.", exc)
        return set(), 0

    ids: set[str] = set()
    n_rows = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as fh:
        for line in data.splitlines(keepends=True):
            try:
                pid = json.loads(line).get("paper_id")
            except (json.JSONDecodeError, AttributeError):
                continue
            if pid:
                ids.add(str(pid))
                fh.write(line if line.endswith(b"\n") else line + b"\n")
                n_rows += 1
    logging.info("Seeded %d existing rows (%d papers) from %s",
                 n_rows, len(ids), _HUB_SECTIONS_URL)
    return ids, n_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="site/data/conferences_db.json",
                    help="A* papers DB (default: site/data/conferences_db.json)")
    ap.add_argument("--out", default="data/sections.jsonl",
                    help="Output JSONL path (default: data/sections.jsonl)")
    ap.add_argument("--limit", type=int, default=None, help="Max papers to process")
    ap.add_argument("--min-score", type=float, default=0.0, help="Min paper_score")
    ap.add_argument("--min-citations", type=int, default=0, help="Min citations")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="Seconds to sleep between papers (politeness)")
    ap.add_argument("--max-pdf-mb", type=float, default=5.0,
                    help="Skip PDFs larger than this (avoids OOM on low-RAM GROBID)")
    ap.add_argument("--fresh", action="store_true",
                    help="Rebuild from scratch instead of merging onto the published split")
    args = ap.parse_args()

    out = Path(args.out)
    existing_ids: set[str] = set()
    existing_rows = 0
    if not args.fresh:
        existing_ids, existing_rows = _seed_from_hub(out)

    papers = select_papers(args.db, min_score=args.min_score,
                           min_citations=args.min_citations, limit=args.limit,
                           exclude_ids=existing_ids)
    logging.info("Selected %d new A* papers (score>=%.1f, citations>=%d, "
                 "%d already covered)",
                 len(papers), args.min_score, args.min_citations,
                 len(existing_ids))
    if not papers and not existing_rows:
        logging.error("No papers matched. Is the DB present?")
        return 1

    stats = build_dataset(papers, out, delay=args.delay,
                          max_pdf_mb=args.max_pdf_mb,
                          append=bool(existing_rows))

    stats["pre_existing_rows"] = existing_rows
    stats["total_rows_in_file"] = existing_rows + stats["rows"]

    logging.info("\n=== DONE ===")
    logging.info("papers processed : %d", stats["papers"])
    logging.info("papers with rows : %d", stats["ok"])
    logging.info("papers skipped   : %d", stats["skipped"])
    logging.info("new rows         : %d", stats["rows"])
    logging.info("rows in file     : %d (incl. %d pre-existing)",
                 stats["total_rows_in_file"], existing_rows)
    logging.info("rows by section  :")
    for sec, n in stats["by_section"].items():
        logging.info("  %-13s %d", sec, n)
    logging.info("→ %s", args.out)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
