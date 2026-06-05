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


def wait_until_alive(base_url: str = _DEFAULT_URL, timeout: float = 90.0) -> bool:
    """Block until GROBID answers /isalive (e.g. after an OOM auto-restart)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_alive(base_url):
            return True
        time.sleep(3)
    return False


def process_fulltext(
    pdf_bytes: bytes,
    base_url: str = _DEFAULT_URL,
    timeout: float = 180.0,
    retries: int = 2,
) -> str | None:
    """Send PDF bytes to GROBID; return TEI XML string or None on failure.

    On a refused connection (GROBID crashed/OOM and is being auto-restarted by
    Docker) we wait for it to come back and retry, rather than silently skipping
    a long run of papers.
    """
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
        except urllib.error.URLError as exc:
            # Connection refused → container is down/restarting. Wait for it.
            if isinstance(exc.reason, ConnectionRefusedError) and attempt < retries:
                log.warning("[grobid] connection refused — waiting for restart…")
                wait_until_alive(base_url)
                continue
            if attempt < retries:
                time.sleep(2)
                continue
            log.warning("[grobid] failed: %s", exc)
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
