from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from pypdf import PdfReader
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_session_factory
from app.models import Paper, PaperChunk, PaperDocument

EXTRACTOR_VERSION = "pypdf-v1"
_PREPARE_SEMAPHORE = asyncio.Semaphore(2)
_STALE_AFTER = timedelta(minutes=15)

_DEFAULT_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "semanticscholar.org",
    "pdfs.semanticscholar.org",
    "nature.com",
    "pmc.ncbi.nlm.nih.gov",
    "europepmc.org",
}


@dataclass(frozen=True)
class ExtractedChunk:
    chunk_index: int
    page_start: int
    page_end: int
    content: str


class DocumentPreparationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _allowed_hosts() -> set[str]:
    extra = {
        item.strip().lower()
        for item in os.environ.get("CHAT_PDF_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    return _DEFAULT_HOSTS | extra


def _host_allowed(host: str, allowed: set[str] | None = None) -> bool:
    host = host.lower().rstrip(".")
    return any(
        host == item or host.endswith(f".{item}")
        for item in (allowed or _allowed_hosts())
    )


def resolve_pdf_url(paper: Paper) -> str | None:
    if paper.pdf_url:
        return paper.pdf_url.strip()

    pid = str(paper.id or "")
    purl = str(paper.paper_url or "")
    source = str(paper.source or "").lower()

    if source == "arxiv" or pid.startswith("arxiv:"):
        arxiv_id = pid.split(":", 1)[-1].split("v", 1)[0]
        return f"https://arxiv.org/pdf/{arxiv_id}"
    if source == "openreview" or pid.startswith("openreview:"):
        forum = pid.split(":", 1)[-1] if ":" in pid else ""
        if not forum and purl:
            forum = parse_qs(urlparse(purl).query).get("id", [""])[0]
        return f"https://openreview.net/pdf?id={forum}" if forum else None
    if source == "acl_anthology" or pid.startswith("acl:"):
        acl_id = (
            pid.split(":", 1)[-1] if ":" in pid else purl.rstrip("/").rsplit("/", 1)[-1]
        )
        return f"https://aclanthology.org/{acl_id}.pdf" if acl_id else None
    if source == "cvf" and purl.endswith(".html") and "/html/" in purl:
        return purl.replace("/html/", "/papers/")[:-5] + ".pdf"
    return None


def safe_pdf_url(paper: Paper) -> str | None:
    url = resolve_pdf_url(paper)
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not _host_allowed(parsed.hostname or ""):
        return None
    return url


async def _validate_public_host(host: str) -> None:
    if not host or not _host_allowed(host):
        raise DocumentPreparationError("pdf_host_not_allowed")
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise DocumentPreparationError("pdf_host_unreachable") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise DocumentPreparationError("pdf_host_not_public")


async def download_pdf(url: str) -> bytes:
    max_bytes = int(float(os.environ.get("CHAT_MAX_PDF_MB", "15")) * 1024 * 1024)
    timeout = httpx.Timeout(
        float(os.environ.get("CHAT_PDF_TIMEOUT_SECONDS", "60")), connect=10
    )
    current = url

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(4):
            parsed = urlparse(current)
            if parsed.scheme != "https":
                raise DocumentPreparationError("pdf_https_required")
            await _validate_public_host(parsed.hostname or "")

            async with client.stream(
                "GET", current, headers={"User-Agent": "ResearchScope/1.0"}
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise DocumentPreparationError("pdf_redirect_invalid")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise DocumentPreparationError("pdf_download_failed")
                declared = int(response.headers.get("content-length") or 0)
                if declared > max_bytes:
                    raise DocumentPreparationError("pdf_too_large")
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > max_bytes:
                        raise DocumentPreparationError("pdf_too_large")
                result = bytes(data)
                if not result.startswith(b"%PDF-"):
                    raise DocumentPreparationError("pdf_invalid")
                return result
    raise DocumentPreparationError("pdf_redirect_limit")


def chunk_pages(
    pages: list[str], *, target_chars: int = 3500, overlap_chars: int = 400
) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    index = 0
    for page_number, raw in enumerate(pages, start=1):
        text = "\n\n".join(
            " ".join(block.split()) for block in raw.split("\n\n") if block.strip()
        ).strip()
        if not text:
            continue
        start = 0
        while start < len(text):
            end = min(len(text), start + target_chars)
            if end < len(text):
                boundary = max(
                    text.rfind("\n\n", start, end), text.rfind(". ", start, end)
                )
                if boundary > start + target_chars // 2:
                    end = boundary + (2 if text[boundary : boundary + 2] == ". " else 0)
            content = text[start:end].strip()
            if content:
                chunks.append(ExtractedChunk(index, page_number, page_number, content))
                index += 1
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_chars)
    return chunks


def extract_pdf(pdf_bytes: bytes) -> tuple[int, list[ExtractedChunk]]:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise DocumentPreparationError("pdf_extract_failed") from exc
    chunks = chunk_pages(pages)
    if not chunks or sum(len(chunk.content) for chunk in chunks) < 1000:
        raise DocumentPreparationError("pdf_text_unavailable")
    return len(pages), chunks


async def queue_document(paper_id: str) -> str:
    async with get_session_factory()() as db:
        paper = await db.get(Paper, paper_id)
        if not paper:
            raise DocumentPreparationError("paper_not_found")
        await db.execute(
            pg_insert(PaperDocument)
            .values(paper_id=paper_id, status="queued")
            .on_conflict_do_nothing(index_elements=[PaperDocument.paper_id])
        )
        await db.commit()
        document = (
            await db.execute(
                select(PaperDocument)
                .where(PaperDocument.paper_id == paper_id)
                .with_for_update()
            )
        ).scalar_one()
        now = datetime.now(timezone.utc)
        if document.status == "ready":
            document.last_accessed_at = now
            await db.commit()
            return "ready"
        if document.status == "preparing" and document.updated_at:
            updated = document.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if now - updated < _STALE_AFTER:
                await db.rollback()
                return "preparing"
        document.status = "preparing"
        document.error_code = None
        await db.commit()
        return "queued"


async def prepare_document(paper_id: str) -> None:
    async with _PREPARE_SEMAPHORE:
        async with get_session_factory()() as db:
            paper = await db.get(Paper, paper_id)
            document = await db.get(PaperDocument, paper_id)
            if not paper or not document:
                return
            if document.status == "ready":
                return
            document.status = "preparing"
            document.error_code = None
            await db.commit()

            try:
                url = resolve_pdf_url(paper)
                if not url:
                    raise DocumentPreparationError("pdf_url_missing")
                pdf_bytes = await download_pdf(url)
                page_count, chunks = await asyncio.to_thread(extract_pdf, pdf_bytes)
                digest = hashlib.sha256(pdf_bytes).hexdigest()

                await db.execute(
                    delete(PaperChunk).where(PaperChunk.paper_id == paper_id)
                )
                for chunk in chunks:
                    db.add(
                        PaperChunk(
                            paper_id=paper_id,
                            chunk_index=chunk.chunk_index,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            content=chunk.content,
                            char_count=len(chunk.content),
                        )
                    )
                await db.flush()
                await db.execute(
                    update(PaperChunk)
                    .where(PaperChunk.paper_id == paper_id)
                    .values(
                        search_vector=func.to_tsvector("english", PaperChunk.content)
                    )
                )
                document.source_url = url
                document.content_hash = digest
                document.page_count = page_count
                document.chunk_count = len(chunks)
                document.extractor_version = EXTRACTOR_VERSION
                document.status = "ready"
                document.error_code = None
                document.prepared_at = datetime.now(timezone.utc)
                document.last_accessed_at = datetime.now(timezone.utc)
                await db.commit()
            except DocumentPreparationError as exc:
                await db.rollback()
                document = await db.get(PaperDocument, paper_id)
                if document:
                    document.status = "failed"
                    document.error_code = exc.code
                    await db.commit()
            except Exception:
                await db.rollback()
                document = await db.get(PaperDocument, paper_id)
                if document:
                    document.status = "failed"
                    document.error_code = "document_prepare_failed"
                    await db.commit()
