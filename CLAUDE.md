# nff — Wokwi Simulation Context

## Hard Rules
- Always use `nff flash --sim` to compile — never call arduino-cli directly.
- Always use `nff wokwi run` or `nff wokwi run --gui` to simulate.
- Never install libraries with arduino-cli. Use built-in ESP32 APIs only,
  or ask the user to install the library first.
- For ESP32 servo/PWM use ledcAttach + ledcWrite (built-in LEDC, no library).

## Project
- Board : arduino:avr:uno
- FQBN  : arduino:avr:uno
- Chip  : wokwi-arduino-uno

---

## Simulation Pipeline

```
1. Write sketch      sketches/<name>/<name>.ino
2. Edit circuit      diagram.json  (add components + wiring)
3. Compile           nff flash --sim sketches/<name> --board arduino:avr:uno
4. Visual sim        nff wokwi run --gui
   Headless sim      nff wokwi run [--timeout MS] [--serial-log FILE]
5. Fix bugs, repeat from step 3
```

wokwi.toml must point to the compiled ELF:
  firmware = "sketches/<name>/build/arduino.avr.uno/<name>.elf/<name>.ino.elf"

---

## diagram.json — Component Wiring

Always wire the serial monitor:
  ["esp:TX0", "$serialMonitor:RX", "", []]
  ["esp:RX0", "$serialMonitor:TX", "", []]

ESP32 pin names: esp:D<gpio>  esp:GND.1  esp:GND.2  esp:3V3  esp:VIN

Common components:
  wokwi-led          attrs: color (red/green/blue/yellow)
  wokwi-pushbutton   attrs: color — pins: btn:1.l (gpio side), btn:2.l (GND side)
  wokwi-servo        attrs: minAngle "-90", maxAngle "90" — pins: PWM, V+, GND
  wokwi-resistor     attrs: value (ohms)

Pushbutton wiring (with INPUT_PULLUP in sketch):
  ["esp:D15", "btn1:1.l", "green", []]
  ["esp:GND.2", "btn1:2.l", "black", []]

Servo connection:
  ["esp:D18",  "srv1:PWM", "orange", []]
  ["esp:3V3",  "srv1:V+",  "red",    []]
  ["esp:GND.1","srv1:GND", "black",  []]

---

## ESP32 Servo — LEDC (no library required)

Wokwi servo maps its full range to 500 µs – 2500 µs.
50 Hz / 16-bit resolution (max count 65 535, period 20 000 µs):

  −90°  →  duty 1638   (500 µs)
    0°  →  duty 4915  (1500 µs)
  +90°  →  duty 8192  (2500 µs)

```cpp
ledcAttach(SERVO_PIN, 50, 16);   // ESP32 Arduino core 3.x
ledcWrite(SERVO_PIN, 4915);      // center
```

Always set minAngle: "-90" and maxAngle: "90" on wokwi-servo in diagram.json.

---

## Debugging

- Compile error     → fix sketch, re-run nff flash --sim
- Wrong output      → nff wokwi run --serial-log out.txt, inspect out.txt
- Component silent  → check diagram.json pin names and connection direction
- Servo wrong angle → verify duty values match the 500–2500 µs Wokwi range
- Button not firing → INPUT_PULLUP + wiring gpio→btn:1.l, GND→btn:2.l

---

# nff — Rust Architecture

## Status

The Python `nff` binary has been fully replaced by a compiled Rust binary — single executable,
no Python runtime required for end users, stronger types, better cross-platform packaging.

The MCP server is now native Rust (`nff-rs/nff/src/mcp_server.rs`, rmcp crate). Wokwi
integration is also native Rust (`tools/wokwi.rs`). Only `nff test` still delegates to the
Python package via subprocess.

**Adding a new MCP tool:** add it to `nff-rs/nff/src/mcp_server.rs` — implement a method on
`NffServer` with the `#[tool(...)]` attribute. Do not edit `nff/nff/mcp_server.py`; it is
superseded.

## Migration Scope

