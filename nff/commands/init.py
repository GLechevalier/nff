"""nff init — detect board, write config, register the MCP server."""

from __future__ import annotations

import pathlib
import sys

if __name__ == "__main__":
    _pkg_parent = str(pathlib.Path(__file__).resolve().parents[2])
    if _pkg_parent not in sys.path:
        sys.path.insert(0, _pkg_parent)

import json
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import click
from rich.console import Console

from nff import config as cfg_module
from nff.tools import boards as boards_module
from nff.tools import toolchain
from nff.tools import installer
from nff.tools.boards import DetectedDevice

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)

_CLAUDE_DESKTOP_CONFIG = Path.home() / ".claude" / "claude_desktop_config.json"
_MCP_ENTRY: dict = {"command": "nff", "args": ["mcp"]}

# Wokwi-supported boards shown during simulation onboarding.
_SIM_BOARDS: list[tuple[str, str]] = [
    ("arduino:avr:uno",         "Arduino Uno"),
    ("arduino:avr:mega",        "Arduino Mega 2560"),
    ("arduino:avr:nano",        "Arduino Nano"),
    ("arduino:avr:leonardo",    "Arduino Leonardo"),
    ("esp32:esp32:esp32",       "ESP32 DevKit V1"),
    ("esp8266:esp8266:generic", "ESP8266"),
]
_SIM_BOARD_NAMES: dict[str, str] = {fqbn: name for fqbn, name in _SIM_BOARDS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_arduino_cli() -> None:
    """Install arduino-cli silently if it is not already on PATH."""
    if toolchain.find_arduino_cli():
        return
    console.print(
        "  [yellow]⚠[/yellow]  arduino-cli not found — installing automatically…"
    )
    try:
        exe = installer.install(force=False)
        if installer.verify(exe):
            console.print("  [bold green]✓[/bold green] arduino-cli installed.")
        else:
            console.print(
                "  [yellow]⚠[/yellow]  arduino-cli installed but could not be verified. "
                "Restart your terminal if commands fail."
            )
    except Exception as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Could not auto-install arduino-cli: {exc}\n"
            "  Install manually: https://arduino.github.io/arduino-cli"
        )


def _pick_mode() -> int:
    """Prompt the user to choose real-board or simulation mode. Returns 1 or 2."""
    console.print()
    console.print("[bold]How would you like to develop?[/bold]")
    console.print(
        "  1. [bold]Real board[/bold]            "
        "[dim]Connect a physical device via USB[/dim]"
    )
    console.print(
        "  2. [bold]Simulated environment[/bold]  "
        "[dim]Develop without hardware using Wokwi[/dim]"
    )
    console.print()
    return click.prompt("Select mode", type=click.IntRange(1, 2), default=1)


def _pick_sim_board() -> str:
    """Prompt the user to choose a Wokwi-supported board. Returns the FQBN."""
    console.print()
    console.print("[bold]Select a target board for simulation:[/bold]")
    for i, (fqbn, name) in enumerate(_SIM_BOARDS, 1):
        console.print(f"  {i}. [bold]{name}[/bold]  [dim]{fqbn}[/dim]")
    console.print()
    choice = click.prompt(
        "Select board",
        type=click.IntRange(1, len(_SIM_BOARDS)),
        default=1,
    )
    return _SIM_BOARDS[choice - 1][0]


def _write_sim_claude_md(fqbn: str, wokwi_chip: str) -> None:
    """Write the Wokwi simulation CLAUDE.md into the current working directory."""
    from nff.commands.wokwi import _CLAUDE_MD_TEMPLATE as _wokwi_tmpl  # noqa: PLC0415
    dest = Path.cwd() / "CLAUDE.md"
    dest.write_text(
        _wokwi_tmpl.format(
            board=fqbn,
            fqbn=fqbn,
            fqbn_dotted=fqbn.replace(":", "."),
            wokwi_chip=wokwi_chip,
        ),
        encoding="utf-8",
    )
    console.print(
        f"  [bold green]✓[/bold green] CLAUDE.md written to [bold]{dest}[/bold]"
    )


