"""nff install-deps — install the active build backend's toolchain."""

import click
from rich.console import Console

from nff.tools import installer, toolchain

console = Console()


@click.command("install-deps")
@click.option("--force", is_flag=True, help="Re-install even if already present")
def install_deps(force):
    """Install the build toolchain nff needs (arduino-cli or PlatformIO, per the
    configured backend)."""
    if toolchain.active_backend() == "platformio":
        from nff.tools.backends import platformio as pio
        console.print("[bold]Installing PlatformIO…[/bold]")
        ok, msg = pio.ensure_toolchain(emit=lambda l: console.print(f"  {l}"))
        if not ok:
            raise click.ClickException(f"Failed to install PlatformIO: {msg}")
        console.print(f"[green]PlatformIO ready[/green] ({pio.platformio_version()})")
        return
    console.print("[bold]Installing arduino-cli…[/bold]")
    try:
        exe = installer.install(force=force)
        console.print(f"[green]arduino-cli installed at {exe}[/green]")
    except Exception as exc:
        raise click.ClickException(f"Failed to install arduino-cli: {exc}")
