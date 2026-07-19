"""RepoRadio CLI — tour / (later: roast, ask, serve, versions)."""

import typer
from rich.console import Console

from reporadio import __version__

app = typer.Typer(
    name="reporadio",
    help="📻 RepoRadio — talk to any GitHub repo. Out loud.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"reporadio {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Your code is now on air."""


@app.command()
def tour(
    url: str = typer.Argument(..., help="GitHub repo URL to tour"),
    engine: str = typer.Option(
        "auto", "--engine", help="TTS engine: auto | kokoro | edge"
    ),
    voice: str = typer.Option(None, "--voice", help="Voice name for the engine"),
    mute: bool = typer.Option(
        False, "--mute", help="No audio — print the show transcript only"
    ),
    max_tokens: int = typer.Option(
        8000, "--max-tokens",
        help="Digest token budget (Groq free tier fits ~8k comfortably)",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Re-ingest, skip cache"),
    no_mic: bool = typer.Option(
        False, "--no-mic", help="Broadcast only — don't open the caller line"
    ),
) -> None:
    """Broadcast a spoken guided tour of a repo. Talk to interrupt the host."""
    _require_key_or_exit()

    from reporadio.ingest.fetcher import IngestError
    from reporadio.session.broadcaster import Broadcaster
    from reporadio.show.script import ScriptError
    from reporadio.voice.tts import TTSError, get_engine

    tts_engine = get_engine(engine, voice, console)
    player = _make_player(mute)

    try:
        Broadcaster(
            console, tts_engine, player, mic_enabled=not (no_mic or mute)
        ).run(url, max_tokens=max_tokens, use_cache=not no_cache)
    except (IngestError, ScriptError, TTSError) as err:
        console.print(f"[red]📻 Station's off the air — {err}[/]")
        raise typer.Exit(1)


@app.command()
def ask(
    url: str = typer.Argument(..., help="GitHub repo URL"),
    question: str = typer.Argument(..., help="Your question about the repo"),
    mute: bool = typer.Option(False, "--mute", help="Print the answer, don't speak it"),
    engine: str = typer.Option("auto", "--engine", help="TTS engine: auto | kokoro | edge"),
    voice: str = typer.Option(None, "--voice", help="Voice name for the engine"),
    max_tokens: int = typer.Option(8000, "--max-tokens", help="Digest token budget"),
) -> None:
    """Call the station without a mic: ask one question, get a spoken answer."""
    _require_key_or_exit()

    from reporadio.index.store import build_index_async
    from reporadio.ingest.fetcher import IngestError, fetch
    from reporadio.session.caller import answer_question
    from reporadio.session.memory import SessionMemory
    from reporadio.voice.tts import TTSError, get_engine

    try:
        with console.status("📡 Tuning in — ingesting the repo…"):
            digest = fetch(url, max_tokens=max_tokens)
        index = build_index_async(digest)
        if not index.ready.is_set():
            with console.status("🗂 Filing the repo into the archive (indexing)…"):
                index.ready.wait()
        with console.status("🎙 The host is checking the code…"):
            qa = answer_question(question, index, digest, SessionMemory())
    except (IngestError, TTSError) as err:
        console.print(f"[red]📻 Station's off the air — {err}[/]")
        raise typer.Exit(1)

    console.print(f"\n[bold green]📞 You:[/] [italic]{qa.question}[/]")
    console.print(f"[bold yellow]🎙 Host:[/] {qa.answer}")
    if qa.files:
        console.print(f"[dim]   (from: {', '.join(qa.files[:4])})[/]")

    if not mute:
        player = _make_player(mute=False)
        try:
            player.enqueue(get_engine(engine, voice, console).synth(qa.answer))
            player.wait()
        finally:
            player.close()


def _require_key_or_exit() -> None:
    from reporadio.config import MissingGroqKeyError, require_groq_key

    try:
        require_groq_key()
    except MissingGroqKeyError as err:
        console.print(f"[red]{err}[/]")
        raise typer.Exit(1)


def _make_player(mute: bool):
    from reporadio.voice.player import NullPlayer, Player, PlayerError

    if mute:
        return NullPlayer()
    try:
        return Player()
    except PlayerError as err:
        console.print(f"[yellow]{err}[/]\n[dim]Going mute for this show.[/]")
        return NullPlayer()
