"""nff monitor — interactive serial monitor."""

from __future__ import annotations

import pathlib
import sys

if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

import click
from rich.console import Console
from rich.text import Text

from nff import config as cfg_module
from nff.tools.serial import SerialError, stream_lines

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_BANNER = "[bold cyan]nff monitor[/bold cyan]  [dim]—  Ctrl+C to exit[/dim]"


def _resolve_connection(
    port: str | None,
    baud: int | None,
) -> tuple[str, int]:
    """Return (port, baud), filling missing values from config.

    Exits with code 1 if the port cannot be resolved.
    """
    try:
        device = cfg_module.get_default_device()
    except cfg_module.ConfigError:
        device = {}

    resolved_port = port or device.get("port") or ""
    resolved_baud = baud or device.get("baud") or 9600

    if not resolved_port:
        console.print(
            "  [bold red]✗[/bold red] No port specified. "
            "Pass --port or run [bold]nff init[/bold] first."
        )
        sys.exit(1)

    return resolved_port, int(resolved_baud)


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

@click.command()
@click.option("--port", default=None, metavar="PORT",
              help="Serial port, e.g. COM3 or /dev/ttyUSB0. Falls back to config.")
@click.option("--baud", default=None, type=int,
              help="Baud rate. Falls back to config default (9600).")
@click.option("--timeout", "timeout_s", default=None, type=float, metavar="SECONDS",
              help="Stop after this many seconds instead of running indefinitely.")
def monitor(
    port: str | None,
    baud: int | None,
    timeout_s: float | None,
) -> None:
    """Open an interactive serial monitor for the connected board.

    Streams device output to the terminal in real time.
    Press Ctrl+C to exit cleanly.

    Port and baud rate default to the values stored by `nff init`.
    """
    resolved_port, resolved_baud = _resolve_connection(port, baud)

    console.print(_BANNER)
    console.print(
        f"  [bold]{resolved_port}[/bold]  "
        f"[dim]@[/dim]  [bold]{resolved_baud}[/bold] baud"
    )
    console.print("[dim]─[/dim]" * 60)

    try:
        for line in stream_lines(resolved_port, resolved_baud, timeout_s=timeout_s):
            # Colour lines that look like errors to make them stand out.
            if any(kw in line.lower() for kw in ("error", "exception", "fault", "panic")):
                console.print(Text(line, style="bold red"))
            elif any(kw in line.lower() for kw in ("warn", "warning")):
                console.print(Text(line, style="yellow"))
            else:
                console.print(line)
    except KeyboardInterrupt:
        console.print("\n[dim]─[/dim]" * 60)
        console.print("  [bold green]✓[/bold green] Monitor closed.")
    except SerialError as exc:
        console.print(f"\n  [bold red]✗[/bold red] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    monitor()
