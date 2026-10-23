"""
Resolve an A* paper record to a downloadable PDF URL.

The conferences_db.json records come from these sources, each with its own
PDF location convention:

  openreview     id="openreview:<forum>"   → https://openreview.net/pdf?id=<forum>
  acl_anthology  id="acl:<paper_id>"       → https://aclanthology.org/<paper_id>.pdf
  cvf            paper_url=.../html/X.html → .../papers/X.pdf
  semantic_scholar                         → no reliable open PDF (DOI only)

Use a supplied PDF URL on the source's official host. Derive a URL only when
the source has a stable ID or a documented URL pattern.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit


_PDF_HOSTS = {
    "openreview": "openreview.net",
    "acl_anthology": "aclanthology.org",
    "cvf": "openaccess.thecvf.com",
    "pmlr": "proceedings.mlr.press",
    "arxiv": "arxiv.org",
}


def resolve_pdf_url(paper: dict) -> str | None:
    """Return a direct PDF URL for a paper, or None if unavailable."""
    source = (paper.get("source") or "").strip()
    pid    = str(paper.get("id") or "")
    purl   = str(paper.get("paper_url") or "")
    pdf_url = str(paper.get("pdf_url") or "")

    if _safe_pdf_url(pdf_url, source):
        return pdf_url

    if source == "openreview":
        forum = pid.split(":", 1)[1] if ":" in pid else _qs(purl, "id")
        return f"https://openreview.net/pdf?id={forum}" if forum else None

    if source == "acl_anthology":
        # id="acl:2025.acl-long.533" → https://aclanthology.org/2025.acl-long.533.pdf
        acl_id = pid.split(":", 1)[1] if ":" in pid else _last_path(purl)
        return f"https://aclanthology.org/{acl_id}.pdf" if acl_id else None

    if source == "cvf":
        # .../content/CVPR2024/html/X_paper.html → .../content/CVPR2024/papers/X_paper.pdf
        if _safe_pdf_url(purl, source, landing=True) and purl.endswith(".html") and "/html/" in purl:
            return purl.replace("/html/", "/papers/")[:-5] + ".pdf"
        return None

    # semantic_scholar: only a DOI; no guaranteed open PDF. Skip for now.
    return None


def _qs(url: str, key: str) -> str:
    m = re.search(rf"[?&]{re.escape(key)}=([^&]+)", url)
    return m.group(1) if m else ""


def _last_path(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _safe_pdf_url(url: str, source: str, *, landing: bool = False) -> bool:
    host = _PDF_HOSTS.get(source)
    if not host:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    hostname = (parts.hostname or "").lower().rstrip(".")
    if (parts.scheme != "https" or parts.username is not None or parts.password is not None
            or not (hostname == host or hostname.endswith("." + host))):
        return False
    if landing:
        return True
    path = parts.path.lower()
    arxiv_pdf_path = (
        source == "arxiv"
        and path.startswith("/pdf/")
        and len(path) > len("/pdf/")
    )
    return (
        path.endswith(".pdf") or path == "/pdf" or arxiv_pdf_path
    ) and not path.endswith("/.pdf")
