"""Language-aware code chunking with file-path + start-line metadata."""

from __future__ import annotations

from dataclasses import dataclass

EXT_LANGUAGE = {
    ".py": "python", ".js": "js", ".jsx": "js", ".ts": "ts", ".tsx": "ts",
    ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cs": "csharp",
    ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
    ".md": "markdown", ".html": "html",
}

CHUNK_SIZE = 1200
OVERLAP = 120


@dataclass
class Chunk:
    id: str
    path: str
    start_line: int
    text: str


def _splitter_for(path: str, chunk_size: int, overlap: int):
    from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    lang = EXT_LANGUAGE.get(ext)
    if lang:
        try:
            return RecursiveCharacterTextSplitter.from_language(
                Language(lang), chunk_size=chunk_size, chunk_overlap=overlap
            )
        except ValueError:
            pass
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)


def chunk_file(
    path: str, text: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    """Split one file by code structure (function/class boundaries where possible),
    tagging every chunk with its path and 1-based start line."""
    parts = _splitter_for(path, chunk_size, overlap).split_text(text)
    chunks: list[Chunk] = []
    search_from = 0
    for i, part in enumerate(parts):
        offset = text.find(part, search_from)
        if offset < 0:
            offset = max(text.find(part), 0)
        start_line = text.count("\n", 0, offset) + 1
        search_from = offset + 1  # overlapping chunks may start before the last end
        chunks.append(Chunk(id=f"{path}:{i}", path=path, start_line=start_line, text=part))
    return chunks


def chunk_digest(digest) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path, text in digest.files.items():
        if text.strip():
            chunks.extend(chunk_file(path, text))
    return chunks