**IN (rewrite in Rust):**
- CLI entry point and all command definitions
- `nff/nff/config.py` → `tools/config.rs`
- `nff/nff/tools/serial.py` → `tools/serial.rs`
- `nff/nff/tools/boards.py` → `tools/boards.rs`
- `nff/nff/tools/toolchain.py` → `tools/toolchain.rs`
- `nff/nff/tools/installer.py` → `tools/installer.rs`
- All commands: `flash`, `init`, `monitor`, `doctor`, `clean`, `connect`, `ota`, `install-deps`
- `commands/mcp.rs` (calls `mcp_server::run()` — native Rust MCP server, no Python)

**OUT (keep in Python):**
- `nff test` command only — delegates to `python -m nff test` via subprocess

## Rust Project Layout

Create at `nff/nff-rs/` (sibling to `nff/nff/`):

```
nff/nff-rs/
├── Cargo.toml              (workspace root)
└── nff/
    ├── Cargo.toml
    └── src/
        ├── main.rs
        ├── cli.rs
        ├── commands/
        │   ├── mod.rs
        │   ├── flash.rs        (replaces commands/flash.py)
        │   ├── init.rs         (replaces commands/init.py)
        │   ├── monitor.rs      (replaces commands/monitor.py)
        │   ├── doctor.rs       (replaces commands/doctor.py)
        │   ├── clean.rs        (replaces commands/clean.py)
        │   ├── connect.rs      (replaces commands/connect.py)
        │   ├── ota.rs          (replaces commands/ota.py)
        │   ├── install_deps.rs (replaces install-deps command in cli.py)
        │   └── mcp.rs          (spawns Python MCP server)
        └── tools/
            ├── mod.rs
            ├── config.rs       (replaces config.py)
            ├── serial.rs       (replaces tools/serial.py)
            ├── boards.rs       (replaces tools/boards.py)
            ├── toolchain.rs    (replaces tools/toolchain.py)
            └── installer.rs    (replaces tools/installer.py)
```

Workspace `Cargo.toml`:
```toml
[workspace]
members = ["nff"]
resolver = "2"
```

## Cargo.toml Dependencies

```toml
[package]
name = "nff"
version = "0.2.16"   # keep in sync with pyproject.toml
edition = "2021"

[[bin]]
name = "nff"
path = "src/main.rs"

[dependencies]
clap        = { version = "4", features = ["derive"] }
serialport  = "4"
rusb        = "0.9"
serde       = { version = "1", features = ["derive"] }
serde_json  = "1"
dirs        = "5"
indicatif   = "0.17"
console     = "0.15"
reqwest     = { version = "0.12", features = ["blocking"] }
zip         = "2"
flate2      = "1"
tar         = "0.4"
which       = "6"
thiserror   = "1"
anyhow      = "1"

[target.'cfg(windows)'.dependencies]
winreg      = "0.52"
```

## CLI Command Hierarchy — src/cli.rs

Use `clap` derive. Mirror every flag and option from the Python Click commands exactly.

