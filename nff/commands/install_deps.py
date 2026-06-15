"""nff install-deps — download and install arduino-cli (and optionally wokwi-cli)."""

import click
from rich.console import Console

from nff.tools import installer

console = Console()


@click.command("install-deps")
@click.option("--force", is_flag=True, help="Re-install even if already present")
@click.option("--skip-wokwi", is_flag=True, help="Skip wokwi-cli installation")
def install_deps(force, skip_wokwi):
    """Install arduino-cli (and wokwi-cli) needed by nff."""
    console.print("[bold]Installing arduino-cli…[/bold]")
    try:
        exe = installer.install(force=force)
        console.print(f"[green]arduino-cli installed at {exe}[/green]")
    except Exception as exc:
        raise click.ClickException(f"Failed to install arduino-cli: {exc}")
