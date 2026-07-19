"""RepoRadio CLI — tour / (later: roast, ask, serve, versions)."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

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
) -> None:
    """Broadcast a guided tour of a repo (pipeline lands in v0.1)."""
    banner = Text()
    banner.append("● ON AIR", style="bold red")
    banner.append("  ·  88.1 Tour FM\n\n", style="dim")
    banner.append("Today's repo: ", style="bold")
    banner.append(url, style="bold yellow")
    banner.append(
        "\n\nThe host is still setting up the studio — "
        "the spoken tour arrives in v0.1.",
        style="dim italic",
    )
    console.print(Panel.fit(banner, border_style="yellow", title="📻 REPORADIO"))
