# nff — Claude Code IoT Bridge

## Project Overview

`nff` is an open source Python CLI tool that connects Claude Code to physical hardware devices via USB — or to simulated hardware via Wokwi. It exposes hardware actions (flash, monitor, reset, simulate) as MCP tools so Claude Code can autonomously compile, upload, debug, and interact with embedded devices, with or without real hardware attached.

**Target devices (v1):** Arduino (Uno, Mega, Nano, Leonardo), ESP32, ESP8266  
**Connection:** USB (real hardware) or Wokwi simulator (no hardware required)  
**Language:** Python 3.10+  
**Distribution:** `pip install nff`

---

## Repository Structure

```
nff/
├── nff/
│   ├── __init__.py
│   ├── cli.py              # Entry point — routes subcommands
│   ├── mcp_server.py       # MCP server — exposes tools to Claude Code
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── init.py         # nff init
│   │   ├── flash.py        # nff flash [--sim]
│   │   ├── monitor.py      # nff monitor
│   │   ├── doctor.py       # nff doctor
│   │   └── wokwi.py        # nff wokwi subcommands
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── serial.py       # Serial read/write/capture
│   │   ├── boards.py       # Board detection + USB vendor ID lookup
│   │   ├── toolchain.py    # arduino-cli + esptool wrappers
│   │   └── wokwi.py        # wokwi-cli subprocess wrapper + diagram helpers
│   └── config.py           # Config file (~/.nff/config.json)
├── tests/
│   ├── test_serial.py
│   ├── test_boards.py
│   ├── test_mcp.py
│   └── test_wokwi.py
├── pyproject.toml
├── README.md
└── CLAUDE.md               # This file
```

---

## CLI Commands

### `nff init`
Detects connected USB devices, identifies the board, and writes config.

```
nff init
→ Scanning USB ports...
→ Found: Arduino Uno on /dev/ttyUSB0 (vendor: 2341, product: 0043)
→ Config written to ~/.nff/config.json
→ MCP config written to ~/.claude/claude_desktop_config.json
```

**What it does:**
- Calls `serial.tools.list_ports` to enumerate USB/serial ports
- Matches USB vendor/product IDs against known board database
- Writes device config to `~/.nff/config.json`
- Appends MCP server entry to `~/.claude/claude_desktop_config.json`

### `nff flash <file> [--board <fqbn>] [--port <port>] [--sim]`
Compiles and uploads firmware to the device, or simulates it via Wokwi.

```
nff flash ./blink.ino
nff flash ./main.ino --board esp32:esp32:esp32 --port /dev/ttyUSB0
nff flash ./blink.ino --sim
nff flash ./main.ino --sim --board arduino:avr:uno
```

**What it does (hardware):**
- Reads board + port from config if not passed as flags
- Calls `arduino-cli compile --fqbn <board> <sketch>`
- Calls `arduino-cli upload --fqbn <board> --port <port> <sketch>`
- Streams stdout/stderr to terminal in real time
- Returns exit code 0 on success, 1 on failure

**What it does (`--sim`):**
- Compiles the sketch via `arduino-cli compile` (no upload)
- Delegates to `nff/tools/wokwi.py` — runs `wokwi-cli` against the compiled ELF
- Streams simulated serial output to terminal
- No physical device or port needed

### `nff wokwi`
Subcommand group for Wokwi simulator management.

#### `nff wokwi init [--board <fqbn>]`
Scaffolds a Wokwi project in the current directory.

```
nff wokwi init
nff wokwi init --board arduino:avr:uno
```

**What it does:**
- Creates `wokwi.toml` pointing at the compiled ELF
- Creates a minimal `diagram.json` for the chosen board (single MCU, no peripherals)
- Writes Wokwi API token path into `~/.nff/config.json` if not already set
- Prints a link to the Wokwi diagram editor for circuit customisation

`diagram.json` template per board:

| Board FQBN | Wokwi chip |
|---|---|
| `arduino:avr:uno` | `wokwi-arduino-uno` |
| `arduino:avr:mega` | `wokwi-arduino-mega` |
| `arduino:avr:nano` | `wokwi-arduino-nano` |
| `esp32:esp32:esp32` | `wokwi-esp32-devkit-v1` |
| `esp8266:esp8266:generic` | `wokwi-esp8266` |

#### `nff wokwi run [--timeout <ms>] [--serial-log <file>]`
Runs the current project in the Wokwi simulator and streams serial output.

```
nff wokwi run
nff wokwi run --timeout 10000 --serial-log ./sim_output.txt
```

