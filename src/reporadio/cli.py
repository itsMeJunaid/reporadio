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


def _broadcast(
    url: str, mode_name: str, lang: str | None, engine: str | None,
    voice: str | None, mute: bool, max_tokens: int, no_cache: bool, no_mic: bool,
    at_commit: str | None = None, changelog: bool = False,
) -> None:
    _require_key_or_exit()

    from reporadio.ingest.fetcher import IngestError
    from reporadio.session.broadcaster import Broadcaster, ChangelogError
    from reporadio.show.modes import ModeError, get_mode, language_block
    from reporadio.show.script import ScriptError
    from reporadio.voice.tts import TTSError, get_engine

    try:
        mode = get_mode(mode_name)
        language_block(lang or mode.language)  # validate early
    except ModeError as err:
        console.print(f"[red]📻 {err}[/]")
        raise typer.Exit(1)

    tts_engine = get_engine(
        engine or mode.voice.engine, voice or mode.voice.name, console
    )
    player = _make_player(mute)
    caster = Broadcaster(
        console, tts_engine, player, mode=mode, lang=lang,
        mic_enabled=not (no_mic or mute),
    )

    try:
        if changelog:
            caster.run_changelog(url, max_tokens=max_tokens)
        else:
            caster.run(
                url, max_tokens=max_tokens, use_cache=not no_cache,
                at_commit=at_commit,
            )
    except ChangelogError as err:
        console.print(f"[yellow]📻 {err}[/]")
        raise typer.Exit(1)
    except (IngestError, ScriptError, TTSError) as err:
        console.print(f"[red]📻 Station's off the air — {err}[/]")
        raise typer.Exit(1)


@app.command()
def tour(
    url: str = typer.Argument(..., help="GitHub repo URL to tour"),
    mode: str = typer.Option(
        "standard", "--mode", "-m",
        help="Station: standard | casual | fun_roast | desi",
    ),
    lang: str = typer.Option(
        None, "--lang", "-l", help="en | ur | roman | mix (default: mode's own)"
    ),
    engine: str = typer.Option(
        None, "--engine", help="Override TTS engine: auto | kokoro | edge"
    ),
    voice: str = typer.Option(None, "--voice", help="Override voice name"),
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
    at: str = typer.Option(
        None, "--at", help="Time-travel: tour a previously analyzed commit"
    ),
) -> None:
    """Broadcast a spoken tour of a repo. Talk to interrupt the host."""
    _broadcast(
        url, mode, lang, engine, voice, mute, max_tokens, no_cache, no_mic,
        at_commit=at,
    )


@app.command()
def roast(
    url: str = typer.Argument(..., help="GitHub repo URL to roast 🔥"),
    lang: str = typer.Option(None, "--lang", "-l", help="en | ur | roman | mix"),
    engine: str = typer.Option(None, "--engine", help="Override TTS engine"),
    voice: str = typer.Option(None, "--voice", help="Override voice name"),
    mute: bool = typer.Option(False, "--mute", help="Transcript only"),
    max_tokens: int = typer.Option(8000, "--max-tokens", help="Digest token budget"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Re-ingest, skip cache"),
    no_mic: bool = typer.Option(False, "--no-mic", help="No caller line"),
) -> None:
    """Tune straight to Roast FM — the code gets cooked, live on air."""
    _broadcast(url, "fun_roast", lang, engine, voice, mute, max_tokens, no_cache, no_mic)


@app.command()
def changelog(
    url: str = typer.Argument(..., help="GitHub repo URL"),
    mode: str = typer.Option("standard", "--mode", "-m", help="Station personality"),
    lang: str = typer.Option(None, "--lang", "-l", help="en | ur | roman | mix"),
    engine: str = typer.Option(None, "--engine", help="Override TTS engine"),
    voice: str = typer.Option(None, "--voice", help="Override voice name"),
    mute: bool = typer.Option(False, "--mute", help="Transcript only"),
    max_tokens: int = typer.Option(8000, "--max-tokens", help="Digest token budget"),
    no_mic: bool = typer.Option(False, "--no-mic", help="No caller line"),
) -> None:
    """Broadcast what changed between the last two analyzed versions."""
    _broadcast(
        url, mode, lang, engine, voice, mute, max_tokens,
        no_cache=False, no_mic=no_mic, changelog=True,
    )


@app.command()
def versions(
    url: str = typer.Argument(..., help="GitHub repo URL"),
) -> None:
    """The archive: every analyzed version of this repo."""
    from rich.table import Table

    from reporadio.ingest.fetcher import IngestError, repo_name
    from reporadio.versions import registry

    try:
        name = repo_name(url)
    except IngestError as err:
        console.print(f"[red]📻 {err}[/]")
        raise typer.Exit(1)

    rows = registry.list_versions(name)
    if not rows:
        console.print(
            f"[yellow]📼 Nothing in the archive for {name} yet — "
            "run a tour first: reporadio tour <url>[/]"
        )
        raise typer.Exit(0)

    table = Table(title=f"📼 {name} — analyzed versions", border_style="yellow")
    table.add_column("#", style="dim")
    table.add_column("Commit", style="bold yellow")
    table.add_column("Analyzed", style="dim")
    table.add_column("Files", justify="right")
    table.add_column("~Tokens", justify="right")
    table.add_column("Languages")
    for i, v in enumerate(rows, 1):
        table.add_row(
            str(i), v.commit[:10], v.analyzed_at,
            str(v.file_count), f"{v.token_count:,}", v.languages,
        )
    console.print(table)
    console.print(
        "[dim]Time-travel:  reporadio tour <url> --at <commit>   ·   "
        "What's new:  reporadio changelog <url>[/]"
    )


@app.command()
def serve(
    port: int = typer.Option(8181, "--port", "-p", help="Studio port"),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open a tab"),
) -> None:
    """Open the studio — the tuner dashboard in your browser."""
    _require_key_or_exit()
    from reporadio.web.app import serve as run_studio

    console.print(
        f"[bold yellow]📻 Studio on air:[/] http://{host}:{port}  "
        "[dim](Ctrl+C to sign off)[/]"
    )
    run_studio(host=host, port=port, open_browser=not no_browser)


@app.command()
def stations() -> None:
    """What's on the dial."""
    from rich.table import Table

    from reporadio.show.modes import load_modes

    table = Table(title="📻 REPORADIO — on the dial", border_style="yellow")
    table.add_column("Freq", style="bold yellow")
    table.add_column("Station", style="bold")
    table.add_column("Vibe")
    table.add_column("Voice", style="dim")
    for m in load_modes().values():
        table.add_row(m.freq, m.key, m.title, f"{m.voice.engine} · {m.voice.name}")
    console.print(table)
    console.print(
        "[dim]Tune in:  reporadio tour <url> --mode desi   ·   reporadio roast <url>[/]"
    )


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
