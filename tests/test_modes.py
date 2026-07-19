import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from reporadio.cli import app
from reporadio.ingest.fetcher import Digest
from reporadio.show.modes import (
    ModeError,
    get_mode,
    language_block,
    load_modes,
)
from reporadio.show.script import PROMPTS_DIR, generate_segments

runner = CliRunner()


def test_all_stations_load():
    modes = load_modes()
    assert set(modes) == {"standard", "casual", "fun_roast"}
    freqs = {m.freq for m in modes.values()}
    assert freqs == {"88.1", "95.7", "101.5"}


def test_every_mode_prompt_file_exists():
    for mode in load_modes().values():
        assert (PROMPTS_DIR / f"{mode.prompt}.md").is_file(), mode.key
    assert (PROMPTS_DIR / "agent.md").is_file()  # live conversation prompt


def test_all_modes_use_kokoro():
    for key in ("standard", "casual", "fun_roast"):
        assert get_mode(key).voice.engine == "kokoro"
    assert get_mode("standard").voice.name == "af_heart"


def test_greetings_ask_the_caller():
    for mode in load_modes().values():
        assert "?" in mode.greeting, f"{mode.key} greeting should invite a question"


def test_unknown_mode_lists_stations():
    with pytest.raises(ModeError) as err:
        get_mode("metal")
    msg = str(err.value)
    assert "88.1" in msg and "101.5" in msg and "casual" in msg


def test_language_blocks():
    assert language_block("en") == ""
    assert "Roman Urdu" in language_block("roman")
    assert "Urdu script" in language_block("ur")
    assert "mix" in language_block("mix").lower()
    with pytest.raises(ModeError):
        language_block("klingon")


# --- lang + roast material reach the actual prompts ---

def chunks_from(text, size=40):
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
        line = json.dumps({"title": "t", "spoken_text": "s"}) + "\n"
        return chunks_from(line)


def make_digest():
    return Digest(
        url="u", name="x/y", commit="a" * 10, summary="s", tree="t",
        files={"a.py": "print(1)"},
    )


def test_lang_block_reaches_system_prompt():
    client = FakeClient()
    list(generate_segments(make_digest(), client=client, lang="roman"))
    assert "Roman Urdu" in client.kwargs["messages"][0]["content"]


def test_roast_material_reaches_user_prompt():
    client = FakeClient()
    list(generate_segments(
        make_digest(), client=client, prompt_name="fun_roast",
        extra_context="RECENT COMMIT MESSAGES (roast material):\n- fix\n- fix again",
    ))
    user = client.kwargs["messages"][1]["content"]
    assert "fix again" in user
    system = client.kwargs["messages"][0]["content"]
    assert "Roast FM" in system


def test_mode_temperature_flows_through():
    client = FakeClient()
    list(generate_segments(make_digest(), client=client, temperature=0.9))
    assert client.kwargs["temperature"] == 0.9


# --- CLI surface ---

def test_stations_command():
    result = runner.invoke(app, ["stations"])
    assert result.exit_code == 0
    assert "88.1" in result.output and "101.5" in result.output
    assert "casual" in result.output


def test_tour_unknown_mode_is_friendly(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    result = runner.invoke(
        app, ["tour", "https://github.com/x/y", "--mode", "metal"]
    )
    assert result.exit_code == 1
    assert "No station" in result.output


def test_roast_command_wired():
    result = runner.invoke(app, ["roast", "--help"])
    assert result.exit_code == 0
    assert "Roast FM" in result.output
