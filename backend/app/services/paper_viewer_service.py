from __future__ import annotations

from urllib.parse import quote, urlparse

import httpx

from app.models import Paper

_MAX_OPENALEX_BYTES = 2_000_000
_EMBEDDABLE_PDF_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "semanticscholar.org",
    "pdfs.semanticscholar.org",
}


def _embeddable_pdf_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    trusted = any(
        host == allowed or host.endswith(f".{allowed}")
        for allowed in _EMBEDDABLE_PDF_HOSTS
    )
    return value if parsed.scheme == "https" and trusted else None


async def resolve_paper_viewer_url(
    paper: Paper,
    *,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Prefer a browser-embeddable PDF while retaining canonical metadata."""
    direct = _embeddable_pdf_url(paper.pdf_url)
    if direct:
        return direct

    paper_id = str(paper.id or "")
    if not paper_id.startswith("openalex:"):
        return None

    work_id = paper_id.split(":", 1)[1]
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        response = await client.get(
            f"https://api.openalex.org/works/{quote(work_id, safe='')}"
        )
    except httpx.HTTPError:
        return None
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code != 200 or len(response.content) > _MAX_OPENALEX_BYTES:
        return None
    try:
        locations = response.json().get("locations", [])
    except ValueError:
        return None
    for location in locations:
        resolved = _embeddable_pdf_url(location.get("pdf_url"))
        if resolved:
            return resolved
    return None