def _run_sim_init(baud: int, force: bool) -> None:
    """Handle the simulation-mode onboarding path."""
    from nff.tools import wokwi as wokwi_tools  # noqa: PLC0415

    fqbn = _pick_sim_board()
    _ensure_arduino_cli()

    cwd = Path.cwd()
    toml_path    = cwd / "wokwi.toml"
    diagram_path = cwd / "diagram.json"

    # Guard against overwriting existing Wokwi project files
    existing = [p for p in (toml_path, diagram_path) if p.exists()]
    if existing and not force:
        for p in existing:
            console.print(f"  [yellow]⚠[/yellow]  {p.name} already exists.")
        console.print("    Pass [bold]--force[/bold] to overwrite.")
        sys.exit(1)

    # Validate FQBN + generate diagram
    try:
        diagram = wokwi_tools.generate_diagram(fqbn)
    except wokwi_tools.WokwiError as exc:
        console.print(f"  [bold red]✗[/bold red] {exc}")
        sys.exit(1)

    # Write nff config (port left empty — no physical device)
    board_name = _SIM_BOARD_NAMES[fqbn]
    cfg_module.set_default_device(port="", board=board_name, fqbn=fqbn, baud=baud)
    console.print(
        f"  [bold green]✓[/bold green] Config written to "
        f"[bold]{cfg_module.CONFIG_PATH}[/bold]"
    )

    # Write diagram.json
    diagram_path.write_text(json.dumps(diagram, indent=2), encoding="utf-8")
    console.print(
        f"  [bold green]✓[/bold green] diagram.json written  "
        f"[dim]({diagram['parts'][0]['type']})[/dim]"
    )

    # Write wokwi.toml
    elf_abs = toolchain.elf_path_for(cwd, fqbn)
    try:
        elf_rel = elf_abs.relative_to(cwd)
    except ValueError:
        elf_rel = elf_abs
    toml_path.write_text(
        "[wokwi]\n"
        "version = 1\n"
        f'elf = "{elf_rel.as_posix()}"\n'
        'firmware = ""\n',
        encoding="utf-8",
    )
    console.print(
        f"  [bold green]✓[/bold green] wokwi.toml written  "
        f"[dim](elf: {elf_rel.as_posix()})[/dim]"
    )

    # Write CLAUDE.md (simulation variant)
    try:
        _write_sim_claude_md(fqbn=fqbn, wokwi_chip=diagram["parts"][0]["type"])
    except OSError as exc:
        console.print(f"  [yellow]⚠[/yellow]  Could not write CLAUDE.md: {exc}")

    # Warn if no Wokwi API token
    if not wokwi_tools._resolve_token():
        console.print(
            "  [yellow]⚠[/yellow]  No Wokwi API token found.\n"
            "    Get one at [bold]https://wokwi.com/dashboard/ci[/bold] then run:\n"
            "    [bold]nff wokwi init --token YOUR_TOKEN[/bold]  or  "
            "[bold]export WOKWI_CLI_TOKEN=...[/bold]"
        )

    # Install skills + register MCP
    try:
        _install_claude_skills()
    except Exception as exc:
        console.print(f"  [yellow]⚠[/yellow]  Could not install Claude skills: {exc}")

    if _register_mcp_claude_code():
        console.print(
            "  [bold green]✓[/bold green] Registered with Claude Code CLI "
            "([bold]claude mcp add nff nff mcp[/bold])"
        )
    else:
        console.print(
            "  [dim]`claude` CLI not found — skipping Claude Code registration.[/dim]\n"
            "  To register manually: [bold]claude mcp add nff nff mcp[/bold]"
        )

    try:
        _update_claude_desktop_config()
        console.print(
            f"  [bold green]✓[/bold green] Claude Desktop config updated: "
            f"[bold]{_CLAUDE_DESKTOP_CONFIG}[/bold]"
        )
    except ValueError as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Claude Desktop config has invalid JSON — "
            f"fix it manually: {exc}\n"
            f"  Path: {_CLAUDE_DESKTOP_CONFIG}"
        )
    except OSError as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Could not write Claude Desktop config: {exc}"
        )

    console.print()
    console.print(
        "  [dim]Next steps:[/dim]\n"
        f"    1. Write your sketch  [bold]<name>.ino[/bold]\n"
        f"    2. Compile + sim      [bold]nff flash --sim <name>.ino --board {fqbn}[/bold]\n"
        f"    3. Visual sim         [bold]nff wokwi run --gui[/bold]\n"
        f"    4. Add components to [bold]diagram.json[/bold] using the Wokwi VS Code extension"
    )


def _pick_device(devices: list[DetectedDevice]) -> DetectedDevice:
    """Return the chosen device; prompts when more than one is connected."""
    if len(devices) == 1:
        return devices[0]

    console.print("\n[bold]Multiple boards detected:[/bold]")
    for i, d in enumerate(devices, 1):
        console.print(f"  {i}. [bold]{d.board}[/bold] on {d.port}")

    choice = click.prompt(
        "Select board",
        type=click.IntRange(1, len(devices)),
        default=1,
    )
    return devices[choice - 1]


