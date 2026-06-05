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
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fulltext.builder import build_dataset, select_papers

logging.basicConfig(level=logging.INFO, format="%(message)s")


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
    args = ap.parse_args()

    papers = select_papers(args.db, min_score=args.min_score,
                           min_citations=args.min_citations, limit=args.limit)
    logging.info("Selected %d A* papers (score>=%.1f, citations>=%d)",
                 len(papers), args.min_score, args.min_citations)
    if not papers:
        logging.error("No papers matched. Is the DB present?")
        return 1

    stats = build_dataset(papers, args.out, delay=args.delay,
                          max_pdf_mb=args.max_pdf_mb)

    logging.info("\n=== DONE ===")
    logging.info("papers processed : %d", stats["papers"])
    logging.info("papers with rows : %d", stats["ok"])
    logging.info("papers skipped   : %d", stats["skipped"])
    logging.info("total rows       : %d", stats["rows"])
    logging.info("rows by section  :")
    for sec, n in stats["by_section"].items():
        logging.info("  %-13s %d", sec, n)
    logging.info("→ %s", args.out)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