**What it does:**
- Reads `wokwi.toml` from the current directory (error if missing — run `nff wokwi init` first)
- Calls `wokwi-cli run --timeout <ms>` and pipes stdout/stderr
- Optionally writes captured serial output to a log file
- Default timeout: 5000 ms

### `nff monitor [--port <port>] [--baud <rate>]`
Opens an interactive serial monitor.

```
nff monitor
nff monitor --port /dev/ttyUSB0 --baud 115200
```

**What it does:**
- Opens serial connection via `pyserial`
- Streams device output to terminal
- Ctrl+C to exit cleanly
- Default baud: 9600 (overridable in config)

### `nff doctor`
Checks all dependencies and configuration, including Wokwi simulator readiness.

```
nff doctor
→ ✓ Python 3.11.2
→ ✓ arduino-cli 0.35.0 found at /usr/local/bin/arduino-cli
→ ✓ esptool 4.6.2 found
→ ✓ pyserial 3.5 installed
→ ✓ Config file found at ~/.nff/config.json
→ ✓ Device detected: Arduino Uno on /dev/ttyUSB0
→ ✓ wokwi-cli 0.14.0 found at /usr/local/bin/wokwi-cli
→ ✓ Wokwi API token configured
→ ✗ Claude Desktop config not found — run nff init
```

**What it checks:**
- Python version >= 3.10
- `arduino-cli` installed and in PATH
- `esptool` installed (`pip install esptool`)
- `pyserial` installed
- `~/.nff/config.json` exists and is valid
- USB device is connected and port is accessible (warns, not errors, if no device — Wokwi works without one)
- `wokwi-cli` installed and in PATH (optional — needed only for `--sim` and `nff wokwi`)
- Wokwi API token present in config or `WOKWI_CLI_TOKEN` env var
- `~/.claude/claude_desktop_config.json` has nff MCP entry

### `nff mcp`
Starts the MCP server. This is called automatically by Claude Code — users do not run this directly.

```
nff mcp
→ nff MCP server running on stdio
→ Waiting for Claude Code...
```

**What it does:**
- Starts an MCP server over stdin/stdout (stdio transport)
- Registers all MCP tools (see MCP Tools section below)
- Reads device config from `~/.nff/config.json`
- Stays running until Claude Code closes the connection

---

## MCP Tools

These are the tools Claude Code can call. Each tool is registered in `mcp_server.py`.

### `list_devices()`
Returns all connected USB/serial devices with board identification.

```json
{
  "devices": [
    {
      "port": "/dev/ttyUSB0",
      "board": "Arduino Uno",
      "fqbn": "arduino:avr:uno",
      "vendor_id": "2341",
      "product_id": "0043"
    }
  ]
}
```

### `flash(code, board, port)`
Writes code to a temp `.ino` file, compiles, and uploads.

**Parameters:**
- `code` (string, required) — full Arduino/C++ sketch source code
- `board` (string, optional) — FQBN e.g. `arduino:avr:uno`, defaults to config
- `port` (string, optional) — serial port e.g. `/dev/ttyUSB0`, defaults to config

**Returns:** compile + upload output, success/failure status

**Implementation note:** Write code to `/tmp/nff_sketch/nff_sketch.ino` before compiling. arduino-cli requires the sketch file to be in a folder with the same name.

### `serial_read(duration_ms, port, baud)`
Captures serial output for a given duration.

**Parameters:**
- `duration_ms` (int, default: 3000) — how long to listen in milliseconds
- `port` (string, optional) — defaults to config
- `baud` (int, default: 9600) — baud rate

**Returns:** captured serial output as a string

### `serial_write(data, port, baud)`
Sends a string to the device over serial.

**Parameters:**
- `data` (string, required) — data to send
- `port` (string, optional) — defaults to config
- `baud` (int, default: 9600)

**Returns:** confirmation string

### `reset_device(port)`
Toggles DTR to trigger a hardware reset on the device.

**Parameters:**
- `port` (string, optional) — defaults to config

**Returns:** confirmation string

### `get_device_info(port)`
Returns detailed info about the connected device.

**Returns:**
```json
{
  "port": "/dev/ttyUSB0",
  "board": "Arduino Uno",
  "fqbn": "arduino:avr:uno",
  "baud": 9600,
  "vendor_id": "2341",
  "product_id": "0043"
}
```

### `wokwi_flash(code, board, timeout_ms)`
Compiles the sketch and runs it in the Wokwi simulator. No physical device needed.

