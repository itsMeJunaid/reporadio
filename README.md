# 📻 RepoRadio

> **Your code is now on air.** Paste any GitHub repo URL — an AI radio host
> explains (or roasts) the codebase out loud. Interrupt it with your voice,
> ask anything.

**v0.4.0 — the archive is open.** Four stations (tour, chai-chat, roast, and
**Desi FM** — *"Haan G! Repo analyze kar lia"*), voice interruptions answered
from the actual code — and now **versioning**: every analysis is archived,
`reporadio changelog` broadcasts what changed between versions, and
`--at <commit>` time-travels the tour to an older snapshot.

## Quickstart (dev)

```bash
uv sync
cp .env.example .env   # paste your free Groq key from console.groq.com
uv run reporadio stations                                # what's on the dial
uv run reporadio tour  https://github.com/fastapi/typer  # talk to interrupt!
uv run reporadio tour  https://github.com/fastapi/typer --mode desi
uv run reporadio roast https://github.com/fastapi/typer  # 🔥
uv run reporadio ask   https://github.com/fastapi/typer "where is the CLI defined?"
uv run reporadio versions  https://github.com/fastapi/typer   # the archive
uv run reporadio changelog https://github.com/fastapi/typer   # what's new, on air
```

Any mode in any language: `--lang en|ur|roman|mix` (e.g. the standard tour in
Roman Urdu: `--mode standard --lang roman`). Adding a station = one entry in
`show/modes.yaml` + one prompt file — zero code change.

> 🎧 **Use headphones for the live caller mode** — with open speakers the host
> hears himself through the mic and takes his own calls.

Useful flags: `--mute` (transcript only), `--engine kokoro|edge`, `--voice`,
`--max-tokens` (digest budget, default 8k — sized for Groq's free tier),
`--no-cache`.

**Voices:** works out of the box via edge-tts (needs internet). For fully local
TTS, drop `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the
[kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases)
into `~/.reporadio/kokoro/`.

## Stations (coming)

| Freq | Station | Vibe |
|---|---|---|
| 88.1 | Standard | Professional guided tour |
| 95.7 | Casual | Chill friend over chai |
| 101.5 | Fun / Roast | Comedy roast — code, never coder |
| 106.3 | Desi FM | "Haan G! Repo analyze kar lia…" 🇵🇰 |

MIT · built on gitingest, Groq free tier, ChromaDB, Kokoro
