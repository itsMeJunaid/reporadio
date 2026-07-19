# 📻 RepoRadio

> **Your code is now on air.** Paste any GitHub repo URL — an AI radio host
> explains (or roasts) the codebase out loud. Interrupt it with your voice,
> ask anything.

**v0.1.0 — the pipeline is live.** `reporadio tour <url>` ingests a repo,
writes a radio show about it with Groq, and speaks it — streaming, segment by
segment. Voice Q&A (interrupt the host) lands in v0.2.

## Quickstart (dev)

```bash
uv sync
cp .env.example .env   # paste your free Groq key from console.groq.com
uv run reporadio tour https://github.com/fastapi/typer
```

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
