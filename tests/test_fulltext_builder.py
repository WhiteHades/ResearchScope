"""Tests for bounded full-text PDF downloads."""
from __future__ import annotations

from src.fulltext import builder


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.read_size: int | None = None

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_size = size
        return self.payload if size < 0 else self.payload[:size]


def test_download_pdf_reads_only_one_byte_past_limit(monkeypatch):
    response = _Response(b"x" * 100)
    monkeypatch.setattr(
        builder.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response,
    )

    payload = builder._download_pdf("https://example.test/paper.pdf", max_bytes=10)

    assert response.read_size == 11
    assert payload is None
