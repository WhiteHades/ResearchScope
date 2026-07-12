from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import Paper, PaperDocument, User
from app.schemas_chat import DocumentStatusOut
from app.services.document_service import (
    DocumentPreparationError,
    prepare_document,
    queue_document,
    safe_pdf_url,
)
from app.services.paper_catalog_service import PaperCatalogError, get_or_import_paper
from app.services.provider_service import chat_enabled

router = APIRouter(prefix="/papers", tags=["paper-chat-documents"])


def _status(paper: Paper, document: PaperDocument | None) -> DocumentStatusOut:
    return DocumentStatusOut(
        paper_id=paper.id,
        status=document.status if document else "not_prepared",
        page_count=document.page_count if document else 0,
        chunk_count=document.chunk_count if document else 0,
        viewer_url=safe_pdf_url(paper),
        error_code=document.error_code if document else None,
    )


@router.get("/{paper_id}/document-status", response_model=DocumentStatusOut)
async def document_status(
    paper_id: str,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        paper = await get_or_import_paper(db, paper_id)
    except PaperCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return _status(paper, await db.get(PaperDocument, paper_id))


@router.post("/{paper_id}/prepare", response_model=DocumentStatusOut)
async def prepare(
    paper_id: str,
    background_tasks: BackgroundTasks,
    response: Response,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not chat_enabled():
        raise HTTPException(status_code=503, detail="chat_disabled")
    try:
        paper = await get_or_import_paper(db, paper_id)
    except PaperCatalogError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    try:
        status = await queue_document(paper_id)
    except DocumentPreparationError as exc:
        raise HTTPException(
            status_code=404 if exc.code == "paper_not_found" else 422, detail=exc.code
        )
    if status == "queued":
        response.status_code = 202
        background_tasks.add_task(prepare_document, paper_id)
    elif status == "preparing":
        response.status_code = 202
    document = await db.get(PaperDocument, paper_id)
    if document:
        await db.refresh(document)
    return _status(paper, document)
