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
) -> None:
    """Broadcast a spoken guided tour of a repo."""
    from reporadio.config import MissingGroqKeyError, require_groq_key

    try:
        require_groq_key()
    except MissingGroqKeyError as err:
        console.print(f"[red]{err}[/]")
        raise typer.Exit(1)

    from reporadio.ingest.fetcher import IngestError
    from reporadio.session.broadcaster import Broadcaster
    from reporadio.show.script import ScriptError
    from reporadio.voice.player import NullPlayer, Player, PlayerError
    from reporadio.voice.tts import TTSError, get_engine

    tts_engine = get_engine(engine, voice, console)
    try:
        player = NullPlayer() if mute else Player()
    except PlayerError as err:
        console.print(f"[yellow]{err}[/]\n[dim]Going mute for this show.[/]")
        player = NullPlayer()

    try:
        Broadcaster(console, tts_engine, player).run(
            url, max_tokens=max_tokens, use_cache=not no_cache
        )
    except (IngestError, ScriptError, TTSError) as err:
        console.print(f"[red]📻 Station's off the air — {err}[/]")
        raise typer.Exit(1)
