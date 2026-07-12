from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaperChunk


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    chunk_index: int
    page_start: int
    page_end: int
    section: str | None
    content: str


def _to_result(chunk: PaperChunk) -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk.id,
        chunk_index=chunk.chunk_index,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        section=chunk.section,
        content=chunk.content,
    )


async def retrieve_chunks(
    db: AsyncSession, paper_id: str, query: str, *, limit: int = 10
) -> list[RetrievedChunk]:
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(PaperChunk.search_vector, tsquery)
    top_stmt = (
        select(PaperChunk)
        .where(PaperChunk.paper_id == paper_id)
        .where(PaperChunk.search_vector.op("@@")(tsquery))
        .order_by(rank.desc(), PaperChunk.chunk_index)
        .limit(min(limit, 8))
    )
    top = list((await db.execute(top_stmt)).scalars().all())
    if not top:
        fallback = list(
            (
                await db.execute(
                    select(PaperChunk)
                    .where(PaperChunk.paper_id == paper_id)
                    .order_by(PaperChunk.chunk_index)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_to_result(chunk) for chunk in fallback]

    indexes = {chunk.chunk_index for chunk in top}
    for chunk in top[:3]:
        indexes.update({chunk.chunk_index - 1, chunk.chunk_index + 1})
    indexes = {index for index in indexes if index >= 0}
    expanded = list(
        (
            await db.execute(
                select(PaperChunk)
                .where(
                    PaperChunk.paper_id == paper_id, PaperChunk.chunk_index.in_(indexes)
                )
                .order_by(PaperChunk.chunk_index)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_to_result(chunk) for chunk in expanded]
