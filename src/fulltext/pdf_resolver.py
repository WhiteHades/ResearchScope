"""
Resolve an A* paper record to a downloadable PDF URL.

The conferences_db.json records come from four sources, each with its own
PDF location convention:

  openreview     id="openreview:<forum>"   → https://openreview.net/pdf?id=<forum>
  acl_anthology  id="acl:<paper_id>"       → https://aclanthology.org/<paper_id>.pdf
  cvf            paper_url=.../html/X.html → .../papers/X.pdf
  semantic_scholar                         → no reliable open PDF (DOI only)

`pdf_url` stored in the DB is unreliable (ACL records store a malformed
".../.pdf"; OpenReview/CVF store an empty string), so we derive the URL from
the stable id / paper_url instead.
"""
from __future__ import annotations

import re


def resolve_pdf_url(paper: dict) -> str | None:
    """Return a direct PDF URL for a paper, or None if unavailable."""
    source = (paper.get("source") or "").strip()
    pid    = str(paper.get("id") or "")
    purl   = str(paper.get("paper_url") or "")

    if source == "openreview":
        forum = pid.split(":", 1)[1] if ":" in pid else _qs(purl, "id")
        return f"https://openreview.net/pdf?id={forum}" if forum else None

    if source == "acl_anthology":
        # id="acl:2025.acl-long.533" → https://aclanthology.org/2025.acl-long.533.pdf
        acl_id = pid.split(":", 1)[1] if ":" in pid else _last_path(purl)
        return f"https://aclanthology.org/{acl_id}.pdf" if acl_id else None

    if source == "cvf":
        # .../content/CVPR2024/html/X_paper.html → .../content/CVPR2024/papers/X_paper.pdf
        if purl.endswith(".html") and "/html/" in purl:
            return purl.replace("/html/", "/papers/")[:-5] + ".pdf"
        return None

    # semantic_scholar: only a DOI; no guaranteed open PDF. Skip for now.
    return None


def _qs(url: str, key: str) -> str:
    m = re.search(rf"[?&]{re.escape(key)}=([^&]+)", url)
    return m.group(1) if m else ""


def _last_path(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]
