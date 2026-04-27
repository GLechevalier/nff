# nff — IoT CLI Bridge for Claude Code

`nff` connects Claude Code to embedded hardware (Arduino, ESP32, ESP8266) via USB or Wokwi simulation.
Use this skill whenever you need to write, compile, simulate, or flash a sketch.

---

## Core Rules

- **Always use `nff flash` to compile/flash** — never call `arduino-cli` directly.
- **Never install libraries with `arduino-cli lib install`** — write sketches that use built-in APIs only, or ask the user to install the library first.
- For ESP32 servo control use `ledcAttach` / `ledcWrite` (built-in LEDC, no library needed).
- The working directory for all `nff` commands is the project root (where `wokwi.toml` lives).

### Sketch-First Rule (mandatory — no exceptions)

**Before flashing anything, the sketch must exist as a real file on disk.**

1. Check whether `sketches/` exists in the project root. If not, create it.
2. Write the sketch to `sketches/<name>/<name>.ino` using the Write tool (the folder name must match the `.ino` filename — arduino-cli requirement).
3. Only then flash the path to that file.

**Never pass raw code strings to MCP tools.** The `code` parameter on `mcp__nff__flash` and `mcp__nff__wokwi_flash` must not be used. Those tools exist for programmatic callers; Claude Code must always write the file first and pass the sketch directory path instead.

```
WRONG: mcp__nff__flash(code="void setup()...")
RIGHT: Write file → nff flash sketches/<name>
```

When iterating on a sketch, edit the `.ino` file with the Edit tool, then re-flash the same path. The file is the source of truth.

---

## Prerequisites Check

Before any pipeline, run:

```bash
nff doctor
```

This verifies: arduino-cli, wokwi-cli, Wokwi token, connected device.

---

## Full Simulation Pipeline (no hardware)

### Step 1 — Write the sketch to disk

Check that `sketches/` exists in the project root; create it if not.
Write the sketch using the Write tool:

```
sketches/<name>/<name>.ino
```

The folder name must match the `.ino` filename (arduino-cli requirement).
Do not flash until this file exists on disk. When iterating, use the Edit tool on this file and re-flash — never overwrite with a new inline string.

### Step 2 — Initialize Wokwi project (first time only)

```bash
nff wokwi init --board <fqbn>
```

Creates `wokwi.toml` and a minimal `diagram.json` in the project root.
To add components (LEDs, buttons, servos, sensors), edit `diagram.json` directly.

**Common FQBNs:**
| Board | FQBN |
|---|---|
| ESP32 DevKit V1 | `esp32:esp32:esp32` |
| Arduino Uno | `arduino:avr:uno` |
| Arduino Nano | `arduino:avr:nano` |
| ESP8266 | `esp8266:esp8266:generic` |

### Step 3 — Compile (flash to simulator)

```bash
nff flash --sim sketches/<name> --board <fqbn>
```

This compiles the sketch and writes the ELF to:
`sketches/<name>/build/<fqbn_dotted>/<name>.elf/<name>.ino.elf`

