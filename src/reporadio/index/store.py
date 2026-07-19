"""Persistent ChromaDB index per repo@commit, embedded with fastembed bge-small."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from reporadio.config import get_settings
from reporadio.ingest.cache import slugify

EMBED_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass
class Hit:
    path: str
    start_line: int
    text: str
    distance: float


class _FastEmbed:
    """Process-wide singleton — the model load is the expensive part."""

    _model = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._model is None:
                from fastembed import TextEmbedding

                cls._model = TextEmbedding(
                    EMBED_MODEL,
                    cache_dir=str(get_settings().data_dir / "fastembed"),
                )
            return cls._model


def collection_name(repo: str, commit: str) -> str:
    return f"{slugify(repo)}-{commit[:10]}"[:63]


class RepoIndex:
    def __init__(self, repo: str, commit: str, *, embed=None):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._embed = embed  # tests inject a deterministic embedder
        client = chromadb.PersistentClient(
            path=str(get_settings().data_dir / "chroma"),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._col = client.get_or_create_collection(
            collection_name(repo, commit), metadata={"hnsw:space": "cosine"}
        )
        self.ready = threading.Event()
        if self.count() > 0:  # previously indexed run of this repo@commit
            self.ready.set()

    def _vectors(self, texts: list[str], query: bool = False) -> list[list[float]]:
        if self._embed is not None:
            return self._embed(texts)
        model = _FastEmbed.get()
        if query and hasattr(model, "query_embed"):
            return [list(map(float, v)) for v in model.query_embed(texts)]
        return [list(map(float, v)) for v in model.embed(texts)]

    def count(self) -> int:
        return self._col.count()

    def build(self, chunks, batch: int = 64) -> None:
        for i in range(0, len(chunks), batch):
            b = chunks[i:i + batch]
            self._col.upsert(
                ids=[c.id for c in b],
                documents=[c.text for c in b],
                embeddings=self._vectors([c.text for c in b]),
                metadatas=[{"path": c.path, "start_line": c.start_line} for c in b],
            )
        self.ready.set()

    def query(self, text: str, k: int = 6) -> list[Hit]:
        n = self.count()
        if n == 0:
            return []
        res = self._col.query(
            query_embeddings=self._vectors([text], query=True),
            n_results=min(k, n),
            include=["documents", "metadatas", "distances"],
        )
        return [
            Hit(path=m["path"], start_line=int(m["start_line"]), text=d, distance=dist)
            for d, m, dist in zip(
                res["documents"][0], res["metadatas"][0], res["distances"][0]
            )
        ]


def build_index_async(digest, *, embed=None) -> RepoIndex:
    """Start indexing in a background thread so the tour keeps speaking.
    index.ready fires when the collection is queryable."""
    index = RepoIndex(digest.name, digest.commit, embed=embed)
    if not index.ready.is_set():
        def _work():
            from reporadio.index.chunker import chunk_digest

            index.build(chunk_digest(digest))

        threading.Thread(target=_work, daemon=True).start()
    return index
