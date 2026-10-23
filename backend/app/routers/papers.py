from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Paper
from app.schemas import PaperList, PaperOut, PaperViewerOut
from app.services.document_service import DocumentPreparationError, download_pdf
from app.services.paper_catalog_service import PaperCatalogError, get_or_import_paper
from app.services.paper_viewer_service import (
    parse_byte_range,
    public_pdf_viewer_url,
    resolve_paper_viewer_url,
)
from app.services.quota_service import (
    QuotaConfigurationError,
    QuotaExceeded,
    client_ip,
    enforce_pdf_limit,
)

router = APIRouter(prefix="/papers", tags=["papers"])

PAPER_SORTS = {
    "paper_score": Paper.paper_score,
    "read_first": Paper.read_first_score,
    "content": Paper.content_potential_score,
    "year": Paper.year,
    "citations": Paper.citations,
    "title": Paper.title,
}
DIFFICULTY_LEVELS = {
    "l1": "L1", "beginner": "L1",
    "l2": "L2", "intermediate": "L2",
    "l3": "L3", "advanced": "L3",
    "l4": "L4", "frontier": "L4",
    "unknown": "Unknown",
}
TAG_ALIASES = json.loads((Path(__file__).resolve().parents[1] / "tag_aliases.json").read_text())
TAG_GROUPS: dict[str, list[str]] = {}
for alias, canonical in TAG_ALIASES.items():
    TAG_GROUPS.setdefault(canonical, []).append(alias)


@router.get("", response_model=PaperList)
async def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = None,  # preprint | conference | journal
    venue: str | None = None,
    year: int | None = None,
    rank: str | None = None,  # A* | A | B
    tag: str | None = None,
    search: str | None = Query(None, max_length=300),
    difficulty: str | None = None,
    paper_type: str | None = None,
    sort_by: str = "paper_score",
    db: AsyncSession = Depends(get_db),
):
    if sort_by not in PAPER_SORTS:
        raise HTTPException(status_code=422, detail="invalid_sort")
    level = None
    if difficulty:
        level = DIFFICULTY_LEVELS.get(difficulty.strip().lower())
        if not level:
            raise HTTPException(status_code=422, detail="invalid_difficulty")

    q = select(Paper)
    if source_type:
        q = q.where(Paper.source_type == source_type)
    if venue:
        q = q.where(Paper.venue.ilike(f"%{venue}%"))
    if year:
        q = q.where(Paper.year == year)
    if rank:
        q = q.where(Paper.conference_rank == rank)
    if tag:
        canonical = TAG_ALIASES.get(tag, tag)
        q = q.where(or_(*(
            Paper.tags.contains([alias])
            for alias in TAG_GROUPS.get(canonical, [tag])
        )))
    if search:
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        author_names = (
            func.jsonb_array_elements_text(Paper.authors)
            .table_valued("name").render_derived()
        )
        q = q.where(or_(
            Paper.title.ilike(f"%{term}%", escape="\\"),
            Paper.abstract.ilike(f"%{term}%", escape="\\"),
            select(1).select_from(author_names).where(
                author_names.c.name.ilike(f"%{term}%", escape="\\")
            ).exists(),
        ))
    if level == "Unknown":
        q = q.where(or_(
            Paper.difficulty_level.is_(None),
            Paper.difficulty_level.in_(["", "Unknown"]),
        ))
    elif level:
        q = q.where(Paper.difficulty_level == level)
    if paper_type:
        q = q.where(Paper.paper_type == paper_type)

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    sort = PAPER_SORTS[sort_by]
    ordering = sort.asc() if sort_by == "title" else sort.desc().nulls_last()
    q = q.order_by(ordering, Paper.id.asc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return PaperList(total=total, page=page, page_size=page_size, results=rows)


@router.get("/conferences", response_model=PaperList)
async def list_conference_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    venue: str | None = None,
    year: int | None = None,
    rank: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Paper).where(Paper.source_type == "conference")
    if venue:
        q = q.where(Paper.venue.ilike(f"%{venue}%"))
    if year:
        q = q.where(Paper.year == year)
    if rank:
        q = q.where(Paper.conference_rank == rank)

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                q.order_by(Paper.paper_score.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return PaperList(total=total, page=page, page_size=page_size, results=rows)


@router.get("/journals", response_model=PaperList)
async def list_journal_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    venue: str | None = None,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Paper).where(Paper.source_type == "journal")
    if venue:
        q = q.where(Paper.venue.ilike(f"%{venue}%"))
    if year:
        q = q.where(Paper.year == year)

    total = (
        await db.execute(select(func.count()).select_from(q.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                q.order_by(Paper.paper_score.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return PaperList(total=total, page=page, page_size=page_size, results=rows)


@router.get("/{paper_id}", response_model=PaperOut)
async def get_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    try:
        paper = await get_or_import_paper(db, paper_id)
    except PaperCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.get("/{paper_id}/viewer-url", response_model=PaperViewerOut)
async def get_paper_viewer_url(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        paper = await get_or_import_paper(db, paper_id)
    except PaperCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    resolved = await resolve_paper_viewer_url(paper)
    return PaperViewerOut(
        viewer_url=public_pdf_viewer_url(paper_id, resolved),
        external_url=paper.pdf_url or paper.paper_url,
    )


@router.get("/{paper_id}/pdf", name="get_paper_pdf")
async def get_paper_pdf(
    paper_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        await enforce_pdf_limit(client_ip(request))
    except QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=exc.code) from exc
    except QuotaConfigurationError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc
    try:
        paper = await get_or_import_paper(db, paper_id)
    except PaperCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    resolved = await resolve_paper_viewer_url(paper)
    if not resolved:
        raise HTTPException(status_code=404, detail="pdf_unavailable")
    try:
        pdf_bytes = await download_pdf(resolved)
    except DocumentPreparationError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    total = len(pdf_bytes)
    etag = f'"{hashlib.sha256(pdf_bytes).hexdigest()}"'
    try:
        cache_seconds = int(
            os.environ.get("CHAT_PDF_RESPONSE_CACHE_SECONDS", "3600").strip()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="pdf_configuration_invalid"
        ) from exc
    if cache_seconds < 0:
        raise HTTPException(status_code=503, detail="pdf_configuration_invalid")
    common_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": f"public, max-age={cache_seconds}",
        "Content-Disposition": 'inline; filename="paper.pdf"',
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=common_headers)
    range_header = request.headers.get("range")
    if range_header and request.headers.get("if-range") not in {None, etag}:
        range_header = None
    try:
        selected = parse_byte_range(range_header, total)
    except ValueError as exc:
        raise HTTPException(
            status_code=416,
            detail="range_not_satisfiable",
            headers={"Content-Range": f"bytes */{total}", "Accept-Ranges": "bytes"},
        ) from exc
    start, end = selected or (0, total - 1)
    headers = {
        **common_headers,
        "Content-Length": str(end - start + 1),
    }
    status_code = 200
    if selected:
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    async def stream_pdf():
        for offset in range(start, end + 1, 64 * 1024):
            yield memoryview(pdf_bytes)[offset : min(offset + 64 * 1024, end + 1)]

    return StreamingResponse(
        stream_pdf(),
        status_code=status_code,
        media_type="application/pdf",
        headers=headers,
    )
