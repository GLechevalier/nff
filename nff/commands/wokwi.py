"""nff wokwi — Wokwi simulator project management.

Subcommands
-----------
  nff wokwi init [--board FQBN] [--token TOKEN] [--force]
      Scaffold wokwi.toml + diagram.json in the current directory.

  nff wokwi run [--timeout MS] [--serial-log FILE]
      Run the Wokwi simulation for the project in the current directory
      and stream serial output to the terminal.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

import click
from rich.console import Console
from rich.text import Text

from nff import config as cfg_module
from nff.tools import toolchain
from nff.tools import wokwi as wokwi_module

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_WOKWI_TOML  = "wokwi.toml"
_DIAGRAM_JSON = "diagram.json"
_VSCODE_EXT  = (
    "https://marketplace.visualstudio.com/items?itemName=wokwi.wokwi-vscode"
)


# ---------------------------------------------------------------------------
# Helpers shared by both subcommands
# ---------------------------------------------------------------------------

def _resolve_fqbn(board: str | None) -> str:
    """Return FQBN from --board or config. Exits 1 if unresolvable."""
    fqbn = board
    if not fqbn:
        try:
            fqbn = cfg_module.get_default_device().get("fqbn") or ""
        except cfg_module.ConfigError:
            fqbn = ""
    if not fqbn:
        console.print(
            "  [bold red]✗[/bold red] Board FQBN required.\n"
            "    Pass [bold]--board FQBN[/bold] or run [bold]nff init[/bold] first."
        )
        sys.exit(1)
    return fqbn


def _read_elf_path_from_toml(toml_path: Path) -> str | None:
    """Return the raw elf value from wokwi.toml, or None if not found."""
    for line in toml_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("elf"):
            _, _, value = stripped.partition("=")
            return value.strip().strip('"').strip("'")
    return None


def _print_serial_line(line: str) -> None:
    """Print one line of simulated serial output with error/warning colouring."""
    low = line.lower()
    if any(kw in low for kw in ("error", "exception", "fault", "panic")):
        console.print(Text(line, style="bold red"))
    elif any(kw in low for kw in ("warn", "warning")):
        console.print(Text(line, style="yellow"))
    else:
        console.print(line)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------

@click.group()
def wokwi() -> None:
    """Wokwi simulator commands — run sketches without real hardware."""


# ---------------------------------------------------------------------------
# nff wokwi init
# ---------------------------------------------------------------------------

@wokwi.command("init")
@click.option("--board", default=None, metavar="FQBN",
              help="Board FQBN, e.g. arduino:avr:uno. Falls back to config.")
@click.option("--token", default=None, metavar="TOKEN",
              help="Wokwi CI API token. Saved to ~/.nff/config.json.")
@click.option("--force", is_flag=True,
              help="Overwrite existing wokwi.toml / diagram.json without prompting.")
def wokwi_init(board: str | None, token: str | None, force: bool) -> None:
    """Scaffold a Wokwi project in the current directory.

    Creates wokwi.toml (pointing at the compiled ELF) and a minimal
    diagram.json for the target board. Run this once per sketch, then
    use `nff wokwi run` to simulate.

    \b
    The ELF path in wokwi.toml assumes arduino-cli compiles into:
      ./build/<fqbn>/<sketch>.elf
    Compile your sketch first with:
      arduino-cli compile --fqbn FQBN .
    """
    fqbn = _resolve_fqbn(board)

    cwd = Path.cwd()
    toml_path    = cwd / _WOKWI_TOML
    diagram_path = cwd / _DIAGRAM_JSON

    # Guard against overwriting
    existing = [p for p in (toml_path, diagram_path) if p.exists()]
    if existing and not force:
        for p in existing:
            console.print(f"  [yellow]⚠[/yellow]  {p.name} already exists.")
        console.print("    Pass [bold]--force[/bold] to overwrite.")
        sys.exit(1)

    # Validate FQBN is Wokwi-supported before writing anything
    try:
        diagram = wokwi_module.generate_diagram(fqbn)
    except wokwi_module.WokwiError as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        sys.exit(1)

    # diagram.json
    diagram_path.write_text(json.dumps(diagram, indent=2), encoding="utf-8")
    console.print(
        f"  [bold green]✓[/bold green] {_DIAGRAM_JSON} written  "
        f"[dim]({diagram['parts'][0]['type']})[/dim]"
    )

    # wokwi.toml — ELF path relative to cwd for portability
    elf_abs = toolchain.elf_path_for(cwd, fqbn)
    try:
        elf_rel = elf_abs.relative_to(cwd)
    except ValueError:
        elf_rel = elf_abs   # fallback to absolute if outside cwd
    toml_content = (
        "[wokwi]\n"
        "version = 1\n"
        f'elf = "{elf_rel.as_posix()}"\n'
        'firmware = ""\n'
    )
    toml_path.write_text(toml_content, encoding="utf-8")
    console.print(
        f"  [bold green]✓[/bold green] {_WOKWI_TOML} written  "
        f"[dim](elf: {elf_rel.as_posix()})[/dim]"
    )

    # Token
    if token:
        cfg_module.set_wokwi_token(token)
        console.print("  [bold green]✓[/bold green] Wokwi API token saved to config.")
    else:
        existing_token = wokwi_module._resolve_token()
        if existing_token:
            console.print("  [dim]Wokwi API token already configured.[/dim]")
        else:
            console.print(
                "  [yellow]⚠[/yellow]  No Wokwi API token found.\n"
                "    Get one at [bold]https://wokwi.com/dashboard/ci[/bold] "
                "then run:\n"
                "    [bold]nff wokwi init --token YOUR_TOKEN[/bold]  or  "
                "[bold]export WOKWI_CLI_TOKEN=...[/bold]"
            )

    # Next-step hints
    console.print()
    console.print(
        "  [dim]Next steps:[/dim]\n"
        f"    1. Compile your sketch:  "
        f"[bold]arduino-cli compile --fqbn {fqbn} .[/bold]\n"
        f"    2. Run the simulation:   [bold]nff wokwi run[/bold]\n"
        f"    3. Add components to {_DIAGRAM_JSON} using the Wokwi VS Code extension:\n"
        f"       [dim]{_VSCODE_EXT}[/dim]"
    )


# ---------------------------------------------------------------------------
# nff wokwi run
# ---------------------------------------------------------------------------

@wokwi.command("run")
@click.option("--timeout", "timeout_ms", default=5000, show_default=True, metavar="MS",
              help="Simulation wall-clock timeout in milliseconds.")
@click.option("--serial-log", "serial_log", default=None,
              type=click.Path(dir_okay=False, path_type=Path),
              metavar="FILE",
              help="Save captured serial output to FILE.")
def wokwi_run(timeout_ms: int, serial_log: Path | None) -> None:
    """Run the Wokwi simulation for the current project.

    Reads wokwi.toml from the current directory and calls wokwi-cli.
    Serial output is streamed to the terminal in real time.

    Run `nff wokwi init` first if wokwi.toml does not exist yet.
    """
    cwd = Path.cwd()
    toml_path = cwd / _WOKWI_TOML

    # -- pre-flight checks ----------------------------------------------------

    if not toml_path.exists():
        console.print(
            f"  [bold red]✗[/bold red] {_WOKWI_TOML} not found in [bold]{cwd}[/bold]\n"
            "    Run [bold]nff wokwi init[/bold] to scaffold the project first."
        )
        sys.exit(1)

    if not toolchain.find_wokwi_cli():
        console.print(
            "  [bold red]✗[/bold red] wokwi-cli not found.\n"
            "    Install from [bold]https://github.com/wokwi/wokwi-cli[/bold]"
        )
        sys.exit(2)

    # Warn if the ELF referenced in wokwi.toml doesn't exist yet
    elf_value = _read_elf_path_from_toml(toml_path)
    if elf_value:
        elf_path = Path(elf_value) if Path(elf_value).is_absolute() else cwd / elf_value
        if not elf_path.exists():
            console.print(
                f"  [yellow]⚠[/yellow]  ELF not found: [bold]{elf_value}[/bold]\n"
                "    Compile your sketch first, e.g.:\n"
                f"    [bold]arduino-cli compile --fqbn <FQBN> .[/bold]"
            )

    # -- environment ----------------------------------------------------------

    token = wokwi_module._resolve_token()
    env = os.environ.copy()
    if token:
        env["WOKWI_CLI_TOKEN"] = token
    elif "WOKWI_CLI_TOKEN" not in env:
        console.print(
            "  [yellow]⚠[/yellow]  No Wokwi API token — simulation may fail.\n"
            "    Run [bold]nff wokwi init --token YOUR_TOKEN[/bold] to configure one."
        )

    cmd = ["wokwi-cli", "run", str(cwd), "--timeout", str(timeout_ms)]

    # -- run ------------------------------------------------------------------

    console.print(
        f"  [bold cyan]nff wokwi run[/bold cyan]  "
        f"[dim]—  timeout: {timeout_ms} ms  —  Ctrl+C to abort[/dim]"
    )
    console.print("[dim]─[/dim]" * 60)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
    except FileNotFoundError:
        console.print("  [bold red]✗[/bold red] wokwi-cli not found (PATH issue).")
        sys.exit(2)

    assert proc.stdout is not None

    serial_lines: list[str] = []
    try:
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\n")
            serial_lines.append(line)
            _print_serial_line(line)
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        console.print("[dim]─[/dim]" * 60)
        console.print("  [dim]Simulation aborted.[/dim]")
        sys.exit(0)

    proc.wait()
    console.print("[dim]─[/dim]" * 60)

    # -- serial log -----------------------------------------------------------

    if serial_log and serial_lines:
        try:
            serial_log.write_text("\n".join(serial_lines) + "\n", encoding="utf-8")
            console.print(
                f"  [bold green]✓[/bold green] Serial log written to "
                f"[bold]{serial_log}[/bold]"
            )
        except OSError as exc:
            console.print(f"  [yellow]⚠[/yellow]  Could not write serial log: {exc}")

    # -- result ---------------------------------------------------------------

    if not serial_lines:
        console.print("  [dim](no serial output)[/dim]")

    if proc.returncode == 0:
        console.print("  [bold green]✓[/bold green] Simulation complete.")
    else:
        console.print(
            f"  [bold red]✗[/bold red] wokwi-cli exited with code {proc.returncode}."
        )
        sys.exit(1)


if __name__ == "__main__":
    wokwi()
