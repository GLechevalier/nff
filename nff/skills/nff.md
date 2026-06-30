# nff — IoT CLI Bridge for Claude Code

`nff` connects Claude Code to embedded hardware (Arduino, ESP32, ESP8266) over USB.
Use this skill whenever you need to write, compile, or flash a sketch to a real board.

> **Simulation** (running firmware without hardware in the Wokwi simulator) lives in the
> separate **nff-sim** package — see its README and the `wokwi-diagram` skill. This skill
> covers real hardware only.

---

## ⚠️ MANDATORY — Before Writing Any Sketch

Run through this checklist every time before touching a `.ino` file.

```
[ ] Identify the target board and its FQBN (see table in the pipeline section)
[ ] Confirm sketches/<name>/<name>.ino does not already exist (avoid silent overwrites)
[ ] Resolve INPUT_PULLUP logic up front:
      buttons wired one leg → GPIO, the other → GND
      read as LOW = pressed, HIGH = released — no exceptions
[ ] Decide blocking vs non-blocking before writing a single line:
      - single action with known duration → delay() is fine
      - concurrent inputs/outputs (read button WHILE showing LED sequence) → millis() state machine, NO delay()
[ ] Set a baud rate for Serial.begin() and write it down — it must match ~/.nff/config.json
[ ] Confirm no external library is needed. If one is, stop and ask the user to install it first.
      Built-in only: Wire, SPI, EEPROM, Preferences, tone(), ledcAttach/ledcWrite
[ ] Point nff tools at the file on disk, never at an inline code blob
      WRONG: mcp__nff__flash(code="void setup()...")
      RIGHT: Write .ino → mcp__nff__compile(sketch="sketches/<name>")  (no board needed)
             then  mcp__nff__flash(sketch="sketches/<name>")          (uploads)
      CLI equivalent: nff compile sketches/<name>   /   nff flash sketches/<name>
```

---

## Core Rules

- **Never call `arduino-cli` directly.** Everything you need is an nff tool:
  - To check a sketch builds → `nff compile` (MCP `compile`). No board, no port — this is the
    one to reach for whenever you just want to know "does it compile?".
  - To upload to real hardware → `nff flash` (MCP `flash`).
  There is no situation where dropping to raw `arduino-cli` is correct — if an nff tool seems to be
  missing a capability, say so rather than bypassing it.
- **Never install libraries with `arduino-cli lib install`** — write sketches that use built-in APIs only, or ask the user to install the library first.
- For ESP32 servo control use `ledcAttach` / `ledcWrite` (built-in LEDC, no library needed).

### compile vs flash — pick the right one

| Goal | Tool | Needs a board/port? | Returns |
|---|---|---|---|
| "Does it build?" | `compile` | No | `{ok, elf, image, errors}` — clean pass/fail |
| Upload to hardware | `flash` | Yes (port) | `OK: flash complete` / `ERROR: …` |

`compile` and `flash` are **separate** on purpose: compile never touches a port, so a missing/blocked
serial port can never make a pure build check fail. Compile first, fix any `errors`, then flash.

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

This verifies: arduino-cli and a connected device.

---

## Full Real Hardware Pipeline

### Step 0 — Write the sketch to disk

Before touching the device, follow the Sketch-First Rule:
check for `sketches/` in the project root, create it if missing, and write
`sketches/<name>/<name>.ino` with the Write tool. Only proceed once the file exists.

**Common FQBNs:**

| Board | FQBN |
|---|---|
| ESP32 DevKit V1 | `esp32:esp32:esp32` |
| Arduino Uno | `arduino:avr:uno` |
| Arduino Nano | `arduino:avr:nano` |
| ESP8266 | `esp8266:esp8266:generic` |

### Step 1 — Detect device

```bash
nff init
```

Scans USB ports, identifies the board, writes `~/.nff/config.json`.

### Step 2 — Compile and flash

Build-check first (no port, can't be derailed by a busy serial port):

```bash
nff compile sketches/<name>
```

Once it reports `Compile succeeded`, upload:

```bash
nff flash sketches/<name>
```

`nff flash` takes a sketch **folder** or a `.ino` file. It uses board and port from config;
override with `--board <fqbn> --port <port>`:

```bash
nff flash sketches/<name> --board esp32:esp32:esp32 --port COM3
```

If upload fails with "Wrong boot mode detected":

```bash
nff flash sketches/<name> --manual-reset
```

Hold the BOOT button when prompted, release after upload starts.

Build artifacts land in the **deterministic** build directory:

```
sketches/<name>/build/<fqbn_dotted>/<name>.ino.elf          ← ELF
sketches/<name>/build/<fqbn_dotted>/<name>.ino.merged.bin   ← flashable image
```

`<fqbn_dotted>` = FQBN with `:` replaced by `.` (e.g. `esp32:esp32:esp32` → `esp32.esp32.esp32`).
Don't guess the path — `nff compile` reports `elf:` and `image:` for you.

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

## Servo (ESP32 LEDC — no library)

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

---

## Debugging Workflow

### Hardware issues

1. Port not found → run `nff init` to re-detect
2. Upload fails → try `--manual-reset`, check driver (CH340/CP210x)
3. Wrong output → use `nff monitor` to inspect live serial
4. Compilation error → read the `error:` lines from `nff compile`, fix `.ino`, re-run `nff compile`
5. Serial output garbled or empty → baud mismatch: match `Serial.begin(N)` ↔ `nff monitor --baud N` ↔ `~/.nff/config.json`

### Live on-chip debugging (JTAG)

For ESP32-S3/C3/C6 (built-in USB-JTAG) you can pause a running device and inspect it at the
source level — like a real debugger, not just serial prints. This drives OpenOCD + GDB; the
binaries come from the PlatformIO toolchain (compile once for the board first).

MCP tools (and the matching `nff debug` REPL commands):

- `debug_start` — launch OpenOCD + GDB, load the last build's `firmware.elf`, reset+halt.
- `get_session_info`, `get_call_stack`, `get_variables`, `expand_variable` — inspect state.
- `get_registers`, `get_memory` — raw CPU registers and a memory hex dump.
- `evaluate` — evaluate a C/C++ expression (e.g. read `someGlobal.field`).
- `set_breakpoint` (`file:line` or function), `pause_execution`, `continue_execution`, `step`
  (`over`/`into`/`out`).
- `gdb_command` — raw GDB escape hatch.

**Workflow:** `nff compile <sketch>` → `nff flash <sketch>` → `debug_start` → the target halts;
then read registers/variables/stack, set a breakpoint, `continue_execution`, and inspect again.
**Most tools require a halted target** — call `pause_execution` (or hit a breakpoint) first.
Classic ESP32 / ESP32-S2 have no built-in JTAG: connect an external probe and pass
`interface=` (e.g. `ftdi/esp32_devkitj_v1`). `nff debug check` reports the detected
chip/OpenOCD/GDB/ELF without touching hardware.

---

## Key File Locations

| File | Purpose |
|---|---|
| `sketches/<name>/<name>.ino` | Arduino sketch source |
| `~/.nff/config.json` | Default board, port, baud |
