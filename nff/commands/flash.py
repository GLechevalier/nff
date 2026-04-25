"""nff flash — compile and upload a sketch to the connected board."""

from __future__ import annotations

import pathlib
import sys

if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

from pathlib import Path

import click
from rich.console import Console

from nff import config as cfg_module
from nff.tools import toolchain

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_target(
    board: str | None,
    port: str | None,
) -> tuple[str, str]:
    """Return (fqbn, port), filling missing values from config.

    Exits with code 1 if either value cannot be resolved.
    """
    try:
        device = cfg_module.get_default_device()
    except cfg_module.ConfigError:
        device = {}

    fqbn = board or device.get("fqbn") or ""
    resolved_port = port or device.get("port") or ""

    missing = []
    if not fqbn:
        missing.append("board FQBN (use --board or run nff init)")
    if not resolved_port:
        missing.append("port (use --port or run nff init)")

    if missing:
        for m in missing:
            console.print(f"  [bold red]✗[/bold red] Missing {m}")
        sys.exit(1)

    return fqbn, resolved_port


def _resolve_sketch(path: Path) -> Path:
    """Return the sketch directory that arduino-cli should compile.

    Handles three cases:
    - A directory that is already a valid sketch folder.
    - A .ino file already inside a correctly-named parent directory.
    - A loose .ino file — copied to the default temp sketch directory.

    Note: multi-file sketches passed as a loose .ino will only include
    that single file. Pass the sketch directory for multi-file projects.

    Exits with code 1 on invalid input.
    """
    if path.is_dir():
        ino_files = list(path.glob("*.ino"))
        if not ino_files:
            console.print(
                f"  [bold red]✗[/bold red] No .ino file found in [bold]{path}[/bold]"
            )
            sys.exit(1)
        return path

    if path.suffix.lower() != ".ino":
        console.print(
            f"  [bold red]✗[/bold red] Expected a .ino file or sketch directory, "
            f"got: [bold]{path.name}[/bold]"
        )
        sys.exit(1)

    # If the file already lives in a correctly-named sketch directory, use it in place.
    if path.parent.name == path.stem:
        return path.parent

    # Loose .ino — write to the temp sketch directory.
    console.print(
        f"  [dim]Copying {path.name} → temp sketch dir "
        f"(multi-file sketches need a directory)[/dim]"
    )
    code = path.read_text(encoding="utf-8")
    return toolchain.write_sketch(code)


def _stream_phase(label: str, stream: toolchain.ProcessStream) -> None:
    """Print *label*, stream lines, then print pass/fail. Exits 1 on failure."""
    console.print(f"\n  {label}")
    for line in stream:
        if line.strip():
            console.print(f"    [dim]{line}[/dim]")

    if stream.returncode != 0:
        phase = label.split()[0].rstrip("…")
        console.print(
            f"\n  [bold red]✗[/bold red] {phase} failed "
            f"(exit {stream.returncode})"
        )
        sys.exit(1)

    phase = label.split()[0].rstrip("…")
    console.print(f"  [bold green]✓[/bold green] {phase} complete")


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

@click.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--board", default=None, metavar="FQBN",
              help="Board FQBN, e.g. arduino:avr:uno. Falls back to config.")
@click.option("--port", default=None, metavar="PORT",
              help="Serial port, e.g. COM3. Falls back to config.")
@click.option("--baud", default=None, type=int,
              help="Baud rate (stored in config, not used by arduino-cli).")
@click.option("--manual-reset", is_flag=True,
              help="Pause before upload — use when auto-reset is broken (common on ESP32 clones).")
def flash(
    file: Path,
    board: str | None,
    port: str | None,
    baud: int | None,
    manual_reset: bool,
) -> None:
    """Compile and upload FILE to the connected board.

    FILE may be a .ino sketch file or a sketch directory.
    Board and port default to the values stored by `nff init`.

    If the upload fails with "Wrong boot mode detected", your board's
    auto-reset is broken. Re-run with --manual-reset and hold the BOOT
    button when prompted.
    """
    fqbn, resolved_port = _resolve_target(board, port)
    sketch_dir = _resolve_sketch(file)

    console.print(
        f"  [bold]{sketch_dir.name}[/bold]  →  "
        f"[bold]{fqbn}[/bold] on [bold]{resolved_port}[/bold]"
    )

    # --- compile ---
    try:
        compile_stream = toolchain.stream_compile(sketch_dir, fqbn)
    except toolchain.ToolchainError as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        sys.exit(2)

    _stream_phase("Compiling…", compile_stream)

    # --- manual-reset gate ---
    if manual_reset:
        console.print(
            "\n  [yellow]Hold the BOOT button on your board, "
            "then press Enter to start uploading…[/yellow]"
        )
        click.pause(info="")
        console.print()

    # --- upload ---
    try:
        upload_stream = toolchain.stream_upload(sketch_dir, fqbn, resolved_port)
    except toolchain.ToolchainError as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        sys.exit(2)

    _stream_phase("Uploading…", upload_stream)


if __name__ == "__main__":
    flash()

