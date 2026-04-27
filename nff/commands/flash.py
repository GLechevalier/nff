"""nff flash — compile and upload a sketch, or simulate it with Wokwi."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

from pathlib import Path

import click
from rich.console import Console

from nff import config as cfg_module
from nff.tools import toolchain
from nff.tools import wokwi as wokwi_module

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_target(
    board: str | None,
    port: str | None,
    sim: bool = False,
) -> tuple[str, str]:
    """Return (fqbn, port), filling missing values from config.

    In simulation mode (*sim=True*) the port is not required — Wokwi
    needs only the FQBN to select the right chip.

    Exits with code 1 if a required value cannot be resolved.
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
    if not resolved_port and not sim:
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


def _run_simulation(sketch_dir: Path, fqbn: str, timeout_ms: int) -> None:
    """Compile *sketch_dir* and simulate it with Wokwi. Exits 1/2 on failure."""
    # -- compile (no upload) --------------------------------------------------
    try:
        compile_stream = toolchain.stream_compile(sketch_dir, fqbn)
    except toolchain.ToolchainError as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        sys.exit(2)

    _stream_phase("Compiling…", compile_stream)

    elf_path = toolchain.elf_path_for(sketch_dir, fqbn)
    if not elf_path.exists():
        console.print(
            f"  [bold red]✗[/bold red] Compiled ELF not found at "
            f"[bold]{elf_path}[/bold]\n"
            "    Ensure arduino-cli wrote its output to the expected path."
        )
        sys.exit(1)

    # -- set up Wokwi project in a temp dir -----------------------------------
    with tempfile.TemporaryDirectory() as _tmpdir:
        project_dir = Path(_tmpdir)
        try:
            diagram = wokwi_module.generate_diagram(fqbn)
            (project_dir / "diagram.json").write_text(
                json.dumps(diagram, indent=2), encoding="utf-8"
            )
            wokwi_module.write_wokwi_toml(project_dir, elf_path)
        except wokwi_module.WokwiError as exc:
            console.print(f"  [bold red]✗[/bold red] {exc}")
            sys.exit(1)

        # -- simulate ---------------------------------------------------------
        console.print(
            f"\n  Simulating…  "
            f"[dim](timeout: {timeout_ms} ms)[/dim]"
        )
        runner = wokwi_module.WokwiRunner()
        try:
            result = runner.run(project_dir, timeout_ms=timeout_ms)
        except wokwi_module.WokwiError as exc:
            console.print(f"  [bold red]✗[/bold red] {exc}")
            sys.exit(1)

    # -- display serial output ------------------------------------------------
    if result.serial_output.strip():
        console.print("[dim]─[/dim]" * 60)
        for line in result.serial_output.splitlines():
            if any(kw in line.lower() for kw in ("error", "exception", "fault", "panic")):
                console.print(f"  [bold red]{line}[/bold red]")
            elif any(kw in line.lower() for kw in ("warn", "warning")):
                console.print(f"  [yellow]{line}[/yellow]")
            else:
                console.print(f"  {line}")
        console.print("[dim]─[/dim]" * 60)
    else:
        console.print("  [dim](no serial output)[/dim]")

    if result.success:
        console.print("  [bold green]✓[/bold green] Simulation complete")
    else:
        console.print(
            f"  [bold red]✗[/bold red] Simulation exited with code {result.exit_code}"
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

@click.command()
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--board", default=None, metavar="FQBN",
              help="Board FQBN, e.g. arduino:avr:uno. Falls back to config.")
@click.option("--port", default=None, metavar="PORT",
              help="Serial port, e.g. COM3. Falls back to config. Not needed with --sim.")
@click.option("--baud", default=None, type=int,
              help="Baud rate (stored in config, not used by arduino-cli).")
@click.option("--manual-reset", is_flag=True,
              help="Pause before upload — use when auto-reset is broken (common on ESP32 clones).")
@click.option("--sim", is_flag=True,
              help="Simulate with Wokwi instead of uploading to real hardware. No board required.")
@click.option("--sim-timeout", default=5000, show_default=True, metavar="MS",
              help="Wokwi simulation timeout in milliseconds. Only used with --sim.")
def flash(
    file: Path,
    board: str | None,
    port: str | None,
    baud: int | None,
    manual_reset: bool,
    sim: bool,
    sim_timeout: int,
) -> None:
    """Compile and upload FILE to the connected board.

    FILE may be a .ino sketch file or a sketch directory.
    Board and port default to the values stored by `nff init`.

    \b
    Simulation mode (--sim):
      Compiles the sketch and runs it in the Wokwi simulator — no board or
      USB cable required.  Serial output is printed to the terminal.

    \b
    If the upload fails with "Wrong boot mode detected", your board's
    auto-reset is broken. Re-run with --manual-reset and hold the BOOT
    button when prompted.
    """
    fqbn, resolved_port = _resolve_target(board, port, sim=sim)
    sketch_dir = _resolve_sketch(file)
    
    if sim:
        console.print(
            f"  [bold]{sketch_dir.name}[/bold]  →  "
            f"[bold]{fqbn}[/bold]  [dim cyan][sim][/dim cyan]"
        )
        _run_simulation(sketch_dir, fqbn, sim_timeout)
        return

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

