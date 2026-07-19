# 📻 RepoRadio

> **Your code is now on air.** Paste any GitHub repo URL — an AI radio host
> explains (or roasts) the codebase out loud. Interrupt it with your voice,
> ask anything.

🚧 **v0.1.0 — scaffold.** The spoken pipeline is being built. Follow along:
`../PHASES.md` has the full build plan.

## Quickstart (dev)

```bash
uv sync
cp .env.example .env   # paste your free Groq key (needed from v0.1)
uv run reporadio tour https://github.com/pallets/flask
```

## Stations (coming)

| Freq | Station | Vibe |
|---|---|---|
| 88.1 | Standard | Professional guided tour |
| 95.7 | Casual | Chill friend over chai |
| 101.5 | Fun / Roast | Comedy roast — code, never coder |
| 106.3 | Desi FM | "Haan G! Repo analyze kar lia…" 🇵🇰 |

MIT · built on gitingest, Groq free tier, ChromaDB, Kokoro
