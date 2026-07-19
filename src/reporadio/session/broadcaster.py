"""Orchestrates the show: ingest → index (background) → streamed script → TTS →
live display, with mic barge-in: interrupt → question → grounded answer → resume."""

from __future__ import annotations

import queue
import time

from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from reporadio.ingest import fetcher
from reporadio.session import caller as caller_flow
from reporadio.session.memory import SessionMemory
from reporadio.show import script as show_script


class Broadcaster:
    def __init__(
        self, console, engine, player, mode=None, lang: str | None = None,
        mic_enabled: bool = True,
    ):
        from reporadio.show.modes import get_mode

        self.console = console
        self.engine = engine
        self.player = player
        self.mode = mode or get_mode("standard")
        self.lang = lang or self.mode.language
        self.station = f"{self.mode.freq} · {self.mode.key}"
        self.mic_enabled = mic_enabled

    def _header(self, repo: str, seg_no: int | str, title: str, state: str) -> Panel:
        txt = Text()
        txt.append("● ON AIR", style="bold red")
        txt.append(f"  ·  {self.station}  ·  voice: {self.engine.name}\n\n", style="dim")
        txt.append("Today's repo: ", style="bold")
        txt.append(f"{repo}\n", style="bold yellow")
        txt.append(f"Segment {seg_no}", style="bold")
        if title:
            txt.append(f" — {title}", style="bold")
        txt.append(f"\n{state}", style="dim italic")
        return Panel(txt, border_style="yellow", title="📻 REPORADIO")

    def _start_mic(self, calls: queue.Queue):
        if not self.mic_enabled:
            return None
        try:
            from reporadio.voice.vad import Mic

            def on_speech() -> None:
                calls.put(self.player.interrupt())

            mic = Mic(on_speech)
            mic.start()
            self.console.print(
                "[dim]📞 Lines are open — just start talking to interrupt the host. "
                "(Use headphones, or the host will hear himself!)[/]"
            )
            return mic
        except Exception as err:
            self.console.print(f"[dim]📵 No caller line (mic unavailable: {err})[/]")
            return None

    def _handle_call(self, mic, calls, index, digest, memory, live, seg_ctx) -> None:
        try:
            leftovers = calls.get_nowait()
        except queue.Empty:
            return

        repo, seg_no, title = seg_ctx
        live.update(self._header(repo, seg_no, title, "📞 LIVE CALLER — listening…"))
        utt = mic.utterance(timeout=12)
        mic.pause()
        try:
            if utt is None:
                return
            live.update(self._header(repo, seg_no, title, "📞 caller on line — transcribing…"))
            from reporadio.voice.stt import transcribe

            question = transcribe(utt)
            if not question:
                return
            live.console.print(f"\n[bold green]📞 You:[/] [italic]{question}[/]")
            live.update(self._header(repo, seg_no, title, "🎙 checking the code…"))
            qa = caller_flow.answer_question(
                question, index, digest, memory, lang=self.lang
            )
            live.console.print(f"[bold yellow]🎙 Host:[/] [dim]{qa.answer}[/]")
            if qa.files:
                live.console.print(f"[dim]   (from: {', '.join(qa.files[:4])})[/]")
            self.player.enqueue(self.engine.synth(qa.answer))
        except Exception as err:
            live.console.print(f"[red]📞 Lost the caller — {err}[/]")
        finally:
            for audio in leftovers:  # resume the show exactly where it stopped
                self.player.enqueue(audio)
            self.player.wait()  # let the answer + resumed tail play before listening again
            if mic:
                mic.resume()
        live.update(self._header(repo, seg_no, title, "🎙 back to the tour…"))

    def run(
        self,
        url: str,
        max_tokens: int = 8000,
        use_cache: bool = True,
    ) -> None:
        t0 = time.monotonic()
        with self.console.status("📡 Tuning in — ingesting the repo…"):
            digest = fetcher.fetch(url, max_tokens=max_tokens, use_cache=use_cache)

        note = (
            f"[dim]Ingested [bold]{digest.name}[/bold] @ {digest.commit[:10]} — "
            f"{len(digest.files)} files, ~{digest.token_estimate:,} tokens"
        )
        if digest.dropped:
            note += f" ({len(digest.dropped)} large files trimmed)"
        self.console.print(note + "[/]")

        extra_context = ""
        if self.mode.prompt == "fun_roast":
            with self.console.status("🔥 Pulling the commit history — roast material…"):
                commits = fetcher.fetch_commit_messages(digest.name)
            if commits:
                extra_context = "RECENT COMMIT MESSAGES (roast material):\n" + "\n".join(
                    f"- {m}" for m in commits
                )
                self.console.print(
                    f"[dim]🔥 {len(commits)} commit messages loaded for the roast[/]"
                )

        from reporadio.index.store import build_index_async

        index = build_index_async(digest)  # embeds in the background while we talk
        memory = SessionMemory()
        calls: queue.Queue = queue.Queue()
        mic = self._start_mic(calls)

        first_audio: float | None = None
        count = 0
        title = ""
        header = self._header(digest.name, "…", "", "✍ the host is writing the show…")
        try:
            with Live(header, console=self.console, refresh_per_second=8) as live:
                if self.mode.greeting:
                    live.console.print(f"\n[bold yellow]🎙 Host:[/] {self.mode.greeting}")
                    self.player.enqueue(self.engine.synth(self.mode.greeting))
                    first_audio = time.monotonic() - t0
                for seg in show_script.generate_segments(
                    digest,
                    prompt_name=self.mode.prompt,
                    temperature=self.mode.temperature,
                    lang=self.lang,
                    extra_context=extra_context,
                ):
                    count += 1
                    title = seg.title
                    if mic:
                        self._handle_call(
                            mic, calls, index, digest, memory, live,
                            (digest.name, count, title),
                        )
                    live.update(self._header(
                        digest.name, count, title, "✍ synthesizing this segment…"
                    ))
                    live.console.print(f"\n[bold yellow]— Segment {count}: {title} —[/]")
                    live.console.print(f"[dim]{seg.spoken_text}[/]")
                    audio = self.engine.synth(seg.spoken_text)
                    if first_audio is None:
                        first_audio = time.monotonic() - t0
                    self.player.enqueue(audio)
                    live.update(self._header(
                        digest.name, count, title, "🎙 on air — next segment incoming…"
                    ))
                while True:  # play out the tail, still answering calls
                    if mic:
                        self._handle_call(
                            mic, calls, index, digest, memory, live,
                            (digest.name, count, title),
                        )
                    if self.player.idle() and calls.empty():
                        break
                    live.update(self._header(
                        digest.name, count, title, "🎶 playing out the rest of the show…"
                    ))
                    time.sleep(0.15)
        except KeyboardInterrupt:
            self.player.stop()
            self.console.print("\n[red]📻 Off air — caller hung up.[/]")
            return
        finally:
            if mic:
                mic.stop()
            self.player.close()

        total = time.monotonic() - t0
        stats = Text()
        stats.append("That's the show. ", style="bold")
        stats.append(
            f"{count} segments · {len(memory)} caller questions · "
            f"first audio in {first_audio:.1f}s · {total:.0f}s total — stay tuned.",
            style="dim",
        )
        self.console.print(Panel.fit(stats, border_style="green", title="📻 SIGN-OFF"))
