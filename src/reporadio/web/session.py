"""One browser connection = one WebSession. A thin wrapper around the same core
the CLI uses — fetcher, index, show/script, session/caller, voice/tts, voice/vad —
that emits protocol events instead of drawing a terminal.

Live agent mode: the browser streams its mic continuously; the SAME Silero VAD
machinery the CLI uses (vad.Mic.process_chunk) runs server-side on that stream,
so barge-in works exactly like the terminal: speak → host stops → answer → resume."""

from __future__ import annotations

import asyncio
import base64
import threading
import time

import numpy as np

from reporadio.web.events import event

CHUNK_SAMPLES = 12000  # 0.5s @ 24kHz per audio_chunk
VAD_BLOCK = 512        # silero wants exact 512-sample blocks @16k


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
        self._thread: threading.Thread | None = None
        self._t0 = 0.0
        self.digest = None
        self.index = None
        self.memory = None
        self.engine = None
        self.mode = None
        self.lang = "en"
        # live agent mode
        self._mic = None           # vad.Mic driven manually via process_chunk
        self._vad_buf = np.zeros(0, dtype=np.float32)
        self._answering = threading.Event()

    # ------------------------------------------------------------- plumbing

    def emit(self, type_: str, **payload) -> None:
        self.loop.call_soon_threadsafe(self.events.put_nowait, event(type_, **payload))

    def _finish(self) -> None:
        self.loop.call_soon_threadsafe(self.events.put_nowait, None)

    def close(self) -> None:
        self.stopped.set()
        self.paused.clear()

    # ------------------------------------------------------------- broadcast

    def tune_in(self, url: str, mode_name: str, lang: str | None) -> None:
        if self._thread and self._thread.is_alive():
            self.emit("error", message="Already on air — refresh to tune a new repo.")
            return
        self._thread = threading.Thread(
            target=self._pipeline, args=(url, mode_name, lang), daemon=True
        )
        self._thread.start()

    def _explorer_paths(self, digest) -> list[dict]:
        """File list for the repo explorer box: every parsed file + kept flag."""
        sizes = digest.sizes or {p: len(t) for p, t in digest.files.items()}
        kept = set(digest.files)
        return [
            {"path": p, "size": n, "kept": p in kept}
            for p, n in sorted(sizes.items())[:600]
        ]

    def _pipeline(self, url: str, mode_name: str, lang: str | None) -> None:
        try:
            from reporadio.index.store import build_index_async
            from reporadio.ingest import fetcher
            from reporadio.session.memory import SessionMemory
            from reporadio.show import script as show_script
            from reporadio.show.modes import get_mode, language_block
            from reporadio.voice.tts import get_engine

            self._t0 = time.monotonic()
            self.mode = get_mode(mode_name)
            self.lang = lang or self.mode.language
            language_block(self.lang)  # validate

            self.emit("status", stage="ingest", detail=f"tuning in to {url}…")
            self.digest = fetcher.fetch(url)
            d = self.digest
            self.emit(
                "status", stage="index",
                detail=f"{d.name} @ {d.commit[:10]} — filing {len(d.files)} files…",
            )
            self.index = build_index_async(d)
            self.memory = SessionMemory()

            self.emit("status", stage="context", detail="the host is writing the show…")
            self.engine = get_engine(self.mode.voice.engine, self.mode.voice.name)

            self.emit(
                "ready",
                repo=d.name, commit=d.commit[:10], files=len(d.files),
                tokens=d.token_estimate, mode=self.mode.key, freq=self.mode.freq,
                voice=f"{self.engine.name} · {self.mode.voice.name}",
                greeting=self.mode.greeting,
                tree=d.tree[:12000],
                paths=self._explorer_paths(d),
            )

            if self.mode.greeting and not self.stopped.is_set():
                self.emit("transcript_line", who="host", text=self.mode.greeting)
                self._speak(self.mode.greeting)

            extra = ""
            if self.mode.prompt == "fun_roast":
                commits = fetcher.fetch_commit_messages(d.name)
                if commits:
                    extra = "RECENT COMMIT MESSAGES (roast material):\n" + "\n".join(
                        f"- {m}" for m in commits
                    )

            n = 0
            for seg in show_script.generate_segments(
                d, prompt_name=self.mode.prompt, temperature=self.mode.temperature,
                lang=self.lang, extra_context=extra,
            ):
                if self.stopped.is_set():
                    return
                n += 1
                self.emit("segment_start", n=n, title=seg.title)
                self.emit("transcript_line", who="host", text=seg.spoken_text)
                self._speak(seg.spoken_text)

            while self._answering.is_set() and not self.stopped.is_set():
                time.sleep(0.1)  # let a late caller answer finish before sign-off
            self.emit("status", stage="off_air", detail=f"that's the show — {n} segments")
        except Exception as err:  # surface anything to the studio
            self.emit("error", message=f"Station's off the air — {err}")
        finally:
            self._finish()

    def _speak(self, text: str, ignore_pause: bool = False) -> None:
        audio = self.engine.synth(text)
        samples = audio.samples
        total = len(samples)
        for start in range(0, total, CHUNK_SAMPLES):
            while self.paused.is_set() and not ignore_pause and not self.stopped.is_set():
                time.sleep(0.05)
            if self.stopped.is_set():
                return
            if self.skip.is_set() and not ignore_pause:
                self.skip.clear()
                self.emit("status", stage="flush", detail="skipped")
                return
            chunk = samples[start:start + CHUNK_SAMPLES]
            self.emit(
                "audio_chunk",
                data=_b64_int16(chunk),
                samplerate=audio.samplerate,
                last=start + CHUNK_SAMPLES >= total,
            )

    # ------------------------------------------------------------- live agent mode

    def set_mic(self, live: bool) -> None:
        if live and self._mic is None:
            try:
                from reporadio.voice.vad import Mic

                self._mic = Mic(on_speech=self._on_speech)  # never .start()ed:
                self._vad_buf = np.zeros(0, dtype=np.float32)  # we feed it ourselves
                self.emit("status", stage="on_air",
                          detail="🔴 live — just talk, the host will yield")
            except Exception as err:
                self.emit("error", message=f"Couldn't arm the caller line — {err}")
        elif not live and self._mic is not None:
            self._mic = None
            self._vad_buf = np.zeros(0, dtype=np.float32)
            self.emit("status", stage="on_air", detail="caller line closed")

    def _on_speech(self) -> None:
        """VAD heard the caller start talking — barge in NOW."""
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

        # push-to-talk fallback (no server VAD armed)
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

    def _answer(self, utterance) -> None:
        try:
            if utterance is None or len(utterance) < 4800:  # <0.3s = blip
                return
            if self.index is None:
                self.emit("error", message="Tune in to a repo before calling the station.")
                return
            from reporadio.session.caller import answer_question
            from reporadio.voice.stt import transcribe

            question = transcribe(utterance)
            if not question:
                return
            self.emit("transcript_line", who="you", text=question)
            qa = answer_question(
                question, self.index, self.digest, self.memory, lang=self.lang
            )
            self.emit("transcript_line", who="host", text=qa.answer, files=qa.files[:4])
            self._speak(qa.answer, ignore_pause=True)
        except Exception as err:
            self.emit("error", message=f"Lost the caller — {err}")
        finally:
            self._answering.clear()
            self.paused.clear()
            self.emit("status", stage="on_air", detail="back to the show")