**Parameters:**
- `code` (string, required) — full Arduino/C++ sketch source code
- `board` (string, optional) — FQBN, defaults to config. Must be a Wokwi-supported board.
- `timeout_ms` (int, default: 5000) — simulation wall-clock timeout in milliseconds

**What it does:**
1. Writes code to a temp sketch directory
2. Compiles via `arduino-cli compile --fqbn <board>`
3. Generates a minimal `diagram.json` if one is not already present alongside the sketch
4. Runs `wokwi-cli run --timeout <timeout_ms>` and captures stdout
5. Returns compile output + simulated serial output + success/failure status

**Returns:**
```json
{
  "compile_output": "...",
  "serial_output": "Hello from Wokwi!\nCounter: 1\n...",
  "exit_code": 0,
  "simulated": true
}
```

### `wokwi_serial_read(code, board, duration_ms)`
Convenience wrapper: compiles, simulates, and returns only the serial output.

**Parameters:**
- `code` (string, required) — full sketch source code
- `board` (string, optional) — FQBN, defaults to config
- `duration_ms` (int, default: 3000) — how long to capture simulated serial output

**Returns:** captured serial output as a string (same format as `serial_read`)

### `wokwi_get_diagram(board)`
Returns a minimal `diagram.json` stub for the given board that Claude can extend.

**Parameters:**
- `board` (string, required) — FQBN

**Returns:** `diagram.json` content as a JSON string, ready to write to disk

---

## Config File

Stored at `~/.nff/config.json`. Created by `nff init`, editable by hand.

```json
{
  "version": "1",
  "default_device": {
    "port": "/dev/ttyUSB0",
    "board": "Arduino Uno",
    "fqbn": "arduino:avr:uno",
    "baud": 9600
  },
  "wokwi": {
    "api_token": "YOUR_WOKWI_TOKEN",
    "default_timeout_ms": 5000,
    "diagram_path": null
  }
}
```

**Wokwi config fields:**
- `api_token` — Wokwi CI API token (https://wokwi.com/dashboard/ci). Can also be set via `WOKWI_CLI_TOKEN` env var (env var takes precedence).
- `default_timeout_ms` — simulation timeout used by `wokwi_flash` and `nff wokwi run` when no `--timeout` flag is passed.
- `diagram_path` — optional path to a custom `diagram.json`. When `null`, a minimal diagram is auto-generated per board at simulation time.

---

## Claude Desktop Config

`nff init` appends this to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nff": {
      "command": "nff",
      "args": ["mcp"]
    }
  }
}
```

---

## Board Support

### USB Vendor ID Map
Used by `nff init` and `list_devices()` to auto-identify boards.

```python
BOARD_MAP = {
    ("2341", "0043"): {"name": "Arduino Uno",       "fqbn": "arduino:avr:uno"},
    ("2341", "0010"): {"name": "Arduino Mega 2560",  "fqbn": "arduino:avr:mega"},
    ("2341", "0036"): {"name": "Arduino Leonardo",   "fqbn": "arduino:avr:leonardo"},
    ("2341", "0058"): {"name": "Arduino Nano",       "fqbn": "arduino:avr:nano"},
    ("10c4", "ea60"): {"name": "ESP32 (CP210x)",     "fqbn": "esp32:esp32:esp32"},
    ("1a86", "7523"): {"name": "ESP32 (CH340)",      "fqbn": "esp32:esp32:esp32"},
    ("0403", "6001"): {"name": "ESP8266 (FTDI)",     "fqbn": "esp8266:esp8266:generic"},
}
```

### Toolchain Requirements
- **Arduino boards:** `arduino-cli` must be installed and boards/cores installed
- **ESP32/ESP8266:** `arduino-cli` with ESP32 core, or `esptool.py` for raw flashing

Install guide written in README and surfaced by `nff doctor`.

---

## Dependencies

```toml
# pyproject.toml
[project]
name = "nff"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pyserial>=3.5",
    "mcp>=1.0.0",
    "click>=8.0",
    "rich>=13.0",
]

[project.scripts]
nff = "nff.cli:main"
```

**External tools (not pip — user must install):**
- `arduino-cli` — https://arduino.github.io/arduino-cli
- `esptool` — `pip install esptool` (optional, for ESP-only workflows)
- `wokwi-cli` — https://github.com/wokwi/wokwi-cli (optional — needed only for `--sim` flag and `nff wokwi` commands; requires a Wokwi CI API token)

---

## Architecture Notes

### MCP Server Transport
Use `stdio` transport — Claude Code spawns `nff mcp` as a child process and communicates over stdin/stdout. Do not use HTTP or SSE transport for the local free tier.

```python
from mcp.server.stdio import stdio_server

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, ...)
```

### Serial Port Access on Linux
On Linux, the user may need to be in the `dialout` group:
```bash
sudo usermod -aG dialout $USER
```
`nff doctor` should detect this and print the fix if the port is inaccessible.

### Wokwi Integration Architecture

`nff/tools/wokwi.py` wraps `wokwi-cli` as a subprocess. The expected flow:

```
nff flash --sim  /  wokwi_flash MCP tool
        │
        ▼
