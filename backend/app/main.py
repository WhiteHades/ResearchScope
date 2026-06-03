from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import auth, favourites, papers, pipeline, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="ResearchScope API",
    description="REST API for CS research papers, journals, conferences, authors, and more.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(search.router)
app.include_router(auth.router)
app.include_router(favourites.router)
app.include_router(pipeline.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "name": "ResearchScope API",
        "docs": "/docs",
        "endpoints": ["/papers", "/search", "/auth", "/favourites", "/pipeline"],
    }
