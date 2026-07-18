"""Tests for pgvector support probing and index-dimension configuration."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.database import (  # noqa: E402
    PGVECTOR_INDEX_DIMENSIONS,
    configured_embedding_dimensions,
)
from app.services import retrieval_service  # noqa: E402
from app.services.retrieval_service import (  # noqa: E402
    _pgvector_available,
    _semantic_search_statement,
    reset_pgvector_support_cache,
)


class _CountingSession:
    """Counts how many times the support probe reaches the database."""

    def __init__(self, supported: bool = True):
        self.supported = supported
        self.probes = 0

    async def execute(self, _statement):
        self.probes += 1
        supported = self.supported

        class _Result:
            @staticmethod
            def scalar_one():
                return supported

        return _Result()


def test_pgvector_support_is_probed_once_and_reused():
    reset_pgvector_support_cache()
    db = _CountingSession(supported=True)

    results = asyncio.run(
        _probe_many(db, times=5)
    )

    assert results == [True] * 5
    assert db.probes == 1, "support probe should not run per query"


def test_negative_pgvector_support_is_also_cached():
    reset_pgvector_support_cache()
    db = _CountingSession(supported=False)

    results = asyncio.run(_probe_many(db, times=3))

    assert results == [False] * 3
    assert db.probes == 1


def test_cache_reset_forces_a_fresh_probe():
    reset_pgvector_support_cache()
    db = _CountingSession(supported=True)
    asyncio.run(_probe_many(db, times=2))
    assert db.probes == 1

    reset_pgvector_support_cache()
    asyncio.run(_probe_many(db, times=1))
    assert db.probes == 2


async def _probe_many(db, *, times: int) -> list[bool]:
    return [await _pgvector_available(db) for _ in range(times)]


def test_typed_vector_cast_tracks_the_shared_index_dimension():
    """The typed cast must follow PGVECTOR_INDEX_DIMENSIONS, not a literal."""
    sql = str(
        _semantic_search_statement(
            dimensions=PGVECTOR_INDEX_DIMENSIONS, pgvector=True, filter_model=False
        )
    )
    assert f"vector({PGVECTOR_INDEX_DIMENSIONS})" in sql

    # A different width cannot use the typed index, so it must not claim to.
    other = PGVECTOR_INDEX_DIMENSIONS * 2
    other_sql = str(
        _semantic_search_statement(dimensions=other, pgvector=True, filter_model=False)
    )
    assert f"vector({other})" not in other_sql
    assert "AS vector)" in other_sql


def test_configured_embedding_dimensions_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "512")
    assert configured_embedding_dimensions() == 512

    monkeypatch.delenv("OPENAI_EMBEDDING_DIMENSIONS", raising=False)
    assert configured_embedding_dimensions() == PGVECTOR_INDEX_DIMENSIONS

    monkeypatch.setenv("OPENAI_EMBEDDING_DIMENSIONS", "not-a-number")
    assert configured_embedding_dimensions() == PGVECTOR_INDEX_DIMENSIONS


def teardown_module(_module):
    """Leave no cached state behind for other test modules."""
    retrieval_service.reset_pgvector_support_cache()