The headless simulation will time out (expected — there's no button to click). What matters is that compilation succeeds.

### Step 4 — Update `wokwi.toml`

Make sure `wokwi.toml` points to the compiled ELF:

```toml
[wokwi]
version = 1
firmware = "sketches/<name>/build/<fqbn_dotted>/<name>.elf/<name>.ino.elf"
```

Where `<fqbn_dotted>` replaces `:` with `.` (e.g. `esp32.esp32.esp32`).

### Step 5 — Run visual simulation

```bash
nff wokwi run --gui
```

Opens `diagram.json` as a new tab in the existing VS Code window and auto-starts the Wokwi simulator after ~3 s.

### Step 6 — Run headless simulation (serial output only)

```bash
nff wokwi run
nff wokwi run --timeout 10000 --serial-log output.txt
```

---

## diagram.json — Component Reference

Always keep the serial monitor wired:

```json
["esp:TX0", "$serialMonitor:RX", "", []],
["esp:RX0", "$serialMonitor:TX", "", []]
```

**ESP32 pin naming:** `esp:D<gpio>` (e.g. `esp:D18`), `esp:GND.1`, `esp:GND.2`, `esp:3V3`, `esp:VIN`

**Common components and their pins — use `/wokwi-diagram` for the full reference:**

| Type | Pins |
|---|---|
| `wokwi-led` | `A` (anode), `C` (cathode — **not K**) |
| `wokwi-resistor` | `1`, `2` |
| `wokwi-pushbutton` | `1.l`, `1.r`, `2.l`, `2.r` |
| `wokwi-servo` | `PWM`, `V+`, `GND` |
| `wokwi-ntc-temperature-sensor` | `VCC`, `GND`, `OUT` |

```json
{ "type": "wokwi-led",         "id": "led1",   "attrs": { "color": "red" } }
{ "type": "wokwi-pushbutton",  "id": "btn1",   "attrs": { "color": "blue" } }
{ "type": "wokwi-servo",       "id": "srv1",   "attrs": { "minAngle": "-90", "maxAngle": "90" } }
{ "type": "wokwi-resistor",    "id": "r1",     "attrs": { "value": "220" } }
{ "type": "wokwi-ntc-temperature-sensor", "id": "tmp1", "attrs": {} }
```

---

## Servo (ESP32 LEDC — no library)

Wokwi servo maps its full range to **500 µs – 2500 µs** pulses.
With 50 Hz / 16-bit LEDC resolution (period = 20 000 µs, max count = 65535):

| Angle | Pulse | Duty count |
|---|---|---|
| min (−90°) | 500 µs | 1638 |
| center (0°) | 1500 µs | 4915 |
| max (+90°) | 2500 µs | 8192 |

```cpp
ledcAttach(SERVO_PIN, 50, 16);          // attach (ESP32 core 3.x API)
ledcWrite(SERVO_PIN, 4915);             // move to center
```

Always declare `minAngle: "-90"` and `maxAngle: "90"` in `diagram.json` for correct visual mapping.

---

## Full Real Hardware Pipeline

### Step 0 — Write the sketch to disk

Before touching the device, follow the Sketch-First Rule:
check for `sketches/` in the project root, create it if missing, and write
`sketches/<name>/<name>.ino` with the Write tool. Only proceed once the file exists.

### Step 1 — Detect device

```bash
nff init
```

Scans USB ports, identifies the board, writes `~/.nff/config.json`.

### Step 2 — Compile and flash

```bash
nff flash sketches/<name>
```

Uses board and port from config. Override with `--board <fqbn> --port <port>`.

```bash
nff flash sketches/<name> --board esp32:esp32:esp32 --port COM3
```

If upload fails with "Wrong boot mode detected":

```bash
nff flash sketches/<name> --manual-reset
```

Hold the BOOT button when prompted, release after upload starts.

### Step 3 — Monitor serial output

```bash
nff monitor
nff monitor --port COM3 --baud 115200
```

Ctrl+C to exit.

**Baud rate:** always match `--baud` (and the value in `~/.nff/config.json`) to the rate passed to
`Serial.begin()` in the sketch. Mismatched baud rates cause garbled or silent output and break
all serial debugging.

---

## Debugging Workflow

### Simulation issues

1. Compilation error → fix the sketch, re-run `nff flash --sim`
2. Serial output looks wrong → check `nff wokwi run --serial-log out.txt`, inspect `out.txt`
3. Component not responding → check `diagram.json` wiring (pin names, connection direction)
4. Servo wrong angle → verify duty cycle values match the 500–2500 µs Wokwi range
5. Button not registering → ensure `INPUT_PULLUP` is set and wiring goes `gpio → btn:1.l`, `GND → btn:2.l`

### Hardware issues

1. Port not found → run `nff init` to re-detect
2. Upload fails → try `--manual-reset`, check driver (CH340/CP210x)
3. Wrong output → use `nff monitor` to inspect live serial

---

## Key File Locations

| File | Purpose |
|---|---|
| `wokwi.toml` | Points to the compiled ELF for simulation |
| `diagram.json` | Circuit schematic for Wokwi |
| `sketches/<name>/<name>.ino` | Arduino sketch source |
| `~/.nff/config.json` | Default board, port, baud, Wokwi token |
