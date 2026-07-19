"""One browser connection = one WebSession — a live conversational repo agent.

Conversation-first: tune_in just ingests + indexes. GO LIVE makes the agent
greet and ASK what the caller wants; from there it's turn-taking by Silero VAD
(the same machinery the CLI uses), with short spoken answers. The classic
segment show still exists behind the `tour` message. File selection feeds the
conversation: clicked files become FILE IN FOCUS, and a silent caller gets a
gentle nudge ("you're looking at cli dot py — want the story?")."""

from __future__ import annotations

import asyncio
import base64
import threading
import time

import numpy as np

from reporadio.web.events import event

CHUNK_SAMPLES = 12000   # 0.5s @ 24kHz per audio_chunk
VAD_BLOCK = 512         # silero wants exact 512-sample blocks @16k
VAD_START_MS = 240      # snappier turn-taking than the CLI defaults
VAD_END_MS = 600
IDLE_NUDGE_S = 7.0      # selected a file + stayed quiet → agent offers help
FOCUS_EXCERPT = 2800    # chars of the focused file we hand to the LLM


def _b64_int16(samples: np.ndarray) -> str:
    pcm = np.clip(samples, -1.0, 1.0)
    return base64.b64encode((pcm * 32767).astype("<i2").tobytes()).decode()


