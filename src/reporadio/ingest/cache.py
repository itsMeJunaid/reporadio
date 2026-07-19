"""Digest cache: one JSON file per repo@commit under data_dir/digests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from reporadio.config import get_settings


def slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower()


def cache_dir() -> Path:
    path = get_settings().data_dir / "digests"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load(key: str) -> dict | None:
    path = cache_dir() / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save(key: str, payload: dict) -> None:
    path = cache_dir() / f"{key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def find(key_prefix: str) -> dict | None:
    """First cached digest whose key starts with the prefix (any token budget)."""
    for path in sorted(cache_dir().glob(f"{key_prefix}*.json")):
        payload = load(path.stem)
        if payload:
            return payload
    return None