```rust
use clap::{Parser, Subcommand, Args};

#[derive(Parser)]
#[command(name = "nff", version)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    Init(InitArgs),
    Flash(FlashArgs),
    Monitor(MonitorArgs),
    Wokwi(WokwiCommand),
    Doctor,
    Clean,
    Test,
    Connect,
    Ota,
    #[command(name = "install-deps")]
    InstallDeps(InstallDepsArgs),
    Mcp,
}

#[derive(Args)]
pub struct InitArgs {
    #[arg(long, value_name = "PORT")]
    pub port: Option<String>,
    #[arg(long, default_value = "9600")]
    pub baud: u32,
    #[arg(long)]
    pub force: bool,
}

#[derive(Args)]
pub struct FlashArgs {
    pub file: std::path::PathBuf,   // required, must exist
    #[arg(long, value_name = "FQBN")]
    pub board: Option<String>,
    #[arg(long, value_name = "PORT")]
    pub port: Option<String>,
    #[arg(long)]
    pub baud: Option<u32>,
    #[arg(long)]
    pub manual_reset: bool,
    #[arg(long)]
    pub sim: bool,
    #[arg(long, default_value = "5000", value_name = "MS")]
    pub sim_timeout: u32,
}

#[derive(Args)]
pub struct MonitorArgs {
    #[arg(long, value_name = "PORT")]
    pub port: Option<String>,
    #[arg(long)]
    pub baud: Option<u32>,
    #[arg(long, value_name = "SECONDS")]
    pub timeout: Option<f64>,
}

#[derive(Args)]
pub struct InstallDepsArgs {
    #[arg(long)]
    pub force: bool,
    #[arg(long)]
    pub skip_wokwi: bool,
}

// Wokwi is a subcommand group; its subcommands delegate to Python.
#[derive(Args)]
pub struct WokwiCommand {
    #[command(subcommand)]
    pub sub: WokwiSubcommands,
}

#[derive(Subcommand)]
pub enum WokwiSubcommands {
    Init(WokwiInitArgs),
    Run(WokwiRunArgs),
}
// (WokwiInitArgs, WokwiRunArgs mirror the Python options)
```

## Module-by-Module Migration

### tools/config.rs (from config.py)

Config path: `dirs::home_dir().unwrap() / ".nff" / "config.json"`

```rust
#[derive(Serialize, Deserialize)]
pub struct Config {
    pub version: String,
    pub default_device: DeviceConfig,
    pub wokwi: WokwiConfig,
}

#[derive(Serialize, Deserialize, Default)]
pub struct DeviceConfig {
    pub port: Option<String>,
    pub board: Option<String>,
    pub fqbn: Option<String>,
    pub baud: u32,   // default 9600
}

#[derive(Serialize, Deserialize, Default)]
pub struct WokwiConfig {
    pub api_token: Option<String>,
    pub default_timeout_ms: u32,   // default 5000
    pub diagram_path: Option<String>,
}
```

Atomic write pattern:
```rust
let tmp = config_path.with_extension("json.tmp");
fs::write(&tmp, serde_json::to_string_pretty(&config)?)?;
fs::rename(tmp, config_path)?;
```

Public API to implement (mirrors config.py):
- `load() -> Result<Config>`
- `save(config: &Config) -> Result<()>`
- `get_default_device() -> Result<DeviceConfig>`
- `set_default_device(port, board, fqbn, baud) -> Result<()>`
- `get_wokwi_config() -> Result<WokwiConfig>`
- `set_wokwi_token(token: Option<&str>) -> Result<()>`
- `set_wokwi_diagram_path(path: Option<&str>) -> Result<()>`
- `set_wokwi_timeout(ms: u32) -> Result<()>`
- `exists() -> bool`

### tools/boards.rs (from tools/boards.py)

`serialport::available_ports()` returns `Vec<SerialPortInfo>` where each entry has an optional
`SerialPortType::UsbPort(UsbPortInfo { vid: u16, pid: u16, .. })`.

```rust
pub const BOARD_MAP: &[(u16, u16, &str, &str, Option<&str>)] = &[
    (0x2341, 0x0043, "Arduino Uno",       "arduino:avr:uno",         Some("wokwi-arduino-uno")),
    (0x2341, 0x0010, "Arduino Mega 2560", "arduino:avr:mega",        Some("wokwi-arduino-mega")),
    (0x2341, 0x0036, "Arduino Leonardo",  "arduino:avr:leonardo",    Some("wokwi-arduino-leonardo")),
    (0x2341, 0x0058, "Arduino Nano",      "arduino:avr:nano",        Some("wokwi-arduino-nano")),
    (0x10c4, 0xea60, "ESP32 (CP210x)",    "esp32:esp32:esp32",       Some("wokwi-esp32-devkit-v1")),
    (0x1a86, 0x7523, "ESP32 (CH340)",     "esp32:esp32:esp32",       Some("wokwi-esp32-devkit-v1")),
    (0x0403, 0x6001, "ESP8266 (FTDI)",    "esp8266:esp8266:generic", Some("wokwi-esp8266")),
];

pub struct DetectedDevice {
    pub port: String,
    pub board: String,
    pub fqbn: String,
    pub vendor_id: String,   // 4-char zero-padded hex, lowercase
    pub product_id: String,
    pub wokwi_chip: Option<String>,
}

pub fn list_devices() -> Vec<DetectedDevice> { ... }
pub fn find_device(port: Option<&str>) -> Option<DetectedDevice> { ... }
```

