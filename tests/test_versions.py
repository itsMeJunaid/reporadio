import json
from types import SimpleNamespace

import pytest
from rich.console import Console

from reporadio.ingest.fetcher import Digest
from reporadio.show.modes import get_mode
from reporadio.show.script import generate_changelog
from reporadio.versions import registry
from reporadio.versions.registry import Version, diff_versions


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    from reporadio import config

    settings = config.Settings(groq_api_key="x", data_dir=tmp_path, _env_file=None)
    monkeypatch.setattr(registry, "get_settings", lambda: settings)
    return settings


def make_digest(commit="a" * 40, files=None):
    files = files or {"app.py": "x" * 400, "readme.md": "y" * 100}
    return Digest(
        url="https://github.com/x/y", name="x/y", commit=commit,
        summary="s", tree="t", files=files,
        sizes={p: len(t) for p, t in files.items()},
    )


def test_record_version_round_trip(tmp_registry):
    assert registry.record_version(make_digest()) is True
    assert registry.record_version(make_digest()) is False  # idempotent
    rows = registry.list_versions("x/y")
    assert len(rows) == 1
    v = rows[0]
    assert v.commit == "a" * 40
    assert v.file_count == 2
    assert v.files["app.py"] == 400
    assert "py" in v.languages


def test_two_versions_and_last_two(tmp_registry):
    registry.record_version(make_digest("a" * 40))
    registry.record_version(make_digest("b" * 40, files={"app.py": "x" * 900}))
    assert len(registry.list_versions("x/y")) == 2
    old, new = registry.last_two("x/y")
    assert old.commit.startswith("a")
    assert new.commit.startswith("b")


def test_last_two_requires_two(tmp_registry):
    assert registry.last_two("x/y") is None
    registry.record_version(make_digest())
    assert registry.last_two("x/y") is None


def test_get_version_by_prefix(tmp_registry):
    registry.record_version(make_digest("abc123" + "0" * 34))
    assert registry.get_version("x/y", "abc123").commit.startswith("abc123")
    assert registry.get_version("x/y", "beef") is None


def test_episode_round_trip(tmp_registry):
    registry.record_episode("x/y", "aaa", "bbb", "desi", "— Intro —\nHaan G")
    rows = registry.list_episodes("x/y")
    assert len(rows) == 1
    assert rows[0]["mode"] == "desi"
    assert "Haan G" in rows[0]["transcript"]


# ---------------------------------------------------------------- diff

def test_diff_versions():
    old = Version("x/y", "a", "t", 3, 100, "",
                  files={"a.py": 100, "b.py": 200, "c.py": 300})
    new = Version("x/y", "b", "t", 3, 100, "",
                  files={"b.py": 200, "c.py": 450, "d.py": 50})
    diff = diff_versions(old, new)
    assert diff.added == [("d.py", 50)]
    assert diff.removed == [("a.py", 100)]
    assert diff.changed == [("c.py", 300, 450)]
    assert not diff.empty
    rendered = diff.render()
    assert "d.py" in rendered and "a.py" in rendered and "c.py" in rendered


def test_diff_empty():
    v = Version("x/y", "a", "t", 1, 10, "", files={"a.py": 1})
    diff = diff_versions(v, v)
    assert diff.empty
    assert "No file-level changes" in diff.render()


# ------------------------------------------------- changelog prompt plumbing

def chunks_from(text, size=60):
    for i in range(0, len(text), size):
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text[i:i + size]))]
        )


class FakeClient:
    def __init__(self):
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return chunks_from(json.dumps({"title": "t", "spoken_text": "s"}) + "\n")


def test_generate_changelog_prompt_contains_diff_and_mode():
    old = Version("x/y", "a" * 40, "2026-01-01", 2, 100, "", files={"a.py": 100})
    new = Version("x/y", "b" * 40, "2026-01-02", 2, 100, "",
                  files={"a.py": 100, "brand_new.py": 55})
    diff = diff_versions(old, new)
    client = FakeClient()
    segs = list(generate_changelog(
        make_digest(), old, new, diff, mode=get_mode("desi"), lang="roman",
        client=client,
    ))
    assert len(segs) == 1
    system = client.kwargs["messages"][0]["content"]
    user = client.kwargs["messages"][1]["content"]
    assert "CHANGELOG EPISODE" in system  # override block appended to mode prompt
    assert "Desi FM" in system            # mode personality present
    assert "Roman Urdu" in system         # lang block present
    assert "brand_new.py" in user         # the actual diff reached the prompt


# ------------------------------------------------- changelog needs two versions

def test_run_changelog_requires_two_versions(tmp_registry, monkeypatch):
    from reporadio.session import broadcaster as bc
    from reporadio.voice.player import NullPlayer

    digest = make_digest()
    registry.record_version(digest)  # only ONE version on file

    monkeypatch.setattr(
        bc.fetcher, "fetch", lambda url, max_tokens=8000, use_cache=True, at_commit=None: digest
    )
    caster = bc.Broadcaster(
        Console(file=None), SimpleNamespace(name="fake", synth=lambda t: None),
        NullPlayer(), mode=get_mode("standard"), mic_enabled=False,
    )
    with pytest.raises(bc.ChangelogError) as err:
        caster.run_changelog("https://github.com/x/y")
    assert "needs two" in str(err.value)
