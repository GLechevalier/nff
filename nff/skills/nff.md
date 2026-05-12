# nff — IoT CLI Bridge for Claude Code

`nff` connects Claude Code to embedded hardware (Arduino, ESP32, ESP8266) via USB or Wokwi simulation.
Use this skill whenever you need to write, compile, simulate, or flash a sketch.

---

## ⚠️ MANDATORY — Before Writing Any Sketch

Run through this checklist every time before touching a `.ino` file.

```
[ ] Identify the target board and its FQBN (see table in pipeline section)
[ ] Confirm sketches/<name>/<name>.ino does not already exist (avoid silent overwrites)
[ ] Open diagram.json and extract the full GPIO map:
      - list every component id, its type, and which esp:D<N> pin it connects to
      - note which components need special APIs (servo → LEDC, buzzer → tone(), etc.)
[ ] Resolve INPUT_PULLUP logic up front:
      buttons wired btn:1.l → GPIO, btn:2.l → GND
      read as LOW = pressed, HIGH = released — no exceptions
[ ] Decide blocking vs non-blocking before writing a single line:
      - single action with known duration → delay() is fine
      - concurrent inputs/outputs (read button WHILE showing LED sequence) → millis() state machine, NO delay()
[ ] Set a baud rate for Serial.begin() and write it down — it must match ~/.nff/config.json
[ ] Confirm no external library is needed. If one is, stop and ask the user to install it first.
      Built-in only: Wire, SPI, EEPROM, Preferences, tone(), ledcAttach/ledcWrite
[ ] Never pass raw code to MCP tools — file on disk is the only valid input
      WRONG: mcp__nff__flash(code="void setup()...")
      RIGHT: Write .ino file with Write tool → nff flash sketches/<name>
```

---

## Core Rules

- **Always use `nff flash` to compile/flash** — never call `arduino-cli` directly.
- **Never install libraries with `arduino-cli lib install`** — write sketches that use built-in APIs only, or ask the user to install the library first.
- For ESP32 servo control use `ledcAttach` / `ledcWrite` (built-in LEDC, no library needed).
- The working directory for all `nff` commands is the sketch folder (where `wokwi.toml` lives).

### Sketch-First Rule (mandatory — no exceptions)

**Before flashing anything, the sketch must exist as a real file on disk.**

1. Check whether `sketches/<name>/` exists. If not, create it.
2. Write the sketch to `sketches/<name>/<name>.ino` using the Write tool.
   The folder name must match the `.ino` filename — arduino-cli requirement.
3. Only then flash the path to that folder.

When iterating, use the Edit tool on the `.ino` file and re-flash the same path. The file is the source of truth.

---

## Prerequisites Check

Before any pipeline, run:

```bash
nff doctor
```

This verifies: arduino-cli, wokwi-cli, Wokwi token, connected device.

---

## Full Simulation Pipeline (no hardware)

Two distinct flows: **first run** (everything created from scratch) and **iteration** (sketch already exists).

---

### First Run

#### Step 1 — Write the sketch to disk

```
sketches/<name>/<name>.ino
```

Use the Write tool. Folder name must match `.ino` filename.

#### Step 2 — Initialize Wokwi project

```bash
nff wokwi init --board <fqbn>
```

Run this **inside** `sketches/<name>/` (it creates `wokwi.toml` and a stub `diagram.json`
in the current directory). If the diagram has already been designed separately (e.g. via
`/wokwi-diagram`), overwrite the generated `diagram.json` with the real one.

**Common FQBNs:**

| Board | FQBN |
|---|---|
| ESP32 DevKit V1 | `esp32:esp32:esp32` |
| Arduino Uno | `arduino:avr:uno` |
| Arduino Nano | `arduino:avr:nano` |
| ESP8266 | `esp8266:esp8266:generic` |

#### Step 3 — Compile

```bash
nff flash --sim sketches/<name> --board <fqbn>
```

Compiles the sketch and writes the ELF to:

```
sketches/<name>/build/<fqbn_dotted>/<name>.elf/<name>.ino.elf
```

`<fqbn_dotted>` = FQBN with `:` replaced by `.`

