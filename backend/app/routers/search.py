from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Paper
from app.schemas import SearchResult

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResult)
async def search(
    q: str = Query(..., min_length=2),
    source_type: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    # PostgreSQL full-text search via tsvector
    tsq = func.plainto_tsquery("english", q)

    stmt = (
        select(Paper)
        .where(Paper.search_vector.op("@@")(tsq))
    )
    if source_type:
        stmt = stmt.where(Paper.source_type == source_type)

    # Rank by ts_rank + paper_score
    rank_expr = func.ts_rank(Paper.search_vector, tsq)
    stmt = stmt.order_by((rank_expr + Paper.paper_score / 10).desc()).limit(limit)

    rows  = (await db.execute(stmt)).scalars().all()
    total = len(rows)

    return SearchResult(total=total, query=q, results=rows)