### tools/serial.rs (from tools/serial.py)

```rust
use serialport::SerialPort;
use std::time::{Duration, Instant};
use std::io::{BufRead, BufReader, Write};

// Open with 100ms read timeout (check deadline per iteration, like Python)
fn open(port: &str, baud: u32) -> Result<Box<dyn SerialPort>, SerialError> {
    serialport::new(port, baud)
        .timeout(Duration::from_millis(100))
        .open()
        .map_err(SerialError::Open)
}

pub fn serial_read(duration_ms: u64, port: Option<&str>, baud: Option<u32>) -> String { ... }
// Reads until deadline, returns captured UTF-8 string or "ERROR: ..."

pub fn serial_write(data: &str, port: Option<&str>, baud: Option<u32>) -> String { ... }
// Appends \n if missing, returns "OK: wrote N byte(s) to <port>" or "ERROR: ..."

pub fn reset_device(port: Option<&str>) -> String { ... }
// port.write_data_terminal_ready(false) + sleep 50ms + write_data_terminal_ready(true)
// Returns "OK: reset <port> via DTR toggle" or "ERROR: ..."

pub fn stream_lines(port: Option<&str>, baud: Option<u32>, timeout_s: Option<f64>)
    -> impl Iterator<Item = String> { ... }
// BufReader::new(serial_port).lines(), deadline-terminated

fn resolve_port(opt: Option<&str>) -> Result<String, SerialError> { ... }
fn resolve_baud(opt: Option<u32>) -> Result<u32, SerialError> { ... }
```

### tools/toolchain.rs (from tools/toolchain.py)

Sketch directory: `std::env::temp_dir() / "nff_sketch"`

```rust
pub struct RunResult {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
    pub returncode: i32,
}
impl RunResult {
    pub fn output(&self) -> String { /* concat stdout + stderr, trimmed */ }
}

// Tool discovery
pub fn find_arduino_cli() -> Option<PathBuf> {
    // 1. which::which("arduino-cli")
    // 2. Windows: %LOCALAPPDATA%\Programs\arduino-cli\arduino-cli.exe
    // 3. Unix: ~/.local/bin/arduino-cli
}

pub fn find_esptool() -> Option<PathBuf> {
    // which::which("esptool.py") then which::which("esptool")
}

pub fn find_wokwi_cli() -> Option<PathBuf> {
    // which::which("wokwi-cli")
    // Windows fallback: %LOCALAPPDATA%\Programs\wokwi-cli\wokwi-cli.exe
    // Unix fallback: ~/.local/bin/wokwi-cli
}

// Sketch management
pub fn write_sketch(code: &str, sketch_dir: Option<&Path>) -> Result<PathBuf, ToolchainError> {
    // Writes code to <sketch_dir>/<sketch_dir.name>.ino
}

pub fn elf_path_for(sketch_dir: &Path, fqbn: &str) -> PathBuf {
    // sketch_dir/build/<fqbn.replace(':','.')>/<sketch_name>.elf
}

// Subprocess wrappers — all use std::process::Command with 120s timeout
pub fn compile_sketch(sketch_dir: &Path, fqbn: &str) -> Result<RunResult, ToolchainError> {
    // arduino-cli compile --fqbn <fqbn> --build-path <build_path> <sketch_dir>
}

pub fn upload_sketch(sketch_dir: &Path, fqbn: &str, port: &str) -> Result<RunResult, ToolchainError> {
    // arduino-cli upload --fqbn <fqbn> --port <port> <sketch_dir>
}

// Streaming variants for progress display
pub struct ProcessStream { cmd: Vec<String>, pub returncode: Option<i32> }
impl Iterator for ProcessStream { type Item = String; ... }
// Uses Command::stdout(Stdio::piped()) + BufReader::lines()

pub fn stream_compile(sketch_dir: &Path, fqbn: &str) -> ProcessStream { ... }
pub fn stream_upload(sketch_dir: &Path, fqbn: &str, port: &str) -> ProcessStream { ... }

// Combined flash: write_sketch → compile → upload
pub fn flash(code: &str, fqbn: &str, port: &str) -> String {
    // Returns "OK: flash complete\n---compile---\n...\n---upload---\n..."
    // or "ERROR: ..."
}

// esptool / espflash wrapper
pub fn esptool_flash(port: &str, bin_path: &Path, baud: u32, address: &str) -> String {
    // Prefers subprocess espflash/esptool, falls back to "python -m esptool"
    // Default address "0x0"
}
```

