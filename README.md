# nff — Claude Code IoT Bridge

**nff** connects [Claude Code](https://claude.ai/code) to physical hardware over USB. It exposes your board as a set of MCP tools so Claude can autonomously write firmware, compile it, upload it, read serial output, and debug — all from a single conversation.

```
you: "Make the LED blink every 200 ms and print the state to serial"
Claude: [writes sketch] → [compiles] → [uploads to ESP32] → [reads serial] → done
```

**Supported boards (v1):** Arduino Uno · Mega · Nano · Leonardo · ESP32 (CP210x / CH340) · ESP8266 (FTDI)

---

## Quickstart

### 1. Install

```bash
pip install nff
```

### 2. Plug in your board, then run init

```bash
nff init
```

`nff init` does three things automatically:
- Detects your board by USB vendor/product ID
- Installs `arduino-cli` if it isn't on your system yet
- Registers the nff MCP server in `~/.claude/claude_desktop_config.json`

Expected output:

```
  ✓ Found: ESP32 (CP210x) on COM10 (vendor: 10c4, product: ea60)
  ✓ arduino-cli installed.
  ✓ Config written to C:\Users\you\.nff\config.json
  ✓ MCP config written to C:\Users\you\.claude\claude_desktop_config.json
```

### 3. Verify everything works

```bash
nff doctor
```

All checks should be green. If `arduino-cli` boards/cores are missing, install them:

```bash
arduino-cli core install arduino:avr      # Arduino boards
arduino-cli core install esp32:esp32      # ESP32
arduino-cli core install esp8266:esp8266  # ESP8266
```

### 4. Open Claude Code and start talking to your hardware

Restart Claude Code (or Claude Desktop) so it picks up the new MCP server. You're ready.

---

## CLI Reference

| Command | Description |
|---|---|
| `nff init` | Detect board, install arduino-cli, write config, register MCP server |
| `nff flash <file>` | Compile and upload a `.ino` sketch or sketch directory |
| `nff monitor` | Interactive serial monitor (Ctrl+C to exit) |
| `nff doctor` | Check all dependencies and configuration |
| `nff install-deps` | Re-download and install arduino-cli |
| `nff mcp` | Start the MCP server (called automatically by Claude Code) |

### `nff flash`

```bash
nff flash ./blink.ino
nff flash ./my_sketch/                       # sketch directory
nff flash ./blink.ino --board arduino:avr:uno --port COM3
nff flash ./blink.ino --manual-reset         # for boards with broken auto-reset
```

### `nff monitor`

```bash
nff monitor
nff monitor --port COM10 --baud 115200
nff monitor --timeout 10                     # stop after 10 seconds
```

---

## MCP Tools (what Claude can call)

Once registered, Claude Code has access to these tools:

| Tool | What it does |
|---|---|
| `list_devices()` | List all connected USB boards |
| `flash(code, board?, port?)` | Write, compile, and upload a sketch |
| `serial_read(duration_ms?, port?, baud?)` | Capture serial output for N ms |
| `serial_write(data, port?, baud?)` | Send a string to the device |
| `reset_device(port?)` | Toggle DTR to hardware-reset the board |
| `get_device_info(port?)` | Return port, board name, FQBN, baud rate |

All tools fall back to the default device in `~/.nff/config.json` when `port` and `board` are omitted.

---

## Config file

Stored at `~/.nff/config.json`, written by `nff init`, editable by hand:

```json
{
  "version": "1",
  "default_device": {
    "port": "COM10",
    "board": "ESP32 (CP210x)",
    "fqbn": "esp32:esp32:esp32",
    "baud": 115200
  }
}
```

---

## Supported Boards

| Board | Vendor ID | Product ID | FQBN |
|---|---|---|---|
| Arduino Uno | 2341 | 0043 | `arduino:avr:uno` |
| Arduino Mega 2560 | 2341 | 0010 | `arduino:avr:mega` |
| Arduino Leonardo | 2341 | 0036 | `arduino:avr:leonardo` |
| Arduino Nano | 2341 | 0058 | `arduino:avr:nano` |
| ESP32 (CP210x) | 10c4 | ea60 | `esp32:esp32:esp32` |
| ESP32 (CH340) | 1a86 | 7523 | `esp32:esp32:esp32` |
| ESP8266 (FTDI) | 0403 | 6001 | `esp8266:esp8266:generic` |

Board not listed? Open a PR — adding one is [two lines of code](CONTRIBUTING.md#adding-a-new-board).

---

## Linux: serial port permissions

On Linux, serial ports require the `dialout` group:

```bash
sudo usermod -aG dialout $USER
# then log out and back in
```

`nff doctor` will detect this and print the fix if your port is inaccessible.

---

## Repository structure

```
nff/
├── nff/
│   ├── cli.py              # Click entry point — routes subcommands
│   ├── mcp_server.py       # MCP server — registers all tools for Claude
│   ├── config.py           # Read/write ~/.nff/config.json
│   ├── commands/
│   │   ├── init.py         # nff init
│   │   ├── flash.py        # nff flash
│   │   ├── monitor.py      # nff monitor
│   │   └── doctor.py       # nff doctor
│   └── tools/
│       ├── boards.py       # USB vendor ID detection
│       ├── serial.py       # pyserial read/write/stream
│       ├── toolchain.py    # arduino-cli subprocess wrappers
│       └── installer.py    # arduino-cli auto-installer
├── scripts/
│   └── install_arduino_cli.py   # Standalone installer (thin wrapper)
├── sketches/
│   └── blink_esp32/        # Example sketch
├── tests/
├── pyproject.toml
└── CONTRIBUTING.md
```

---

## License

MIT — see [LICENSE](LICENSE).  
Copyright (c) 2026 Gauthier Lechevalier
