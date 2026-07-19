"""Repo URL → Digest via gitingest: smart excludes, token cap, per-commit cache."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatch

from reporadio.ingest import cache

# Vendored dirs, lockfiles, binaries, media — noise that wastes the token budget.
EXCLUDE_PATTERNS: set[str] = {
    "node_modules/*", "vendor/*", "dist/*", "build/*", ".git/*",
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "*.min.js", "*.min.css", "*.map",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.ico", "*.pdf",
    "*.woff", "*.woff2", "*.ttf", "*.eot",
    "*.mp3", "*.mp4", "*.wav", "*.onnx", "*.bin", "*.pt", "*.pth",
    "*.zip", "*.tar.gz", "*.whl", "*.so", "*.dylib", "*.dll",
    "*.ipynb", "*.csv", "*.parquet",
}

MAX_FILE_BYTES = 100_000  # per-file cap handed to gitingest

# gitingest separates files with a ==== / FILE: path / ==== header block
_FILE_HEADER = re.compile(r"^=+\s*\n(?:FILE|SYMLINK):\s*(.+?)\s*\n=+\s*\n?", re.MULTILINE)
_GITHUB_URL = re.compile(r"github\.com[/:]([^/]+)/([^/#?]+?)(?:\.git)?(?:[/#?].*)?$")


class IngestError(RuntimeError):
    pass


def estimate_tokens(text: str) -> int:
    return len(text) // 4


def repo_name(url: str) -> str:
    m = _GITHUB_URL.search(url)
    if not m:
        raise IngestError(
            f"Can't tune in to '{url}' — expected a GitHub repo URL like "
            "https://github.com/owner/repo"
        )
    return f"{m.group(1)}/{m.group(2)}"


def is_excluded(path: str) -> bool:
    path = path.lstrip("/")
    return any(
        fnmatch(path, pat) or fnmatch(f"{path}/", pat) or f"/{pat.rstrip('/*')}/" in f"/{path}"
        for pat in EXCLUDE_PATTERNS
    )


def fetch_commit_messages(name: str, limit: int = 30) -> list[str]:
    """Recent commit messages via the GitHub API — prime roast material.
    Best-effort: returns [] offline or when rate-limited."""
    import json
    from urllib.request import Request, urlopen

    url = f"https://api.github.com/repos/{name}/commits?per_page={limit}"
    try:
        req = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "reporadio",
            },
        )
        with urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        return [
            c["commit"]["message"].splitlines()[0][:100]
            for c in data
            if isinstance(c, dict) and "commit" in c
        ]
    except Exception:
        return []


def head_commit(url: str) -> str:
    """HEAD hash without cloning; 'latest' when the remote can't be reached."""
    try:
        out = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
        return out.split()[0] if out.split() else "latest"
    except (subprocess.SubprocessError, OSError, IndexError):
        return "latest"


def truncate_tree(tree: str, max_tokens: int) -> str:
    """Big repos have huge trees — cap it so files keep most of the budget."""
    if estimate_tokens(tree) <= max_tokens:
        return tree
    lines = tree.splitlines()
    keep: list[str] = []
    used = 0
    for line in lines:
        used += estimate_tokens(line) + 1
        if used > max_tokens:
            keep.append(f"… (+{len(lines) - len(keep)} more entries, tree truncated)")
            break
        keep.append(line)
    return "\n".join(keep)


def _priority(path: str) -> int:
    """Lower = more important for a tour."""
    p = path.lower()
    depth = path.count("/")
    if p.rsplit("/", 1)[-1].startswith("readme"):
        return 0
    if "test" in p or "example" in p or p.startswith("docs/") or "/docs/" in p:
        return 4
    if depth == 0:
        return 1
    return 2 if depth == 1 else 3


def parse_content(content: str) -> dict[str, str]:
    """gitingest's flat content blob → {path: file_text}."""
    matches = list(_FILE_HEADER.finditer(content))
    if not matches:
        return {"_digest": content}
    files: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        files[m.group(1)] = content[m.end():end].strip("\n")
    return files


def trim_to_cap(
    files: dict[str, str], max_tokens: int, overhead: str = ""
) -> tuple[dict[str, str], list[str]]:
    """Greedy-fill the token budget: README → root files → shallow core → docs/tests,
    smaller files first within each tier, so a tour keeps the load-bearing files."""
    budget = max_tokens - estimate_tokens(overhead)
    ordered = sorted(files, key=lambda p: (_priority(p), len(files[p])))
    kept: dict[str, str] = {}
    used = 0
    dropped: list[str] = []
    for path in ordered:
        cost = estimate_tokens(files[path])
        if used + cost <= budget:
            kept[path] = files[path]
            used += cost
        else:
            dropped.append(path)
    # preserve original file order for the digest text
    kept = {p: files[p] for p in files if p in kept}
    return kept, sorted(dropped, key=lambda p: -len(files[p]))


@dataclass
class Digest:
    url: str
    name: str
    commit: str
    summary: str
    tree: str
    files: dict[str, str]
    dropped: list[str] = field(default_factory=list)

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.tree) + sum(
            estimate_tokens(t) for t in self.files.values()
        )

    def content(self) -> str:
        parts = []
        for path, text in self.files.items():
            parts.append(f"{'=' * 48}\nFILE: {path}\n{'=' * 48}\n{text}")
        return "\n\n".join(parts)

    def to_payload(self) -> dict:
        return {
            "url": self.url, "name": self.name, "commit": self.commit,
            "summary": self.summary, "tree": self.tree,
            "files": self.files, "dropped": self.dropped,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "Digest":
        return cls(**payload)


def fetch(url: str, max_tokens: int = 8000, use_cache: bool = True) -> Digest:
    """Ingest a repo (or reuse the cached digest for this commit + budget)."""
    name = repo_name(url)
    commit = head_commit(url)
    key = f"{cache.slugify(name)}-{commit[:10]}-{max_tokens}"

    if use_cache and commit != "latest":
        cached = cache.load(key)
        if cached:
            return Digest.from_payload(cached)

    try:
        from loguru import logger as _loguru

        _loguru.disable("gitingest")  # keep the radio UI clean
    except ImportError:
        pass
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        from gitingest import ingest

        summary, tree, content = ingest(
            url, max_file_size=MAX_FILE_BYTES, exclude_patterns=EXCLUDE_PATTERNS
        )
    except Exception as err:  # gitingest raises plain exceptions for 404/private
        raise IngestError(
            f"Couldn't ingest {name} — is the repo public and the URL right?\n"
            f"(Tip: if the repo was renamed/moved, use its current URL.) ({err})"
        ) from err

    tree = truncate_tree(tree, max_tokens // 4)
    files = {p: t for p, t in parse_content(content).items() if not is_excluded(p)}
    files, dropped = trim_to_cap(files, max_tokens, overhead=tree + summary)

    digest = Digest(
        url=url, name=name, commit=commit, summary=summary,
        tree=tree, files=files, dropped=dropped,
    )
    if commit != "latest":
        cache.save(key, digest.to_payload())
    return digest
