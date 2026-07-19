"""Orchestrates the show: ingest → streamed script → TTS queue → live display."""

from __future__ import annotations

import time

from rich.panel import Panel
from rich.live import Live
from rich.text import Text

from reporadio.ingest import fetcher
from reporadio.show import script as show_script


class Broadcaster:
    def __init__(self, console, engine, player, station: str = "88.1 Tour FM"):
        self.console = console
        self.engine = engine
        self.player = player
        self.station = station

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

    def run(
        self,
        url: str,
        max_tokens: int = 8000,
        use_cache: bool = True,
        prompt_name: str = "standard",
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

        first_audio: float | None = None
        count = 0
        header = self._header(digest.name, "…", "", "✍ the host is writing the show…")
        try:
            with Live(header, console=self.console, refresh_per_second=8) as live:
                for seg in show_script.generate_segments(digest, prompt_name=prompt_name):
                    count += 1
                    live.update(self._header(
                        digest.name, count, seg.title, "✍ synthesizing this segment…"
                    ))
                    live.console.print(
                        f"\n[bold yellow]— Segment {count}: {seg.title} —[/]"
                    )
                    live.console.print(f"[dim]{seg.spoken_text}[/]")
                    audio = self.engine.synth(seg.spoken_text)
                    if first_audio is None:
                        first_audio = time.monotonic() - t0
                    self.player.enqueue(audio)
                    live.update(self._header(
                        digest.name, count, seg.title, "🎙 on air — next segment incoming…"
                    ))
                live.update(self._header(
                    digest.name, count, "", "🎶 playing out the rest of the show…"
                ))
                self.player.wait()
        except KeyboardInterrupt:
            self.player.stop()
            self.console.print("\n[red]📻 Off air — caller hung up.[/]")
            return
        finally:
            self.player.close()

        total = time.monotonic() - t0
        stats = Text()
        stats.append("That's the show. ", style="bold")
        stats.append(
            f"{count} segments · first audio in {first_audio:.1f}s · "
            f"{total:.0f}s total — stay tuned.",
            style="dim",
        )
        self.console.print(Panel.fit(stats, border_style="green", title="📻 SIGN-OFF"))
