"""
Minimal GROBID client.

Talks to a running GROBID server (default http://localhost:8070, overridable
with the GROBID_URL env var). Only the full-text endpoint is needed: it returns
TEI XML with the body segmented into <div><head>…</head><p>…</p></div> blocks
that the segmenter maps onto canonical sections.

Run a server locally with:
    docker run --rm -p 8070:8070 lfoppiano/grobid:0.8.0
"""
from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_DEFAULT_URL = os.environ.get("GROBID_URL", "http://localhost:8070").rstrip("/")
_BOUNDARY = "----ResearchScopeGrobidBoundary"


def is_alive(base_url: str = _DEFAULT_URL, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/isalive", timeout=timeout) as r:
            return r.read().strip() in (b"true", b"True", b"1")
    except Exception:
        return False


def process_fulltext(
    pdf_bytes: bytes,
    base_url: str = _DEFAULT_URL,
    timeout: float = 180.0,
    retries: int = 2,
) -> str | None:
    """Send PDF bytes to GROBID; return TEI XML string or None on failure."""
    body = _multipart(pdf_bytes)
    url = f"{base_url}/api/processFulltextDocument"
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={_BOUNDARY}")
        req.add_header("Accept", "application/xml")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            # 503 = GROBID busy (queue full); back off and retry.
            if e.code == 503 and attempt < retries:
                time.sleep(2 + attempt * 3)
                continue
            log.warning("[grobid] HTTP %s on attempt %d", e.code, attempt)
            return None
        except Exception as exc:
            if attempt < retries:
                time.sleep(2)
                continue
            log.warning("[grobid] failed: %s", exc)
            return None
    return None


def _multipart(pdf_bytes: bytes) -> bytes:
    """Build a multipart/form-data body with the PDF + GROBID options."""
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.append(
            f'--{_BOUNDARY}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )

    parts.append(
        f'--{_BOUNDARY}\r\nContent-Disposition: form-data; name="input"; '
        f'filename="paper.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
    )
    parts.append(pdf_bytes)
    parts.append(b"\r\n")
    # Keep raw section structure; we don't need coordinates or consolidation.
    field("segmentSentences", "0")
    field("consolidateHeader", "0")
    field("consolidateCitations", "0")
    parts.append(f"--{_BOUNDARY}--\r\n".encode())
    return b"".join(parts)