arduino-cli compile  →  .elf binary in /tmp/nff_sketch/build/
        │
        ▼
auto-generate diagram.json  (if diagram_path is null in config)
        │
        ▼
wokwi-cli run --elf <path> --diagram <path> --timeout <ms>
        │
        ├── stdout → serial output lines
        └── exit code 0/1
```

**`wokwi.toml` format** (generated by `nff wokwi init`):
```toml
[wokwi]
version = 1
elf = ".pio/build/uno/firmware.elf"   # or arduino-cli build output path
firmware = ""
```

**Diagram generation:** `nff/tools/wokwi.py` contains a `generate_diagram(fqbn: str) -> dict` function that returns a minimal diagram with only the MCU chip and no wiring. Claude can extend it by calling `wokwi_get_diagram()` and editing the JSON before a simulation run.

**Token handling:** `WokwiRunner` (class in `nff/tools/wokwi.py`) reads the token from `WOKWI_CLI_TOKEN` env var first, then falls back to `config["wokwi"]["api_token"]`. It passes it to `wokwi-cli` via the `--token` flag. Never store the token in plaintext in a sketch directory.

**wokwi-cli not installed:** All Wokwi paths must check for `wokwi-cli` presence before running and return a clear human-readable error if missing (e.g. `"wokwi-cli not found — install it from https://github.com/wokwi/wokwi-cli and add a CI token via nff wokwi init"`). Do not raise — return the error string from MCP tools.

### Async vs Sync
- CLI commands (`nff flash`, `nff monitor`) can be synchronous
- MCP server must be async (the MCP Python SDK requires `asyncio`)
- Serial capture in MCP tools: use `asyncio.to_thread()` to run pyserial blocking calls without blocking the event loop

### Error Handling Philosophy
- Always return human-readable error messages from MCP tools — Claude reads them
- Never raise raw exceptions from MCP tool handlers — catch and return as error strings
- Exit codes: 0 = success, 1 = user error, 2 = dependency missing

---

## Development Setup

```bash
git clone https://github.com/GLechevalier/nff
cd nff
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run CLI locally
nff doctor

# Run tests
pytest tests/
```

---

## Coding Conventions

- **Formatter:** `black`
- **Linter:** `ruff`
- **Type hints:** required on all public functions
- **Docstrings:** Google style
- **CLI framework:** `click` (not argparse)
- **Terminal output:** `rich` for colors, tables, progress bars
- **No print() in library code** — use `rich.console.Console` or return strings from MCP tools

---

## Key Files to Write First

Build in this order:

1. `nff/config.py` — read/write `~/.nff/config.json` (include wokwi block)
2. `nff/tools/boards.py` — USB vendor ID detection + FQBN→Wokwi chip map
3. `nff/tools/serial.py` — pyserial read/write/capture
4. `nff/tools/toolchain.py` — arduino-cli subprocess wrappers
5. `nff/tools/wokwi.py` — `WokwiRunner` class, `generate_diagram()`, wokwi-cli subprocess wrapper
6. `nff/commands/doctor.py` — dependency checks (hardware + wokwi-cli + token)
7. `nff/commands/init.py` — device detection + config writing
8. `nff/commands/flash.py` — compile + upload, plus `--sim` flag routing to wokwi
9. `nff/commands/monitor.py` — interactive serial monitor
10. `nff/commands/wokwi.py` — `nff wokwi init` and `nff wokwi run` subcommands
11. `nff/mcp_server.py` — MCP server + all tool registrations (hardware + wokwi tools)
12. `nff/cli.py` — click entry point wiring everything together

---

## Out of Scope for v1

- OTA / WiFi flashing
- Cloud serial monitor
- Multi-device management
- CI/CD integration
- STM32 / nRF52 / RP2040 support
- Windows-specific serial port handling edge cases (best effort)
- Authentication / paid tier features
- Wokwi diagram editor GUI — users edit `diagram.json` by hand or via the Wokwi web editor; nff only generates a minimal stub
- Multi-component Wokwi circuits (auto-wiring peripherals) — out of scope; Claude can author the JSON manually using `wokwi_get_diagram()` as a starting point