### tools/installer.rs (from tools/installer.py)

Arduino CLI download base: `https://downloads.arduino.cc/arduino-cli/arduino-cli_latest`

```rust
fn asset_url() -> (&'static str, &'static str) {
    // Returns (url, extension) based on std::env::consts::{OS, ARCH}
    // Windows x86_64 → "_Windows_64bit.zip"
    // Windows other  → "_Windows_32bit.zip"
    // macOS arm64    → "_macOS_ARM64.tar.gz"
    // macOS other    → "_macOS_64bit.tar.gz"
    // Linux x86_64   → "_Linux_64bit.tar.gz"
    // Linux aarch64  → "_Linux_ARM64.tar.gz"
    // Linux arm      → "_Linux_ARMv7.tar.gz"
}

fn install_dir() -> PathBuf {
    // Windows: %LOCALAPPDATA%\Programs\arduino-cli
    // Unix: ~/.local/bin
}

pub fn install(force: bool) -> Result<PathBuf> {
    // 1. reqwest::blocking::get(url)?.bytes()? → write to tempfile
    // 2. Extract binary: zip (ZipArchive) or tar.gz (flate2 GzDecoder + tar::Archive)
    // 3. Unix: set executable bit (std::os::unix::fs::PermissionsExt)
    // 4. ensure_on_path(install_dir)
    // Returns path to extracted executable
}

fn ensure_on_path(dir: &Path) {
    // Windows: winreg read/write HKCU\Environment PATH (semicolon-separated)
    // Unix: append 'export PATH="$PATH:/dir"' to first of ~/.bashrc, ~/.zshrc, ~/.profile
    // Both: update std::env::var("PATH") for current process
}

pub fn verify(exe: &Path) -> bool {
    // Command::new(exe).arg("version").output().map(|o| o.status.success()).unwrap_or(false)
}
```

### mcp_server.rs

`nff mcp` starts the MCP server natively in Rust via the `rmcp` crate on stdio. No Python needed.

```rust
pub async fn run() -> anyhow::Result<()> {
    let service = NffServer.serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}
```

Add new tools as `async fn` methods on `NffServer` with `#[tool(description = "...")]`.

### commands/flash.rs (from commands/flash.py)

```
1. Resolve FQBN: --board arg → config::get_default_device().fqbn → error
2. Resolve port: --port arg → boards::find_device() → config default → error
3. If --manual-reset: print prompt, wait for Enter
4. If --sim: spawn Python `nff wokwi run --timeout <sim_timeout>` via subprocess
5. Else:
   a. toolchain::stream_compile(sketch_dir, fqbn) → print each line (indicatif spinner)
   b. toolchain::stream_upload(sketch_dir, fqbn, port) → print each line
   c. Check ProcessStream.returncode; exit non-zero on failure
```

### commands/init.rs (from commands/init.py)

