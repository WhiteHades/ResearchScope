"""
Segment GROBID TEI XML into ResearchScope's seven canonical sections.

GROBID emits the body as a sequence of <div> blocks, each with an optional
<head> (the section heading) and one or more <p> paragraphs. We map each
heading onto one canonical bucket via keyword rules, then concatenate the
paragraph text. Numbered prefixes ("1.", "3.2") and trailing punctuation are
stripped before matching.

Sections we cannot confidently classify are dropped rather than guessed — for
fine-tuning data, a clean miss is better than a mislabelled example.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from src.fulltext import CANONICAL_SECTIONS

_TEI_NS = "http://www.tei-c.org/ns/1.0"
_NS = {"tei": _TEI_NS}

# Heading keyword → canonical section. Order matters: the first bucket whose
# any keyword appears in the (lowercased) heading wins. More specific buckets
# (related_work, experiments) are checked before generic ones (method).
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("related_work", ("related work", "related works", "prior work", "background",
                       "literature review", "preliminaries")),
    ("experiments",  ("experiment", "experimental setup", "experimental settings",
                      "implementation details", "datasets", "setup", "training details",
                      "evaluation protocol", "benchmark")),
    ("results",      ("results", "evaluation", "analysis", "ablation", "discussion",
                      "findings", "comparison", "main results")),
    ("conclusion",   ("conclusion", "conclusions", "concluding remarks", "future work",
                      "limitations", "broader impact")),
    ("method",       ("method", "methodology", "approach", "model", "architecture",
                      "proposed", "framework", "our ", "algorithm", "design",
                      "formulation", "problem formulation")),
    ("introduction", ("introduction", "intro", "motivation", "overview")),
]


def _norm_head(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"^[0-9]+(\.[0-9]+)*\.?\s*", "", t)      # strip "3.", "3.2 "
    t = re.sub(r"^[ivxlc]+\.\s*", "", t)                # strip roman "IV."
    return t.strip(" .:-")


def _classify(head: str) -> str | None:
    h = _norm_head(head)
    if not h:
        return None
    for bucket, keywords in _RULES:
        if any(k in h for k in keywords):
            return bucket
    return None


def _text_of(elem: ET.Element) -> str:
    """All descendant text of a <p>/<div>, whitespace-normalised."""
    return re.sub(r"\s+", " ", "".join(elem.itertext())).strip()


def segment(tei_xml: str) -> dict[str, str]:
    """Return {canonical_section: text} for the sections found in the TEI."""
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return {}

    buckets: dict[str, list[str]] = {s: [] for s in CANONICAL_SECTIONS}

    # Abstract lives in the header, not the body.
    for abs in root.iterfind(f".//tei:abstract", _NS):
        txt = _text_of(abs)
        if txt:
            buckets["abstract"].append(txt)

    body = root.find(f".//tei:text/tei:body", _NS)
    if body is not None:
        for div in body.iterfind("tei:div", _NS):
            head_el = div.find("tei:head", _NS)
            if head_el is None:
                continue
            bucket = _classify("".join(head_el.itertext()))
            if bucket is None:
                continue
            paras = [_text_of(p) for p in div.iterfind("tei:p", _NS)]
            text = " ".join(t for t in paras if t)
            if text:
                buckets[bucket].append(text)

    return {k: "\n\n".join(v) for k, v in buckets.items() if v}
