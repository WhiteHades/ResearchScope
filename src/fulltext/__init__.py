"""
Full-text section extraction for ResearchScope.

A* conference papers are PDF-based (ACL Anthology, OpenReview, CVF). This
package resolves each paper to a downloadable PDF, runs it through a GROBID
server to obtain structured TEI XML, and segments the body into seven
canonical sections used by downstream paper-writing agents:

    abstract | introduction | related_work | method | experiments |
    results | conclusion

The output is a per-(paper × section) JSONL dataset suitable for fine-tuning.
"""
from __future__ import annotations

CANONICAL_SECTIONS = [
    "abstract",
    "introduction",
    "related_work",
    "method",
    "experiments",
    "results",
    "conclusion",
]
