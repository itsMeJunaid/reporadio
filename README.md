<div align="center">

# 📻 RepoRadio

### **Your code is now on air.**

*Paste any GitHub repo — a voice AI that's read the whole thing talks to you about it.
Ask anything, out loud. It stops when you speak. It roasts on request.*

[![Python](https://img.shields.io/badge/python-3.11+-FFB03A?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-A8E05F?style=flat-square)](LICENSE)
[![Groq](https://img.shields.io/badge/LLM-Groq%20·%20free%20tier-FF4B4B?style=flat-square)](https://console.groq.com)
[![TTS](https://img.shields.io/badge/voice-100%25%20local%20(Kokoro)-5FD3C4?style=flat-square)](#-voices)
[![Cost](https://img.shields.io/badge/running%20cost-%240-A8E05F?style=flat-square)](#-the-stack)

</div>

---

```
📞 you   hey, what's this repo all about?
🎙 host  This is RepoRadio — paste a GitHub repo URL and an AI radio host explains
         the codebase out loud. You go live, just talk, and it answers from the
         actual code.
📞 you   give me just one sentence.
🎙 host  Talk to any GitHub repo, out loud.
📞 you   [clicks ✦ ask on tests/test_smoke.py]
🎙 host  That's the smoke-test file — my favorite part is test_tour_without_key_
         is_friendly: it makes sure the app stays polite when your API key is missing.
```

## ✨ What it does

| | |
|---|---|
| 🎛 **The Studio** | A browser dashboard: 3D particle visualizer, live transcript, repo file explorer, radio-tuning animations |
| 🔴 **Live agent mode** | Hit **GO LIVE** and just talk — server-side Silero VAD barge-in: the host stops mid-word when you speak, answers from the code, and waits for your next question |
| 📁 **Click any file** | Select a file → it's "in focus" for your questions · hover **✦ ask** → spoken walkthrough · stay quiet and the host offers: *"I see you've got cli dot py open — want the quick story?"* |
| 📡 **Three stations** | `88.1 standard` (crisp) · `95.7 casual` (code over chai) · `101.5 roast` 🔥 (brutally honest — roasts the code, never the coder) |
| 🎙 **The classic tour** | Press ▶ for a full guided radio tour: entry point → core flow → how data moves → where to start reading |
| 📼 **Version archive** | Every analysis is archived per commit — `changelog` broadcasts *what changed* as a spoken episode, `--at <commit>` time-travels |
| 🧠 **Grounded answers** | RAG over the real code (ChromaDB + bge-small). Doesn't know? It says so honestly — no invented files, ever |

## 🚀 Quickstart

**You need:** Python 3.11+ · a free [Groq API key](https://console.groq.com) (no card) · a mic (for live mode)

### With [uv](https://docs.astral.sh/uv/) — recommended

```bash
git clone https://github.com/itsMeJunaid/reporadio && cd reporadio
uv sync
cp .env.example .env        # paste your GROQ_API_KEY inside
uv run reporadio serve      # 🎛 the studio opens in your browser
```

### With plain pip

```bash
git clone https://github.com/itsMeJunaid/reporadio && cd reporadio
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt    # 1) download the dependencies
pip install -e .                   # 2) install reporadio itself
cp .env.example .env               # 3) add your GROQ_API_KEY
reporadio serve                    # 4) on air 📻
```

## 🎛 Using the Studio

1. **Paste a repo URL** and hit **TUNE IN** — enjoy the radio-seek animation while it ingests, indexes, and reads the code (`INGEST → INDEX → CONTEXT → READY`)
2. **Pick a station** — the whole studio re-themes to the mood
3. **GO LIVE** 🔴 — the host greets you: *"I've read this repo end to end. What would you like to know?"*
4. **Just talk.** No buttons. Speak → it stops and listens. Stop → it answers in a sentence or two. Interrupt it any time — mid-word is fine
5. **Explore files** — click one to put it in focus, hover **✦ ask** for a spoken walkthrough, or ask *"what does this file do?"* while it's selected
6. **▶** plays the classic full tour · **⏭** skips/shuts him up · **⏸** pauses

> 🎧 Echo-cancellation is on, so open speakers work — headphones are still cleaner.

## ⌨️ CLI reference

```bash
reporadio serve                             # the browser studio
reporadio tour  <repo-url>                  # spoken guided tour (talk to interrupt)
reporadio tour  <repo-url> --mode casual    # pick the mood
reporadio roast <repo-url>                  # 🔥 straight to Roast FM
reporadio ask   <repo-url> "where is X?"    # one spoken answer, no mic needed
reporadio stations                          # what's on the dial
reporadio versions  <repo-url>             # 📼 every analyzed version
reporadio changelog <repo-url>             # broadcast what changed between versions
reporadio tour <repo-url> --at <commit>    # ⏪ time-travel an old snapshot
```

Useful flags: `--mute` (transcript only) · `--no-mic` · `--engine kokoro|edge` · `--voice <name>` · `--max-tokens` (digest budget, default 8k — sized for Groq's free tier) · `--no-cache`

## 🔊 Voices

Works out of the box with **edge-tts** (online). For **fully local, faster** speech,
drop two files from the [kokoro-onnx releases](https://github.com/thewh1teagle/kokoro-onnx/releases) into `~/.reporadio/kokoro/`:

```
~/.reporadio/kokoro/
├── kokoro-v1.0.onnx    (~310 MB)
└── voices-v1.0.bin     (~27 MB)
```

That's it — `auto` picks Kokoro the moment the files exist. Default host voice: `af_heart`.

## ⚙️ How it works

```
TUNE IN   repo URL ─→ gitingest ─→ smart-trimmed digest (README > core > docs)
                              └──→ ChromaDB index (bge-small, per repo@commit)
GO LIVE   your mic ─→ WebSocket ─→ Silero VAD (server) ─→ barge-in: host yields
                                        └─→ Whisper STT ─→ RAG ─→ Groq llama-3.3-70b
ANSWER    1–2 spoken sentences ─→ Kokoro TTS ─→ gapless audio to your browser
```

Everything streams: the show starts talking while later segments are still being
written. CLI and web share the same core — the web layer only translates events.

## 🛠 The stack

| Layer | Tech | Cost |
|---|---|---|
| LLM | Groq · llama-3.3-70b | free tier |
| Speech-to-text | Groq · whisper-large-v3-turbo | free tier |
| Text-to-speech | Kokoro (local) · edge-tts fallback | free |
| Barge-in | Silero VAD via onnxruntime (no torch!) | free |
| RAG | ChromaDB + fastembed bge-small | free, local |
| Ingestion | gitingest | free |
| Server / UI | FastAPI + WebSocket · vanilla JS (zero JS deps) | free |

**Total running cost: $0.** Bring your own free Groq key.

## 🩺 Troubleshooting

<details>
<summary><b>"Station's off the air — GROQ_API_KEY is missing"</b></summary>
Copy <code>.env.example</code> to <code>.env</code> and paste your free key from <a href="https://console.groq.com">console.groq.com</a>.
</details>

<details>
<summary><b>"Rate limit reached" (429)</b></summary>
Groq's free tier has a daily token budget. It resets on its own — come back in a few hours, or use <code>--max-tokens 4000</code> to stretch it.
</details>

<details>
<summary><b>"Repository not found" on a repo that exists</b></summary>
Renamed/moved repos redirect (e.g. <code>tiangolo/typer</code> → <code>fastapi/typer</code>) — use the repo's current URL.
</details>

<details>
<summary><b>The host keeps interrupting himself</b></summary>
Speaker sound leaking into the mic. Echo-cancellation handles most of it — if not, use headphones or lower the volume.
</details>

<details>
<summary><b>No audio device / mic errors on Linux</b></summary>
<code>sudo apt install libportaudio2</code> — or run with <code>--mute</code> / use the studio's transcript.
</details>

## 🔮 Roadmap

See [FUTURE.md](FUTURE.md) — PR-review radio, two-host podcast mode, and more.

---

<div align="center">

**MIT** · built on gitingest, Groq, ChromaDB, Kokoro, Silero
*Tour it. Roast it. Ship it.*

</div>