| FQBN | fqbn_dotted |
|---|---|
| `esp32:esp32:esp32` | `esp32.esp32.esp32` |
| `arduino:avr:uno` | `arduino.avr.uno` |
| `arduino:avr:nano` | `arduino.avr.nano` |

Full ELF path examples:
```
sketches/blink/build/esp32.esp32.esp32/blink.elf/blink.ino.elf
sketches/simon_game/build/esp32.esp32.esp32/simon_game.elf/simon_game.ino.elf
```

A timeout error at this step is **expected** — the headless sim starts and immediately times out
because nothing triggers the program. What matters is that compilation succeeded (exit code 0,
no `error:` lines in output).

#### Step 4 — Sync `wokwi.toml`

Open `sketches/<name>/wokwi.toml` and confirm **both** `elf` and `firmware` are present and correct:

```toml
[wokwi]
version = 1
elf      = "build/<fqbn_dotted>/<name>.ino.elf"
firmware = "build/<fqbn_dotted>/<name>.ino.merged.bin"
```

Both fields are **required** — `elf` drives the simulator; `firmware` is the merged binary for
flashing real hardware. `nff wokwi init` generates both automatically.

> Paths are **relative** to the folder containing `wokwi.toml` (i.e. `sketches/<name>/`).
> If either field is missing or wrong, fix it now — a wrong path causes a silent "no firmware"
> failure in the simulator with no helpful error message.

#### Step 5 — Run visual simulation

```bash
nff wokwi run --gui
```

Opens `diagram.json` in VS Code and auto-starts the simulator after ~3 s.
Interact with the circuit (press buttons, watch LEDs) and observe Serial Monitor output.

#### Step 6 — Headless simulation (capture serial output)

```bash
nff wokwi run --timeout 10000 --serial-log output.txt
```

`--timeout` in milliseconds. Serial output is written to `output.txt`. Useful for automated
verification without opening a GUI.

---

### Iteration (sketch already exists)

This is the loop to repeat for every fix or feature addition:

```
1. Edit .ino  →  Edit tool on sketches/<name>/<name>.ino
2. Recompile  →  nff flash --sim sketches/<name> --board <fqbn>
3. Simulate   →  nff wokwi run --gui   (or --serial-log for headless)
4. If wrong   →  back to step 1
```

**Do NOT re-run `nff wokwi init`** on iteration — it overwrites `wokwi.toml` and `diagram.json`.
**Do NOT re-write the `.ino` with Write tool** on iteration — use Edit tool to preserve the file
and avoid accidentally blanking code you wrote earlier.

Diagram-only change (no code change): skip steps 1–2, just run `nff wokwi run --gui` again.
The simulator always reads `diagram.json` fresh on each run.

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

### Simulation — symptom lookup

| Symptom | Cause | Fix |
|---|---|---|
| Compilation error | Sketch bug | Fix `.ino`, re-run `nff flash --sim` |
| Simulator opens but nothing happens | Wrong path in `wokwi.toml` | Check both `elf =` and `firmware =` — must match actual build output |
| Simulator opens but nothing happens | `diagram.json` not in same folder as `wokwi.toml` | Move or symlink `diagram.json` to `sketches/<name>/` |
| LED never lights | Wiring reversed (resistor after LED, not before) | Check chain: GPIO → R → LED_A … LED_C → GND |
| LED never lights | Cathode pin named `K` | Change to `C` in `diagram.json` |
| Button never fires | Active-LOW not handled | `digitalRead(pin) == LOW` means pressed with `INPUT_PULLUP` |
| Button never fires | Wrong pin wiring side | `btn:1.l` → GPIO, `btn:2.l` → GND — never reversed |
| Buzzer silent | Pins reversed | `buz1:1` → GND, `buz1:2` → GPIO signal |
| Servo jerks to wrong angle | Wrong duty values | Use 1638/4915/8192 for −90/0/+90° at 50 Hz 16-bit |
| Program locks up after first button press | `delay()` inside event handler | Replace with `millis()` state machine |
| Serial output garbled or empty | Baud mismatch | Match `Serial.begin(N)` ↔ `nff monitor --baud N` ↔ `~/.nff/config.json` |
| `nff flash --sim` times out | Expected — not an error | Ignore timeout; check only for `error:` lines |

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
