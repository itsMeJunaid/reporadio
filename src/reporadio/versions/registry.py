"""SQLite registry: every analyzed repo@commit is a version, old Chroma
collections stay put, and changelog episodes get archived."""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field

from reporadio.config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos(
  name TEXT PRIMARY KEY,
  url TEXT,
  first_seen TEXT
);
CREATE TABLE IF NOT EXISTS versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  commit_hash TEXT NOT NULL,
  analyzed_at TEXT NOT NULL,
  file_count INTEGER,
  token_count INTEGER,
  languages TEXT,
  files TEXT,
  UNIQUE(repo, commit_hash)
);
CREATE TABLE IF NOT EXISTS episodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  from_commit TEXT,
  to_commit TEXT,
  mode TEXT,
  created_at TEXT,
  transcript TEXT
);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _db() -> sqlite3.Connection:
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data_dir / "reporadio.db")
    con.executescript(_SCHEMA)
    con.row_factory = sqlite3.Row
    return con


@dataclass
class Version:
    repo: str
    commit: str
    analyzed_at: str
    file_count: int
    token_count: int
    languages: str
    files: dict[str, int] = field(default_factory=dict)  # path -> size (chars)


def _row_to_version(row: sqlite3.Row) -> Version:
    return Version(
        repo=row["repo"], commit=row["commit_hash"], analyzed_at=row["analyzed_at"],
        file_count=row["file_count"], token_count=row["token_count"],
        languages=row["languages"] or "",
        files=json.loads(row["files"] or "{}"),
    )


def _languages(sizes: dict[str, int]) -> str:
    total = sum(sizes.values()) or 1
    by_ext: Counter[str] = Counter()
    for path, size in sizes.items():
        ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else "other"
        by_ext[ext] += size
    return " · ".join(f"{ext} {100 * n // total}%" for ext, n in by_ext.most_common(3))


def record_version(digest) -> bool:
    """Idempotent: returns True only when this repo@commit is new to the archive."""
    sizes = digest.sizes or {p: len(t) for p, t in digest.files.items()}
    con = _db()
    try:
        with con:
            con.execute(
                "INSERT OR IGNORE INTO repos(name, url, first_seen) VALUES (?,?,?)",
                (digest.name, digest.url, _now()),
            )
            cur = con.execute(
                "INSERT OR IGNORE INTO versions"
                "(repo, commit_hash, analyzed_at, file_count, token_count, languages, files)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    digest.name, digest.commit, _now(), len(sizes),
                    digest.token_estimate, _languages(sizes), json.dumps(sizes),
                ),
            )
            return cur.rowcount > 0
    finally:
        con.close()


def list_versions(repo: str) -> list[Version]:
    con = _db()
    try:
        rows = con.execute(
            "SELECT * FROM versions WHERE repo = ? ORDER BY id", (repo,)
        ).fetchall()
        return [_row_to_version(r) for r in rows]
    finally:
        con.close()


def last_two(repo: str) -> tuple[Version, Version] | None:
    """(previous, latest) — or None when fewer than two versions exist."""
    versions = list_versions(repo)
    if len(versions) < 2:
        return None
    return versions[-2], versions[-1]


def get_version(repo: str, commit_prefix: str) -> Version | None:
    for v in list_versions(repo):
        if v.commit.startswith(commit_prefix):
            return v
    return None


def record_episode(
    repo: str, from_commit: str, to_commit: str, mode: str, transcript: str
) -> None:
    con = _db()
    try:
        with con:
            con.execute(
                "INSERT INTO episodes(repo, from_commit, to_commit, mode, created_at, transcript)"
                " VALUES (?,?,?,?,?,?)",
                (repo, from_commit, to_commit, mode, _now(), transcript),
            )
    finally:
        con.close()


def list_episodes(repo: str) -> list[sqlite3.Row]:
    con = _db()
    try:
        return con.execute(
            "SELECT * FROM episodes WHERE repo = ? ORDER BY id", (repo,)
        ).fetchall()
    finally:
        con.close()


# ---------------------------------------------------------------- digest diff

@dataclass
class DigestDiff:
    added: list[tuple[str, int]]
    removed: list[tuple[str, int]]
    changed: list[tuple[str, int, int]]  # (path, old_size, new_size)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def render(self) -> str:
        lines: list[str] = []
        if self.added:
            lines.append("ADDED FILES:")
            lines += [f"- {p} ({n} chars)" for p, n in self.added]
        if self.removed:
            lines.append("REMOVED FILES:")
            lines += [f"- {p} (was {n} chars)" for p, n in self.removed]
        if self.changed:
            lines.append("CHANGED FILES (size shift):")
            lines += [f"- {p}: {a} -> {b} chars" for p, a, b in self.changed]
        return "\n".join(lines) if lines else "No file-level changes detected."


def diff_versions(old: Version, new: Version) -> DigestDiff:
    added = sorted(
        ((p, n) for p, n in new.files.items() if p not in old.files),
        key=lambda x: -x[1],
    )
    removed = sorted(
        ((p, n) for p, n in old.files.items() if p not in new.files),
        key=lambda x: -x[1],
    )
    changed = sorted(
        (
            (p, old.files[p], n)
            for p, n in new.files.items()
            if p in old.files and old.files[p] != n
        ),
        key=lambda x: -abs(x[2] - x[1]),
    )
    return DigestDiff(added=added, removed=removed, changed=changed)