class WebSession:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.events: asyncio.Queue[dict | None] = asyncio.Queue()
        self.paused = threading.Event()
        self.skip = threading.Event()
        self.stopped = threading.Event()
        self._caller_chunks: list[np.ndarray] = []
        self._show_thread: threading.Thread | None = None
        self._t0 = 0.0
        self.digest = None
        self.index = None
        self.memory = None
        self.engine = None
        self.mode = None
        self.lang = "en"
        # live agent state
        self._mic = None
        self._vad_buf = np.zeros(0, dtype=np.float32)
        self._answering = threading.Event()
        self._greeted = False
        self._focus: str | None = None
        self._nudged: set[str] = set()
        self._nudge_timer: threading.Timer | None = None

    # ------------------------------------------------------------- plumbing

    def emit(self, type_: str, **payload) -> None:
        self.loop.call_soon_threadsafe(self.events.put_nowait, event(type_, **payload))

    def _finish(self) -> None:
        self.loop.call_soon_threadsafe(self.events.put_nowait, None)

    def close(self) -> None:
        self.stopped.set()
        self.paused.clear()
        if self._nudge_timer:
            self._nudge_timer.cancel()

    # ------------------------------------------------------------- tune in

    def tune_in(self, url: str, mode_name: str, lang: str | None) -> None:
        threading.Thread(
            target=self._prepare, args=(url, mode_name, lang), daemon=True
        ).start()

    def _explorer_paths(self, digest) -> list[dict]:
        sizes = digest.sizes or {p: len(t) for p, t in digest.files.items()}
        kept = set(digest.files)
        return [
            {"path": p, "size": n, "kept": p in kept}
            for p, n in sorted(sizes.items())[:600]
        ]

    def _prepare(self, url: str, mode_name: str, lang: str | None) -> None:
        try:
            from reporadio.index.store import build_index_async
            from reporadio.ingest import fetcher
            from reporadio.session.memory import SessionMemory
            from reporadio.show.modes import get_mode, language_block
            from reporadio.voice.tts import get_engine

            self._t0 = time.monotonic()
            self.mode = get_mode(mode_name)
            self.lang = lang or self.mode.language
            language_block(self.lang)

            self.emit("status", stage="ingest", detail=f"tuning in to {url}…")
            self.digest = fetcher.fetch(url)
            d = self.digest
            self.emit(
                "status", stage="index",
                detail=f"{d.name} @ {d.commit[:10]} — filing {len(d.files)} files…",
            )
            self.index = build_index_async(d)
            self.memory = SessionMemory()
            self.emit("status", stage="context", detail="agent is reading the code…")
            self.engine = get_engine(self.mode.voice.engine, self.mode.voice.name)
            self.engine.synth("mic check")  # warm the TTS model → lower first-word latency

            self.emit(
                "ready",
                repo=d.name, commit=d.commit[:10], files=len(d.files),
                tokens=d.token_estimate, mode=self.mode.key, freq=self.mode.freq,
                voice=f"{self.engine.name} · {self.mode.voice.name}",
                greeting=self.mode.greeting,
                tree=d.tree[:12000],
                paths=self._explorer_paths(d),
            )
            self.emit(
                "status", stage="on_air",
                detail="tuned — GO LIVE and just ask, or hit ▶ tour",
            )
        except Exception as err:
            self.emit("error", message=f"Station's off the air — {err}")

    # ------------------------------------------------------------- speech out

    def _say(self, text: str, files: list[str] | None = None,
             interruptible: bool = True) -> None:
        """Transcript line + spoken audio."""
        self.emit("transcript_line", who="host", text=text, files=files or [])
        audio = self.engine.synth(text)
        samples = audio.samples
        total = len(samples)
        for start in range(0, total, CHUNK_SAMPLES):
            while self.paused.is_set() and interruptible and not self.stopped.is_set():
                time.sleep(0.05)
            if self.stopped.is_set():
                return
            if self.skip.is_set() and interruptible:
                self.skip.clear()
                self.emit("status", stage="flush", detail="skipped")
                return
            self.emit(
                "audio_chunk",
                data=_b64_int16(samples[start:start + CHUNK_SAMPLES]),
                samplerate=audio.samplerate,
                last=start + CHUNK_SAMPLES >= total,
            )

    # ------------------------------------------------------------- live agent

    def set_mic(self, live: bool) -> None:
        if live and self._mic is None:
            try:
                from reporadio.voice.vad import Mic

                self._mic = Mic(
                    on_speech=self._on_speech,
                    start_ms=VAD_START_MS, end_ms=VAD_END_MS,
                )  # fed manually — never .start()ed
                self._vad_buf = np.zeros(0, dtype=np.float32)
                self.emit("status", stage="on_air",
                          detail="🔴 live — just talk, I'm listening")
                if not self._greeted and self.mode is not None:
                    self._greeted = True
                    threading.Thread(
                        target=self._say, args=(self.mode.greeting,),
                        daemon=True,
                    ).start()
            except Exception as err:
                self.emit("error", message=f"Couldn't arm the caller line — {err}")
        elif not live and self._mic is not None:
            self._mic = None
            self._vad_buf = np.zeros(0, dtype=np.float32)
            self.emit("status", stage="on_air", detail="caller line closed")

    def _on_speech(self) -> None:
        """VAD heard the caller — yield the floor instantly."""
        self._cancel_nudge()
        self.paused.set()
        self.emit("status", stage="flush", detail="caller barged in")
        self.emit("status", stage="listening", detail="listening…")

    def caller_chunk(self, b64data: str, end: bool) -> None:
        if self._mic is not None:
            if b64data and not self._answering.is_set():
                pcm = np.frombuffer(base64.b64decode(b64data), dtype="<i2")
                self._vad_buf = np.concatenate(
                    [self._vad_buf, pcm.astype(np.float32) / 32767.0]
                )
                while len(self._vad_buf) >= VAD_BLOCK:
                    self._mic.process_chunk(self._vad_buf[:VAD_BLOCK])
                    self._vad_buf = self._vad_buf[VAD_BLOCK:]
                utt = self._mic.utterance(timeout=0)
                if utt is not None:
                    self._answering.set()
                    self.emit("status", stage="thinking", detail="checking the code…")
                    threading.Thread(
                        target=self._answer, args=(utt,), daemon=True
                    ).start()
            return

        # push-to-talk fallback
        if b64data:
            pcm = np.frombuffer(base64.b64decode(b64data), dtype="<i2")
            self._caller_chunks.append(pcm.astype(np.float32) / 32767.0)
        if not end:
            self.paused.set()
            return
        utterance = (
            np.concatenate(self._caller_chunks) if self._caller_chunks else None
        )
        self._caller_chunks = []
        self._answering.set()
        threading.Thread(target=self._answer, args=(utterance,), daemon=True).start()

    def _fetch_raw(self, path: str) -> str | None:
        """Trimmed from the digest? Pull the single file from GitHub raw so a
        clicked file can ALWAYS be explained. Cached per session."""
        if not hasattr(self, "_raw_cache"):
            self._raw_cache: dict[str, str | None] = {}
        if path in self._raw_cache:
            return self._raw_cache[path]
        text = None
        try:
            from urllib.request import Request, urlopen

            url = f"https://raw.githubusercontent.com/{self.digest.name}/{self.digest.commit}/{path}"
            req = Request(url, headers={"User-Agent": "reporadio"})
            with urlopen(req, timeout=10) as resp:
                text = resp.read(FOCUS_EXCERPT * 4).decode("utf-8", "replace")
        except Exception:
            pass
        self._raw_cache[path] = text
        return text

    def _focus_context(self) -> str:
        if not self._focus or self.digest is None:
            return ""
        text = self.digest.files.get(self._focus) or self._fetch_raw(self._focus)
        excerpt = (
            f"\n{text[:FOCUS_EXCERPT]}" if text
            else " (couldn't load its contents — say so honestly)"
        )
        return f"FILE IN FOCUS — the caller has {self._focus} selected:{excerpt}"

    def _overview_context(self) -> str:
        d = self.digest
        return (
            f"REPO OVERVIEW MATERIAL:\n{d.summary}\n\nTREE (partial):\n{d.tree[:2400]}\n\n"
            f"STATION MOOD: {self.mode.title}"
        )

    def _answer(self, utterance) -> None:
        try:
            if utterance is None or len(utterance) < 4800:  # <0.3s = blip
                return
            if self.index is None:
                self.emit("error", message="Tune in to a repo before calling the station.")
                return
            from reporadio.session.caller import answer_question
            from reporadio.voice.stt import transcribe

            t0 = time.monotonic()
            question = transcribe(utterance)
            if not question:
                return
            self.emit("transcript_line", who="you", text=question)
            qa = answer_question(
                question, self.index, self.digest, self.memory, lang=self.lang,
                prompt_name="agent",
                extra_context="\n\n".join(
                    filter(None, [self._overview_context(), self._focus_context()])
                ),
            )
            self.emit("status", stage="on_air",
                      detail=f"answered in {time.monotonic() - t0:.1f}s")
            self._say(qa.answer, files=qa.files[:4], interruptible=False)
        except Exception as err:
            self.emit("error", message=f"Lost the caller — {err}")
        finally:
            self._answering.clear()
            self.paused.clear()

    # ------------------------------------------------------------- files

    def select_file(self, path: str) -> None:
        self._focus = path
        self._cancel_nudge()
        self.emit("status", stage="on_air", detail=f"in focus: {path}")
        if self._mic is not None and path not in self._nudged:
            self._nudge_timer = threading.Timer(IDLE_NUDGE_S, self._nudge, args=(path,))
            self._nudge_timer.daemon = True
            self._nudge_timer.start()

    def _cancel_nudge(self) -> None:
        if self._nudge_timer:
            self._nudge_timer.cancel()
            self._nudge_timer = None

    def _nudge(self, path: str) -> None:
        """Caller selected a file and went quiet — offer to explain it."""
        if (self._focus != path or self._answering.is_set()
                or self.paused.is_set() or self.stopped.is_set()):
            return
        self._nudged.add(path)
        name = path.rsplit("/", 1)[-1].replace("_", " underscore ").replace(".", " dot ")
        self._say(f"I see you've got {name} open — want the quick story on what it does?")

    def explain_file(self, path: str) -> None:
        self._focus = path
        self._cancel_nudge()
        self._nudged.add(path)
        self._answering.set()
        self.emit("status", stage="thinking", detail=f"reading {path}…")

        def _work() -> None:
            try:
                from reporadio.session.caller import answer_question

                qa = answer_question(
                    f"Walk me through {path} — what does this file do and what's "
                    "interesting in it?",
                    self.index, self.digest, self.memory, lang=self.lang,
                    prompt_name="agent",
                    extra_context=self._focus_context() or
                    f"FILE IN FOCUS: {path} (contents not in digest — use chunks)",
                )
                self.emit("transcript_line", who="you", text=f"[clicked ✦ explain {path}]")
                self._say(qa.answer, files=[path], interruptible=False)
            except Exception as err:
                self.emit("error", message=f"Couldn't read that one — {err}")
            finally:
                self._answering.clear()
                self.paused.clear()

        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------- classic tour

    def start_tour(self) -> None:
        if self.digest is None:
            self.emit("error", message="Tune in first — then I'll run the tour.")
            return
        if self._show_thread and self._show_thread.is_alive():
            return
        self._show_thread = threading.Thread(target=self._tour, daemon=True)
        self._show_thread.start()

    def _tour(self) -> None:
        try:
            from reporadio.ingest import fetcher
            from reporadio.show import script as show_script

            extra = ""
            if self.mode.prompt == "fun_roast":
                commits = fetcher.fetch_commit_messages(self.digest.name)
                if commits:
                    extra = "RECENT COMMIT MESSAGES (roast material):\n" + "\n".join(
                        f"- {m}" for m in commits
                    )
            n = 0
            for seg in show_script.generate_segments(
                self.digest, prompt_name=self.mode.prompt,
                temperature=self.mode.temperature, lang=self.lang,
                extra_context=extra,
            ):
                if self.stopped.is_set():
                    return
                n += 1
                self.emit("segment_start", n=n, title=seg.title)
                self._say(seg.spoken_text)
            self.emit("status", stage="on_air", detail=f"tour done — {n} segments. Ask away.")
        except Exception as err:
            self.emit("error", message=f"Tour fell off the air — {err}")
