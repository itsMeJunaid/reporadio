import pytest

from reporadio.index.chunker import Chunk, chunk_digest, chunk_file
from reporadio.ingest.fetcher import Digest

PY_FILE = "\n\n".join(
    f"def func_{i}():\n" + "\n".join(f"    x_{i} = {j}" for j in range(12))
    for i in range(6)
)


def test_chunk_file_metadata():
    chunks = chunk_file("src/app.py", PY_FILE, chunk_size=300, overlap=30)
    assert len(chunks) > 1
    assert all(c.path == "src/app.py" for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
    assert chunks[0].start_line == 1
    lines = [c.start_line for c in chunks]
    assert lines == sorted(lines)
    assert lines[-1] > 1


def test_chunk_file_unknown_extension_falls_back():
    chunks = chunk_file("notes.xyz", "word " * 500, chunk_size=400, overlap=40)
    assert len(chunks) > 1


def test_chunk_digest_skips_empty_files():
    digest = Digest(
        url="u", name="x/y", commit="c" * 10, summary="", tree="",
        files={"a.py": "def f():\n    return 1", "empty.py": "   \n"},
    )
    chunks = chunk_digest(digest)
    assert {c.path for c in chunks} == {"a.py"}


# --- store round-trip with a deterministic fake embedder (no model download) ---

TOPICS = ["auth", "database", "frontend"]


def fake_embed(texts):
    return [
        [float(t.count(topic)) for topic in TOPICS] + [1.0] for t in texts
    ]


@pytest.fixture
def tmp_settings(tmp_path, monkeypatch):
    from reporadio import config
    from reporadio.index import store

    settings = config.Settings(groq_api_key="x", data_dir=tmp_path, _env_file=None)
    monkeypatch.setattr(store, "get_settings", lambda: settings)
    return settings


def make_chunks():
    return [
        Chunk(id="auth.py:0", path="auth.py", start_line=1,
              text="auth auth login handler checks the auth token"),
        Chunk(id="db.py:0", path="db.py", start_line=10,
              text="database session commits rows to the database"),
        Chunk(id="ui.js:0", path="ui.js", start_line=5,
              text="frontend renders the frontend button"),
    ]


def test_store_round_trip(tmp_settings):
    from reporadio.index.store import RepoIndex

    index = RepoIndex("x/y", "abc1234567", embed=fake_embed)
    assert not index.ready.is_set()
    index.build(make_chunks())
    assert index.ready.is_set()
    assert index.count() == 3

    hits = index.query("where is the auth logic", k=2)
    assert hits[0].path == "auth.py"
    assert hits[0].start_line == 1
    assert "auth" in hits[0].text


def test_store_persists_across_instances(tmp_settings):
    from reporadio.index.store import RepoIndex

    RepoIndex("x/y", "abc1234567", embed=fake_embed).build(make_chunks())
    again = RepoIndex("x/y", "abc1234567", embed=fake_embed)
    assert again.ready.is_set()  # already indexed → no re-embed needed
    assert again.count() == 3


def test_build_index_async_signals_ready(tmp_settings):
    from reporadio.index.store import build_index_async

    digest = Digest(
        url="u", name="x/y", commit="def7654321", summary="", tree="",
        files={"auth.py": "auth token validation lives here"},
    )
    index = build_index_async(digest, embed=fake_embed)
    assert index.ready.wait(timeout=15)
    assert index.count() >= 1
