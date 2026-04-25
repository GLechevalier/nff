# nff — Claude Code IoT Bridge

## Project Overview

`nff` is an open source Python CLI tool that connects Claude Code to physical hardware devices via USB. It exposes hardware actions (flash, monitor, reset) as MCP tools so Claude Code can autonomously compile, upload, debug, and interact with embedded devices.

**Target devices (v1):** Arduino (Uno, Mega, Nano, Leonardo), ESP32, ESP8266  
**Connection:** USB only (OTA is a future paid feature)  
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
│   │   ├── flash.py        # nff flash
│   │   ├── monitor.py      # nff monitor
│   │   └── doctor.py       # nff doctor
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── serial.py       # Serial read/write/capture
│   │   ├── boards.py       # Board detection + USB vendor ID lookup
│   │   └── toolchain.py    # arduino-cli + esptool wrappers
│   └── config.py           # Config file (~/.nff/config.json)
├── tests/
│   ├── test_serial.py
│   ├── test_boards.py
│   └── test_mcp.py
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

### `nff flash <file> [--board <fqbn>] [--port <port>]`
Compiles and uploads firmware to the device.

```
nff flash ./blink.ino
nff flash ./main.ino --board esp32:esp32:esp32 --port /dev/ttyUSB0
```

**What it does:**
- Reads board + port from config if not passed as flags
- Calls `arduino-cli compile --fqbn <board> <sketch>`
- Calls `arduino-cli upload --fqbn <board> --port <port> <sketch>`
- Streams stdout/stderr to terminal in real time
- Returns exit code 0 on success, 1 on failure

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
Checks all dependencies and configuration.

```
nff doctor
→ ✓ Python 3.11.2
→ ✓ arduino-cli 0.35.0 found at /usr/local/bin/arduino-cli
→ ✓ esptool 4.6.2 found
→ ✓ pyserial 3.5 installed
→ ✓ Config file found at ~/.nff/config.json
→ ✓ Device detected: Arduino Uno on /dev/ttyUSB0
→ ✗ Claude Desktop config not found — run nff init
```

**What it checks:**
- Python version >= 3.10
- `arduino-cli` installed and in PATH
- `esptool` installed (`pip install esptool`)
- `pyserial` installed
- `~/.nff/config.json` exists and is valid
- USB device is connected and port is accessible
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
  }
}
```

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

1. `nff/config.py` — read/write `~/.nff/config.json`
2. `nff/tools/boards.py` — USB vendor ID detection
3. `nff/tools/serial.py` — pyserial read/write/capture
4. `nff/tools/toolchain.py` — arduino-cli subprocess wrappers
5. `nff/commands/doctor.py` — dependency checks
6. `nff/commands/init.py` — device detection + config writing
7. `nff/commands/flash.py` — compile + upload
8. `nff/commands/monitor.py` — interactive serial monitor
9. `nff/mcp_server.py` — MCP server + all tool registrations
10. `nff/cli.py` — click entry point wiring everything together

---

## Out of Scope for v1

- OTA / WiFi flashing
- Cloud serial monitor
- Multi-device management
- CI/CD integration
- STM32 / nRF52 / RP2040 support
- Windows-specific serial port handling edge cases (best effort)
- Authentication / paid tier features