def _register_mcp_claude_code() -> bool:
    """Register nff with Claude Code CLI via `claude mcp add`.

    Uses the absolute path of the running nff executable so Claude Code can
    locate it on Windows where bare-name resolution may fail.

    Returns True on success, False if `claude` is not in PATH or the command fails.
    """
    if not shutil.which("claude"):
        return False

    nff_exe = shutil.which("nff") or sys.executable
    # On Windows prefer the .exe alongside the current interpreter if found
    if sys.platform == "win32":
        candidate = Path(sys.executable).parent / "nff.exe"
        if candidate.exists():
            nff_exe = str(candidate)

    try:
        result = subprocess.run(
            ["claude", "mcp", "add", "--scope", "user", "nff", nff_exe, "mcp"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _install_claude_skills() -> None:
    """Copy bundled skill files to ~/.claude/commands/ (user-level global skills).

    Silently skips any file that cannot be written so it never aborts init.
    """
    dest_dir = Path.home() / ".claude" / "commands"
    dest_dir.mkdir(parents=True, exist_ok=True)

    skills_pkg = resources.files("nff") / "skills"
    installed: list[str] = []
    for skill_file in skills_pkg.iterdir():
        if not skill_file.name.endswith(".md"):
            continue
        try:
            dest = dest_dir / skill_file.name
            dest.write_text(skill_file.read_text(encoding="utf-8"), encoding="utf-8")
            installed.append(skill_file.name)
        except OSError:
            pass

    if installed:
        names = ", ".join(f"/{p.removesuffix('.md')}" for p in installed)
        console.print(
            f"  [bold green]✓[/bold green] Claude skills installed: [bold]{names}[/bold]"
        )


def _update_claude_desktop_config() -> None:
    """Merge the nff MCP entry into ~/.claude/claude_desktop_config.json.

    Preserves all pre-existing keys and other mcpServers entries.

    Raises:
        OSError: If the file cannot be written.
        ValueError: If an existing file contains invalid JSON (caller should
            surface this as a warning rather than aborting).
    """
    _CLAUDE_DESKTOP_CONFIG.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if _CLAUDE_DESKTOP_CONFIG.exists():
        raw = _CLAUDE_DESKTOP_CONFIG.read_text(encoding="utf-8")
        if raw.strip():
            data = json.loads(raw)  # raises ValueError on bad JSON

    data.setdefault("mcpServers", {})["nff"] = _MCP_ENTRY

    _CLAUDE_DESKTOP_CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------

@click.command()
@click.option("--port", default=None, metavar="PORT",
              help="Serial port to use; skips auto-detection.")
@click.option("--baud", default=9600, show_default=True,
              help="Baud rate stored in config.")
@click.option("--force", is_flag=True,
              help="Overwrite an existing config without prompting.")
def init(port: str | None, baud: int, force: bool) -> None:
    """Detect a connected board, write config, and register the MCP server."""
    # When no explicit port is given, prompt for development mode first.
    if not port:
        mode = _pick_mode()
        if mode == 2:
            _run_sim_init(baud, force)
            return

    _ensure_arduino_cli()

    # Guard against overwriting an existing, valid config
    if cfg_module.exists() and not force:
        try:
            existing = cfg_module.get_default_device()
            if existing.get("port"):
                console.print(
                    f"[yellow]Config already exists[/yellow] "
                    f"({existing.get('board', '?')} on {existing['port']}).\n"
                    "  Pass [bold]--force[/bold] to overwrite."
                )
                return
        except cfg_module.ConfigError:
            pass  # unreadable config → let the user fix it by re-running init

    # -----------------------------------------------------------------
    # Device resolution
    # -----------------------------------------------------------------
    device: DetectedDevice | None = None

    if port:
        # User supplied a port — accept it even if the board isn't recognised.
        console.print(f"  Using specified port [bold]{port}[/bold]…")
        device = boards_module.find_device(port)
        if device is None:
            console.print(
                f"  [yellow]⚠[/yellow]  {port} not matched to a known board. "
                "Storing as 'Unknown'."
            )
            cfg_module.set_default_device(port=port, board="Unknown", fqbn="", baud=baud)
            _write_success(port=port, board="Unknown", device=None)
            return
    else:
        console.print("  Scanning USB ports…")
        devices = boards_module.list_devices()

        if not devices:
            console.print(
                "[bold red]✗[/bold red] No recognised boards found.\n"
                "  Plug in a board and try again, or use "
                "[bold]--port PORT[/bold] to specify one manually."
            )
            sys.exit(1)

        device = _pick_device(devices)

    # -----------------------------------------------------------------
    # Write nff config
    # -----------------------------------------------------------------
    cfg_module.set_default_device(
        port=device.port,
        board=device.board,
        fqbn=device.fqbn,
        baud=baud,
    )

    _write_success(port=device.port, board=device.board, device=device)


_CLAUDE_MD_TEMPLATE = """\
# nff — Hardware Development Context

## Hard Rules
- Always use `nff flash` to compile/flash — never call arduino-cli directly.
- Always use `nff flash --sim` for simulation — never call wokwi-cli directly.
- Never install libraries with arduino-cli. Write sketches that use built-in APIs,
  or ask the user to install the library first.
- For ESP32 servo/PWM use ledcAttach + ledcWrite (built-in LEDC, no library needed).
- Write sketches in the **current directory**: `<name>.ino` (not in a subdirectory).

## Connected Device
- Board  : {board}
- Port   : {port}
- FQBN   : {fqbn}
- Wokwi  : {wokwi_chip}

---

## nff CLI Commands

```
nff mcp                               start the MCP server (Claude Code calls this automatically)
nff flash <sketch.ino>                compile + upload to {port}
nff flash <sketch.ino> --sim          compile + simulate with Wokwi (no hardware needed)
nff flash <sketch.ino> --board <fqbn> override board FQBN
nff flash <sketch.ino> --port <port>  override serial port
nff monitor                           open interactive serial monitor on {port}
nff monitor --port <port> --baud <n>  override port / baud rate
nff wokwi init                        scaffold wokwi.toml + diagram.json in cwd
nff wokwi run                         run headless Wokwi simulation, stream serial output
nff wokwi run --gui                   open animated circuit in VS Code
nff wokwi run --timeout <ms>          set simulation wall-clock timeout (default 5000 ms)
nff wokwi run --serial-log <file>     write captured serial output to a file
nff doctor                            check all dependencies and config
nff init                              re-detect board, rewrite config + CLAUDE.md
```

---

## Workflow — Real Hardware

Iteration loop:
1. Write / edit `<name>.ino` in the current directory.
2. `nff flash <name>.ino` — compile and upload.
3. `nff monitor` — inspect serial output (Ctrl+C to quit).
4. Fix bugs, repeat from step 2.

MCP tools (called by Claude, no terminal needed):
```
flash(code)           compile + upload sketch
serial_read(3000)     capture 3 s of serial output
serial_write(data)    send a string to the device
reset_device()        hardware reset via DTR toggle
list_devices()        verify board is connected
get_device_info()     port / board / FQBN / baud
```

---

## Workflow — Wokwi Simulation (no hardware needed)

### Quick — headless via MCP tool
1. `wokwi_flash(code, board="{fqbn}")` — compile + simulate, returns serial output.
2. Inspect `serial_output` — no USB cable required.
3. Iterate until output is correct, then `flash(code)` to upload to real hardware.

### Full pipeline — visual circuit
1. Write `<name>.ino` in the current directory.
2. `nff wokwi init --board {fqbn}` — creates `wokwi.toml` + `diagram.json`.
3. Edit `diagram.json` to add components (LEDs, buttons, servos…).
4. `nff flash <name>.ino --sim --board {fqbn}` — compile.
5. Update `wokwi.toml` firmware path:
     firmware = "build/{fqbn_dotted}/<name>.ino.elf"
6. `nff wokwi run --gui` — opens animated circuit in VS Code.
7. Fix bugs, repeat from step 4.

---

## diagram.json — Component Wiring

Always wire the serial monitor:
  ["esp:TX0", "$serialMonitor:RX", "", []]
  ["esp:RX0", "$serialMonitor:TX", "", []]

ESP32 pin names: esp:D<gpio>  esp:GND.1  esp:GND.2  esp:3V3  esp:VIN

Common components:
  wokwi-led          attrs: color (red/green/blue/yellow)
  wokwi-pushbutton   attrs: color — pins: btn:1.l (gpio), btn:2.l (GND)
  wokwi-servo        attrs: minAngle "-90", maxAngle "90" — pins: PWM, V+, GND
  wokwi-resistor     attrs: value (ohms)
  wokwi-ntc-temperature-sensor

Pushbutton wiring (INPUT_PULLUP):
  ["esp:D15", "btn1:1.l", "green", []]
  ["esp:GND.2", "btn1:2.l", "black", []]

---

## ESP32 Servo — LEDC (no library)

Wokwi servo range: 500 µs (−90°) → 1500 µs (0°) → 2500 µs (+90°)
50 Hz, 16-bit resolution (period = 20 000 µs, max count = 65 535):

  −90°  → duty 1638
    0°  → duty 4915
  +90°  → duty 8192

```cpp
ledcAttach(SERVO_PIN, 50, 16);   // ESP32 Arduino core 3.x
ledcWrite(SERVO_PIN, 4915);      // center position
```

---

## Debugging

Simulation:
- Compile error     → fix sketch, re-run nff flash --sim
- Wrong output      → nff wokwi run --serial-log out.txt, inspect out.txt
- Component silent  → check diagram.json pin names and connection direction
- Servo wrong angle → verify duty values match the 500–2500 µs Wokwi range
- Button skipped    → ensure INPUT_PULLUP and wiring gpio→btn:1.l, GND→btn:2.l

Hardware:
- Port not found    → nff init to re-detect
- Upload fails      → nff flash --manual-reset, hold BOOT when prompted
- Wrong output      → nff monitor --baud 115200
"""


def _write_claude_md(port: str, board: str, fqbn: str, wokwi_chip: str | None) -> None:
    """Write CLAUDE.md into the current working directory."""
    dest = Path.cwd() / "CLAUDE.md"
    content = _CLAUDE_MD_TEMPLATE.format(
        board=board,
        port=port,
        fqbn=fqbn or "unknown",
        fqbn_dotted=(fqbn or "unknown").replace(":", "."),
        wokwi_chip=wokwi_chip or "not supported",
    )
    dest.write_text(content, encoding="utf-8")
    console.print(
        f"  [bold green]✓[/bold green] CLAUDE.md written to [bold]{dest}[/bold]"
    )


def _write_success(port: str, board: str, device: DetectedDevice | None) -> None:
    """Print the success lines and update the Claude Desktop config."""
    if device:
        wokwi_note = (
            f"  [dim cyan]sim: {device.wokwi_chip}[/dim cyan]"
            if device.wokwi_chip
            else "  [dim]no Wokwi support[/dim]"
        )
        console.print(
            f"  [bold green]✓[/bold green] Found: [bold]{device.board}[/bold] "
            f"on {device.port} "
            f"(vendor: {device.vendor_id}, product: {device.product_id})"
            f"{wokwi_note}"
        )

    console.print(
        f"  [bold green]✓[/bold green] Config written to "
        f"[bold]{cfg_module.CONFIG_PATH}[/bold]"
    )

    # Write CLAUDE.md in cwd
    try:
        fqbn = device.fqbn if device else ""
        wokwi_chip = device.wokwi_chip if device else None
        _write_claude_md(port=port, board=board, fqbn=fqbn, wokwi_chip=wokwi_chip)
    except OSError as exc:
        console.print(f"  [yellow]⚠[/yellow]  Could not write CLAUDE.md: {exc}")

    # Install Claude skills globally
    try:
        _install_claude_skills()
    except Exception as exc:
        console.print(f"  [yellow]⚠[/yellow]  Could not install Claude skills: {exc}")

    # Claude Code CLI — preferred
    if _register_mcp_claude_code():
        console.print(
            "  [bold green]✓[/bold green] Registered with Claude Code CLI "
            "([bold]claude mcp add nff nff mcp[/bold])"
        )
    else:
        console.print(
            "  [dim]`claude` CLI not found — skipping Claude Code registration.[/dim]\n"
            "  To register manually: [bold]claude mcp add nff nff mcp[/bold]"
        )

    # Claude Desktop — write JSON config as well
    try:
        _update_claude_desktop_config()
        console.print(
            f"  [bold green]✓[/bold green] Claude Desktop config updated: "
            f"[bold]{_CLAUDE_DESKTOP_CONFIG}[/bold]"
        )
    except ValueError as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Claude Desktop config has invalid JSON — "
            f"fix it manually: {exc}\n"
            f"  Path: {_CLAUDE_DESKTOP_CONFIG}"
        )
    except OSError as exc:
        console.print(
            f"  [yellow]⚠[/yellow]  Could not write Claude Desktop config: {exc}"
        )


if __name__ == "__main__":
    init()
