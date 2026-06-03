from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import Favourite, Paper, User
from app.schemas import FavouriteOut

router = APIRouter(prefix="/favourites", tags=["favourites"])


@router.get("", response_model=list[FavouriteOut])
async def list_favourites(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(Favourite)
        .where(Favourite.user_id == current_user.id)
        .options(selectinload(Favourite.paper))
        .order_by(Favourite.created_at.desc())
    )).scalars().all()
    return rows


@router.post("/{paper_id}", status_code=201)
async def add_favourite(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    paper = await db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = await db.get(Favourite, (current_user.id, paper_id))
    if existing:
        raise HTTPException(status_code=409, detail="Already in favourites")

    db.add(Favourite(user_id=current_user.id, paper_id=paper_id))
    await db.commit()
    return {"status": "added", "paper_id": paper_id}


@router.delete("/{paper_id}", status_code=204)
async def remove_favourite(
    paper_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fav = await db.get(Favourite, (current_user.id, paper_id))
    if not fav:
        raise HTTPException(status_code=404, detail="Not in favourites")
    await db.delete(fav)
    await db.commit()
