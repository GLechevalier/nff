"""nff test — placeholder for upcoming test features."""

from __future__ import annotations

import sys

import click
from rich.console import Console

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_REPO_URL = "https://github.com/GLechevalier/nff"


@click.command()
def test() -> None:
    """Run hardware/firmware tests (coming soon)."""
    console.print()
    console.print(
        "  [bold yellow]⚗[/bold yellow]  [bold]nff test[/bold] — incoming feature, "
        "currently in development."
    )
    console.print()
    console.print(
        "  Show your support by starring the repo: "
        f"[bold cyan]{_REPO_URL}[/bold cyan]"
    )
    console.print()
