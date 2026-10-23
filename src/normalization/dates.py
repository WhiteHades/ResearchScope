"""Normalize source dates without inventing missing calendar precision."""
from __future__ import annotations

from datetime import date


def normalize_publication_date(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if len(value) != 10 or value[4] != "-" or value[7] != "-":
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""
