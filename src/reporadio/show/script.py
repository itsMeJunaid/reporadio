"""Digest → streamed, validated tour segments from Groq (NDJSON, one retry)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

MODEL = "llama-3.3-70b-versatile"
PROMPTS_DIR = Path(__file__).parent / "prompts"


class ScriptError(RuntimeError):
    pass


class Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    spoken_text: str

    @field_validator("title", "spoken_text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v


def load_prompt(name: str = "standard") -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _parse_line(line: str) -> Segment | None:
    line = line.strip().strip("`").strip()
    if not line.startswith("{"):
        return None
    try:
        return Segment(**json.loads(line))
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _digest_message(digest) -> str:
    dropped = (
        f"\n(Note: these files were trimmed for size, don't guess their contents: "
        f"{', '.join(digest.dropped[:12])})" if digest.dropped else ""
    )
    return (
        f"REPO DIGEST — {digest.name} @ {digest.commit[:10]}\n\n"
        f"SUMMARY:\n{digest.summary}\n\nFILE TREE:\n{digest.tree}\n\n"
        f"FILES:\n{digest.content()}{dropped}\n\n"
        "OUTPUT FORMAT — STRICT:\n"
        "Reply with NDJSON only: one JSON object per line, nothing else.\n"
        'Each line: {"title": "short segment title", "spoken_text": "what the host says"}\n'
        "5 to 8 lines total. No markdown fences, no commentary, no blank lines."
    )


def generate_segments(
    digest,
    *,
    client=None,
    model: str = MODEL,
    prompt_name: str = "standard",
    temperature: float = 0.6,
    lang: str = "en",
    extra_context: str = "",
) -> Iterator[Segment]:
    """Yield Segments as the model streams them; one corrective retry on garbage."""
    if client is None:
        from groq import Groq

        from reporadio.config import require_groq_key

        client = Groq(api_key=require_groq_key())

    from reporadio.show.modes import language_block

    user_msg = _digest_message(digest)
    if extra_context:
        user_msg += f"\n\n{extra_context}"
    messages = [
        {"role": "system", "content": load_prompt(prompt_name) + language_block(lang)},
        {"role": "user", "content": user_msg},
    ]

    yielded = False
    for attempt in (1, 2):
        stream = client.chat.completions.create(
            model=model, messages=messages, stream=True, temperature=temperature
        )
        buf = ""
        raw = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            buf += delta
            raw += delta
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                seg = _parse_line(line)
                if seg:
                    yielded = True
                    yield seg
        seg = _parse_line(buf)
        if seg:
            yielded = True
            yield seg

        if yielded:
            return
        if attempt == 1:
            messages.append({"role": "assistant", "content": raw[:2000]})
            messages.append({
                "role": "user",
                "content": (
                    "That was not valid NDJSON. Reply again with ONLY one JSON "
                    'object per line, exactly {"title": ..., "spoken_text": ...}, '
                    "no other text of any kind."
                ),
            })

    raise ScriptError(
        "The host lost the script — model returned no valid segments after a retry."
    )
