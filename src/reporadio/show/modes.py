"""Config-driven personalities: modes.yaml is the single source of truth.
Adding a station = one YAML entry + one prompt file. Zero code change."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

MODES_FILE = Path(__file__).parent / "modes.yaml"

LANGUAGES = ("en", "ur", "roman", "mix")

_LANGUAGE_BLOCKS = {
    "en": "",
    "ur": (
        "\n\nLANGUAGE: Speak in Urdu (Urdu script). Keep all technical terms — "
        "file names, functions, libraries — in English."
    ),
    "roman": (
        "\n\nLANGUAGE: Speak in Roman Urdu (Urdu written in Latin letters), with "
        "natural English code-switching, like a Karachi FM host. Technical terms "
        "— file names, functions, libraries — ALWAYS stay in English. "
        "Tone example: 'Chaliye, ab dekhte hain cli dot py — yahan se sara show "
        "shuru hota hai.'"
    ),
    "mix": (
        "\n\nLANGUAGE: Speak in a warm, natural Urdu-English mix — Roman Urdu "
        "sentences flowing in and out of English, the way desi devs actually "
        "talk. Technical terms always in English. Keep it effortless, never "
        "forced: 'So basically yeh function request ko validate karta hai, "
        "and then it hands off to the router.'"
    ),
}


class ModeError(RuntimeError):
    pass


class ModeVoice(BaseModel):
    engine: str
    name: str


class Mode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    freq: str
    title: str
    prompt: str
    voice: ModeVoice
    language: str = "en"
    temperature: float = 0.7
    greeting: str = ""


def load_modes() -> dict[str, Mode]:
    import yaml

    raw = yaml.safe_load(MODES_FILE.read_text(encoding="utf-8"))
    return {key: Mode(key=key, **cfg) for key, cfg in raw.items()}


def get_mode(name: str) -> Mode:
    modes = load_modes()
    if name not in modes:
        stations = "\n".join(
            f"  {m.freq}  {m.key:<10} {m.title}" for m in modes.values()
        )
        raise ModeError(
            f"No station called '{name}' on this dial. Try one of:\n{stations}"
        )
    return modes[name]


def language_block(lang: str) -> str:
    if lang not in _LANGUAGE_BLOCKS:
        raise ModeError(
            f"Unknown language '{lang}' — pick from: {', '.join(LANGUAGES)}"
        )
    return _LANGUAGE_BLOCKS[lang]