```
1. Interactive prompt (stdin): "1) Real board  2) Simulation"
2. If real board:
   a. boards::list_devices() — list connected devices
   b. User picks port (or auto-detect if only one)
   c. config::set_default_device(port, board, fqbn, baud)
   d. installer::install(force=false) if arduino-cli not found
3. If simulation:
   a. Offer 6 Wokwi board choices (same list as Python)
   b. config::set_default_device("", board, fqbn, 9600)
4. Register MCP with Claude Code:
   Command::new("claude").args(["mcp", "add", "--scope", "user",
       "nff", current_exe_path, "mcp"])
5. Print success summary
```

### commands/monitor.rs (from commands/monitor.py)

```rust
pub fn run(args: &MonitorArgs) -> anyhow::Result<()> {
    let port = serial::resolve_port(args.port.as_deref())?;
    let baud = serial::resolve_baud(args.baud)?;
    for line in serial::stream_lines(Some(&port), Some(baud), args.timeout) {
        println!("{line}");
    }
    Ok(())
}
```

## Error Handling Convention

Domain errors use `thiserror`:
```rust
#[derive(thiserror::Error, Debug)]
pub enum SerialError { ... }

#[derive(thiserror::Error, Debug)]
pub enum ToolchainError { ... }

#[derive(thiserror::Error, Debug)]
pub enum ConfigError { ... }
```

Command-level functions return `anyhow::Result<()>` and use `?` for propagation.

MCP-facing tool functions (called via Python MCP server through subprocess) must return
`"OK: ..."` or `"ERROR: ..."` strings — same protocol as Python, so the existing
`mcp_server.py` can call the Rust binary without changes.

## Completed Migration Phases

All phases complete. Run `cargo test && cargo clippy -- -D warnings` to verify.

1. ~~Bootstrap~~ — workspace Cargo.toml, all deps, builds clean
2. ~~config.rs~~ — `~/.nff/config.json` read/write round-trip
3. ~~boards.rs~~ — USB enumeration via `serialport`
4. ~~serial.rs~~ — read/write/reset via `serialport`
5. ~~toolchain.rs~~ — arduino-cli subprocess wrappers
6. ~~installer.rs~~ — download + extract (zip on Windows, tar.gz on Unix)
7. ~~cli.rs + main.rs~~ — clap, all commands wired
8. ~~commands~~ — `init`, `flash`, `monitor`, `doctor`, `clean`, `install_deps`, `mcp`, `connect`, `ota`
9. ~~mcp_server.rs~~ — native Rust MCP server via `rmcp` (no Python subprocess)
10. ~~tools/wokwi.rs~~ — Wokwi simulation tools in Rust

## Verification

`cargo test && cargo clippy -- -D warnings`

End-to-end smoke test:
- [ ] `./nff --version` prints version string matching `Cargo.toml`
- [ ] `./nff init` creates `~/.nff/config.json` with correct schema
- [ ] `./nff flash <sketch.ino>` compiles and uploads
- [ ] `./nff monitor --timeout 5` streams serial for 5 s then exits cleanly
- [ ] `./nff install-deps` downloads and installs arduino-cli
- [ ] `./nff mcp` starts native Rust MCP server on stdio; `list_devices` tool returns data from Claude Code
- [ ] `cargo build --release` produces a single binary that runs on a clean machine without Python

## Key Source Files (reference during migration)

| Rust target | Python source |
|---|---|
| `tools/config.rs` | `nff/nff/config.py` |
| `tools/boards.rs` | `nff/nff/tools/boards.py` |
| `tools/serial.rs` | `nff/nff/tools/serial.py` |
| `tools/toolchain.rs` | `nff/nff/tools/toolchain.py` |
| `tools/installer.rs` | `nff/nff/tools/installer.py` |
| `commands/flash.rs` | `nff/nff/commands/flash.py` |
| `commands/init.rs` | `nff/nff/commands/init.py` |
| `commands/monitor.rs` | `nff/nff/commands/monitor.py` |
| `cli.rs` | `nff/nff/cli.py` |
| `mcp_server.rs` | Native Rust MCP server (rmcp) — supersedes `nff/nff/mcp_server.py` |
