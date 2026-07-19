# 📻 RepoRadio

> **Your code is now on air.** Paste any GitHub repo URL — an AI radio host
> explains (or roasts) the codebase out loud. Interrupt it with your voice,
> ask anything.

**v1.0.0 — the studio is open.** `reporadio serve` puts the whole station in
your browser: paste a repo, watch the needle sweep INGEST → INDEX → CONTEXT →
READY, pick a station (including **Desi FM** — *"Haan G! Repo analyze kar
lia"*), hear the show, and **hold the mic button to call in** — the host
answers from the actual code and the show resumes. All four stations, four
languages, versioned archive, changelog episodes — CLI and web share the same
core.

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
uv run reporadio serve                                        # 🎛 the browser studio
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
