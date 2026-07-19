import json
from types import SimpleNamespace

import pytest

from reporadio.ingest.fetcher import Digest
from reporadio.show.script import ScriptError, Segment, generate_segments


def make_digest() -> Digest:
    return Digest(
        url="https://github.com/x/y", name="x/y", commit="abc1234567",
        summary="Repository: x/y", tree="src/\n  app.py",
        files={"src/app.py": "print('hi')"},
    )


def chunks_from(text: str, size: int = 7):
    """Split a response into small stream chunks to exercise line buffering."""
    for i in range(0, len(text), size):
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text[i:i + size]))]
        )


class FakeClient:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls = 0
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls += 1
        return chunks_from(self._responses.pop(0))


def ndjson(*segs) -> str:
    return "\n".join(json.dumps(s) for s in segs) + "\n"


VALID = ndjson(
    {"title": "The cold open", "spoken_text": "Welcome to RepoRadio."},
    {"title": "Entry point", "spoken_text": "It all starts in app dot py."},
)


def test_valid_ndjson_streams_segments():
    client = FakeClient([VALID])
    segs = list(generate_segments(make_digest(), client=client))
    assert client.calls == 1
    assert [s.title for s in segs] == ["The cold open", "Entry point"]
    assert all(isinstance(s, Segment) for s in segs)


def test_last_line_without_newline_is_flushed():
    client = FakeClient([VALID.rstrip("\n")])
    segs = list(generate_segments(make_digest(), client=client))
    assert len(segs) == 2


def test_garbage_lines_are_skipped():
    noisy = "Sure! Here's your tour:\n" + VALID + "Hope that helps!\n"
    client = FakeClient([noisy])
    segs = list(generate_segments(make_digest(), client=client))
    assert len(segs) == 2


def test_invalid_then_valid_retries_once():
    client = FakeClient(["I am a helpful assistant and here is prose.", VALID])
    segs = list(generate_segments(make_digest(), client=client))
    assert client.calls == 2
    assert len(segs) == 2


def test_all_invalid_raises_script_error():
    client = FakeClient(["prose only", "still prose"])
    with pytest.raises(ScriptError):
        list(generate_segments(make_digest(), client=client))
    assert client.calls == 2


def test_segment_rejects_empty_fields():
    with pytest.raises(ValueError):
        Segment(title="  ", spoken_text="hello")
    with pytest.raises(ValueError):
        Segment(title="ok", spoken_text="")


def test_segment_ignores_extra_keys():
    seg = Segment(title="t", spoken_text="s", mood="spicy")
    assert seg.title == "t"
