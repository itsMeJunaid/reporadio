# 📻 RepoRadio

> **Your code is now on air.** Paste any GitHub repo URL — an AI radio host
> explains (or roasts) the codebase out loud. Interrupt it with your voice,
> ask anything.

**v0.2.0 — the caller line is open.** `reporadio tour <url>` speaks a guided
tour of any repo — and now you can **interrupt the host with your voice**:
Silero VAD cuts the TTS the instant you talk, Groq Whisper transcribes you,
and the host answers from a ChromaDB index of the actual code, then resumes
the show right where it stopped.

## Quickstart (dev)

```bash
uv sync
cp .env.example .env   # paste your free Groq key from console.groq.com
uv run reporadio tour https://github.com/fastapi/typer   # talk to interrupt!
uv run reporadio ask  https://github.com/fastapi/typer "where is the CLI defined?"
```

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
