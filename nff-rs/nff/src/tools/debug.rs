//! Live on-chip debugging for ESP32 and STM32 — OpenOCD (JTAG/SWD) + GDB/MI bridge.
//!
//! nff's equivalent of a Cortex-Debug bridge: halt a running MCU and inspect it at the
//! source level (registers, memory, locals, the call stack), set breakpoints, step, and
//! run raw GDB. nff owns the whole stack — it launches OpenOCD (a GDB *server* on :3333),
//! launches the chip's GDB in machine-interface (MI) mode, loads the last build's
//! `firmware.elf` for symbols, and `reset halt`s the target.
//!
//! Binaries are reused from PlatformIO's package cache (`~/.platformio/packages`), falling
//! back to `PATH`. There is no `pygdbmi`-equivalent crate, so the MI protocol is driven by
//! hand: spawn `gdb --interpreter=mi3`, write commands to stdin, and parse the `^done`/
//! `^error`/`~"..."`/`(gdb)` records from stdout (see [`MiParser`] + [`DebugSession::exec`]).

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Map, Value};
use thiserror::Error;

const GDB_PORT: u16 = 3333;
const OPENOCD_STARTUP_TIMEOUT_SECS: u64 = 15;
const MI_READ_TIMEOUT_SECS: u64 = 20;

/// Chips with a built-in USB-Serial-JTAG controller (one-file `board/<chip>-builtin.cfg`).
const BUILTIN_JTAG: &[&str] = &["esp32s3", "esp32c3", "esp32c6", "esp32c2", "esp32h2", "esp32p4"];
/// ESP RISC-V parts use riscv32-esp-elf-gdb; the rest of ESP32 is Xtensa.
const RISCV_CHIPS: &[&str] = &["esp32c3", "esp32c6", "esp32c2", "esp32h2", "esp32p4"];
/// ESP32 chip tokens, most-specific first so "esp32s3" wins over "esp32".
const CHIP_TOKENS: &[&str] = &[
    "esp32s3", "esp32s2", "esp32c6", "esp32c3", "esp32c2", "esp32h2", "esp32p4", "esp32",
];

/// STM32 family ("f4") → the OpenOCD `target/*.cfg` basename.
const STM32_TARGETS: &[(&str, &str)] = &[
    ("f0", "stm32f0x"), ("f1", "stm32f1x"), ("f2", "stm32f2x"), ("f3", "stm32f3x"),
    ("f4", "stm32f4x"), ("f7", "stm32f7x"), ("g0", "stm32g0x"), ("g4", "stm32g4x"),
    ("h7", "stm32h7x"), ("l0", "stm32l0"), ("l1", "stm32l1"), ("l4", "stm32l4x"),
    ("l5", "stm32l5x"), ("u5", "stm32u5x"), ("wb", "stm32wbx"), ("wl", "stm32wlx"),
];

#[derive(Error, Debug)]
pub enum DebugError {
    #[error("{0}")]
    Other(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

fn err(msg: impl Into<String>) -> DebugError {
    DebugError::Other(msg.into())
}

// ---------------------------------------------------------------------------
// Chip / board resolution
// ---------------------------------------------------------------------------

fn norm(s: &str) -> String {
    s.to_lowercase()
        .chars()
        .filter(|c| *c != '-' && *c != ':' && *c != '_')
        .collect()
}

/// The toolchain family for a chip id: "arm" (STM32), "riscv", or "xtensa".
pub fn family(chip: &str) -> &'static str {
    if chip.starts_with("stm32") || chip.starts_with("arm") {
        "arm"
    } else if RISCV_CHIPS.contains(&chip) {
        "riscv"
    } else {
        "xtensa"
    }
}

/// Extract the STM32 family digit-pair (e.g. "f4") from board/FQBN candidates.
fn stm32_family(candidates: &[String]) -> String {
    for raw in candidates {
        let n = norm(raw);
        // After an stm32/nucleo/bluepill/disco anchor, the first <letter><digit> is the family.
        for anchor in ["stm32", "nucleo", "bluepill", "disco"] {
            if let Some(pos) = n.find(anchor) {
                let bytes = n.as_bytes();
                let mut i = pos + anchor.len();
                while i + 1 < bytes.len() {
                    let (a, b) = (bytes[i] as char, bytes[i + 1] as char);
                    if matches!(a, 'f' | 'g' | 'h' | 'l' | 'u' | 'w') && b.is_ascii_digit() {
                        return format!("{a}{b}");
                    }
                    i += 1;
                }
            }
        }
    }
    String::new()
}

/// The PlatformIO board id (or FQBN) of the first connected device, so `nff debug`
/// targets the plugged-in board even before `nff init` records it.
pub fn autodetect_board() -> Option<String> {
    for d in crate::tools::boards::list_devices() {
        if let Some(pio) = d.pio_board.filter(|s| !s.is_empty()) {
            return Some(pio);
        }
        if !d.fqbn.is_empty() {
            return Some(d.fqbn);
        }
        if !d.board.is_empty() {
            return Some(d.board);
        }
    }
    None
}

/// Best-effort chip id: an ESP32 family ("esp32s3"…), an STM32 family ("stm32f4"), or
/// "esp32" as a default. Looks at the passed board, the configured board, and the FQBN.
pub fn detect_chip(board: Option<String>) -> String {
    let mut candidates: Vec<String> = Vec::new();
    if let Some(b) = board {
        candidates.push(b);
    }
    candidates.push(crate::tools::toolchain::configured_board());
    if let Ok(d) = crate::tools::config::get_default_device() {
        if let Some(f) = d.fqbn {
            candidates.push(f);
        }
    }
    let norms: Vec<String> = candidates.iter().map(|c| norm(c)).collect();
    if norms
        .iter()
        .any(|n| n.contains("stm32") || n.contains("nucleo") || n.contains("bluepill"))
    {
        return format!("stm32{}", stm32_family(&candidates));
    }
    for n in &norms {
        for token in CHIP_TOKENS {
            if n.contains(token) {
                return (*token).to_string();
            }
        }
    }
    "esp32".to_string()
}

// ---------------------------------------------------------------------------
// Binary / config discovery
// ---------------------------------------------------------------------------

fn platformio_packages() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".platformio")
        .join("packages")
}

fn debug_cfg() -> crate::tools::config::DebugConfig {
    crate::tools::config::get_debug_config().unwrap_or_default()
}

fn openocd_exe() -> &'static str {
    if cfg!(windows) {
        "openocd.exe"
    } else {
        "openocd"
    }
}

/// Path to an OpenOCD binary from PlatformIO's package cache, then `PATH`. STM32/ARM use
/// the generic `tool-openocd`; ESP32 use the Espressif `tool-openocd-esp32`.
pub fn find_openocd(chip: &str) -> Option<String> {
    if let Some(p) = debug_cfg().openocd_path {
        if Path::new(&p).exists() {
            return Some(p);
        }
    }
    let pkgs = platformio_packages();
    let preferred = if family(chip) == "arm" {
        "tool-openocd"
    } else {
        "tool-openocd-esp32"
    };
    let other = if preferred == "tool-openocd" {
        "tool-openocd-esp32"
    } else {
        "tool-openocd"
    };
    for pkg in [preferred, other] {
        let cand = pkgs.join(pkg).join("bin").join(openocd_exe());
        if cand.exists() {
            return Some(cand.to_string_lossy().into_owned());
        }
    }
    which::which("openocd")
        .ok()
        .map(|p| p.to_string_lossy().into_owned())
}

/// The `scripts` dir bundled with a PlatformIO OpenOCD, so `-f interface/…`/`-f target/…`
/// resolve. None for a system OpenOCD (it has its own search path).
pub fn openocd_scripts_dir(openocd_path: &str) -> Option<PathBuf> {
    let pkg = Path::new(openocd_path).parent()?.parent()?; // <pkg>/bin/openocd → <pkg>
    [
        pkg.join("openocd").join("scripts"),
        pkg.join("share").join("openocd").join("scripts"),
    ]
    .into_iter()
    .find(|sub| sub.is_dir())
}

/// Path to the GDB for `chip`: PlatformIO's toolchain then `PATH`. ARM/STM32 use
/// `arm-none-eabi-gdb`; xtensa parts use `xtensa-*-elf-gdb`; RISC-V use `riscv32-esp-elf-gdb`.
pub fn find_gdb(chip: &str) -> Option<String> {
    if let Some(p) = debug_cfg().gdb_path {
        if Path::new(&p).exists() {
            return Some(p);
        }
    }
    let names: Vec<String> = match family(chip) {
        "arm" => vec!["arm-none-eabi-gdb".into()],
        "riscv" => vec!["riscv32-esp-elf-gdb".into()],
        _ => vec![
            format!("xtensa-{chip}-elf-gdb"),
            "xtensa-esp-elf-gdb".into(),
            "xtensa-esp32-elf-gdb".into(),
        ],
    };
    // Collect every toolchain-*/bin file once, then pick by substring + a stem ending in
    // "gdb" (so helper scripts like *-gdb-add-index / *-gdb-py3 are skipped).
    let mut bins: Vec<PathBuf> = Vec::new();
    if let Ok(entries) = std::fs::read_dir(platformio_packages()) {
        for e in entries.flatten() {
            if e.file_name().to_string_lossy().starts_with("toolchain-") {
                if let Ok(files) = std::fs::read_dir(e.path().join("bin")) {
                    bins.extend(files.flatten().map(|f| f.path()));
                }
            }
        }
    }
    for name in &names {
        for b in &bins {
            let fname = b.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            let stem = b.file_stem().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
            if b.is_file() && stem.ends_with("gdb") && fname.contains(name.as_str()) {
                return Some(b.to_string_lossy().into_owned());
            }
        }
    }
    for name in &names {
        if let Ok(p) = which::which(name) {
            return Some(p.to_string_lossy().into_owned());
        }
    }
    None
}

/// OpenOCD `-f` argument list for `chip` (STM32: ST-Link + family target; ESP32: built-in
/// JTAG board cfg, or an interface override for external probes).
pub fn openocd_config(chip: &str, interface: Option<&str>) -> Result<Vec<String>, DebugError> {
    let cfg = debug_cfg();
    if let Some(o) = cfg.openocd_config {
        return Ok(vec!["-f".into(), o]);
    }
    let interface = interface.map(|s| s.to_string()).or(cfg.interface);
    if family(chip) == "arm" {
        let fam = &chip[5.min(chip.len())..]; // strip "stm32"
        let target = STM32_TARGETS
            .iter()
            .find(|(k, _)| *k == fam)
            .map(|(_, v)| *v)
            .ok_or_else(|| {
                err(format!(
                    "unknown STM32 family for {chip:?} — set debug.openocd_config to the \
                     OpenOCD target cfg (e.g. 'target/stm32f4x.cfg')"
                ))
            })?;
        let iface = interface.unwrap_or_else(|| "stlink".into());
        return Ok(vec![
            "-f".into(),
            format!("interface/{iface}.cfg"),
            "-f".into(),
            format!("target/{target}.cfg"),
        ]);
    }
    if let Some(iface) = interface {
        return Ok(vec![
            "-f".into(),
            format!("interface/{iface}.cfg"),
            "-f".into(),
            format!("target/{chip}.cfg"),
        ]);
    }
    if BUILTIN_JTAG.contains(&chip) {
        return Ok(vec!["-f".into(), format!("board/{chip}-builtin.cfg")]);
    }
    Err(err(format!(
        "{chip} has no built-in USB-JTAG — connect an external probe and pass interface= \
         (e.g. interface='ftdi/esp32_devkitj_v1'), or set debug.openocd_config"
    )))
}

/// Locate the firmware ELF (symbol file): explicit path wins, else the most-recently-built
/// `firmware.elf` under the PlatformIO scratch tree, else any `*.elf` from an arduino build.
pub fn resolve_elf(elf: Option<&str>) -> Result<PathBuf, DebugError> {
    if let Some(e) = elf.filter(|s| !s.is_empty()) {
        let p = PathBuf::from(e);
        if !p.exists() {
            return Err(err(format!("ELF not found: {e}")));
        }
        return Ok(p);
    }
    let pio_root = std::env::temp_dir().join("nff_pio");
    if let Some(p) = newest_named(&pio_root, "firmware.elf") {
        return Ok(p);
    }
    let sketch_root = std::env::temp_dir().join("nff_sketch");
    if let Some(p) = crate::tools::toolchain::find_by_ext(&sketch_root, ".elf") {
        return Ok(p);
    }
    Err(err(
        "No firmware ELF found — compile first (`nff compile <sketch>`), or pass elf= with a \
         path to a built .elf",
    ))
}

/// The newest file named `name` anywhere under `root` (by mtime), or None.
fn newest_named(root: &Path, name: &str) -> Option<PathBuf> {
    let mut best: Option<(std::time::SystemTime, PathBuf)> = None;
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path.file_name().and_then(|n| n.to_str()) == Some(name) {
                if let Ok(mtime) = entry.metadata().and_then(|m| m.modified()) {
                    if best.as_ref().map(|(t, _)| mtime > *t).unwrap_or(true) {
                        best = Some((mtime, path));
                    }
                }
            }
        }
    }
    best.map(|(_, p)| p)
}

// ---------------------------------------------------------------------------
// GDB/MI parser — a minimal recursive-descent parser of the MI value grammar
// (c-string | tuple {…} | list […]) into serde_json::Value.
// ---------------------------------------------------------------------------

struct MiParser<'a> {
    b: &'a [u8],
    i: usize,
}

impl<'a> MiParser<'a> {
    fn new(s: &'a str) -> Self {
        MiParser { b: s.as_bytes(), i: 0 }
    }

    fn peek(&self) -> Option<u8> {
        self.b.get(self.i).copied()
    }

    /// Parse a comma-separated list of `name=value` results into a JSON object.
    fn parse_results(&mut self) -> Value {
        let mut map = Map::new();
        while self.peek().is_some() {
            let (k, v) = self.parse_result();
            if !k.is_empty() {
                map.insert(k, v);
            }
            if self.peek() == Some(b',') {
                self.i += 1;
            } else {
                break;
            }
        }
        Value::Object(map)
    }

    fn parse_result(&mut self) -> (String, Value) {
        let key = self.parse_var();
        if self.peek() == Some(b'=') {
            self.i += 1;
        }
        (key, self.parse_value())
    }

    fn parse_var(&mut self) -> String {
        let start = self.i;
        while let Some(c) = self.peek() {
            if c == b'=' || c == b',' {
                break;
            }
            self.i += 1;
        }
        String::from_utf8_lossy(&self.b[start..self.i]).into_owned()
    }

    fn parse_value(&mut self) -> Value {
        match self.peek() {
            Some(b'"') => Value::String(self.parse_cstring()),
            Some(b'{') => self.parse_tuple(),
            Some(b'[') => self.parse_list(),
            _ => Value::Null,
        }
    }

    fn parse_cstring(&mut self) -> String {
        self.i += 1; // opening quote
        let mut out: Vec<u8> = Vec::new();
        while let Some(c) = self.peek() {
            self.i += 1;
            if c == b'\\' {
                if let Some(e) = self.peek() {
                    self.i += 1;
                    out.push(match e {
                        b'n' => b'\n',
                        b't' => b'\t',
                        b'r' => b'\r',
                        b'"' => b'"',
                        b'\\' => b'\\',
                        other => other,
                    });
                }
            } else if c == b'"' {
                break;
            } else {
                out.push(c);
            }
        }
        String::from_utf8_lossy(&out).into_owned()
    }

    fn parse_tuple(&mut self) -> Value {
        self.i += 1; // '{'
        let mut map = Map::new();
        if self.peek() == Some(b'}') {
            self.i += 1;
            return Value::Object(map);
        }
        loop {
            let (k, v) = self.parse_result();
            if !k.is_empty() {
                map.insert(k, v);
            }
            if self.peek() == Some(b',') {
                self.i += 1;
            } else {
                break;
            }
        }
        if self.peek() == Some(b'}') {
            self.i += 1;
        }
        Value::Object(map)
    }

    fn parse_list(&mut self) -> Value {
        self.i += 1; // '['
        let mut arr: Vec<Value> = Vec::new();
        if self.peek() == Some(b']') {
            self.i += 1;
            return Value::Array(arr);
        }
        loop {
            // An element is either a bare value or a `name=value` result; for the latter
            // (e.g. stack=[frame={…},frame={…}]) keep the value and drop the repeated key.
            let v = match self.peek() {
                Some(b'"') | Some(b'{') | Some(b'[') => self.parse_value(),
                _ => self.parse_result().1,
            };
            arr.push(v);
            if self.peek() == Some(b',') {
                self.i += 1;
            } else {
                break;
            }
        }
        if self.peek() == Some(b']') {
            self.i += 1;
        }
        Value::Array(arr)
    }
}

/// Parse a `^class,payload…` result record into (class, payload-object).
fn parse_result_record(line: &str) -> Option<(String, Value)> {
    let rest = line.strip_prefix('^')?;
    let (class, payload) = match rest.find(',') {
        Some(idx) => (&rest[..idx], &rest[idx + 1..]),
        None => (rest, ""),
    };
    let value = if payload.is_empty() {
        Value::Object(Map::new())
    } else {
        MiParser::new(payload).parse_results()
    };
    Some((class.to_string(), value))
}

fn unquote(s: &str) -> String {
    if s.starts_with('"') {
        MiParser::new(s).parse_cstring()
    } else {
        s.to_string()
    }
}

struct MiResponse {
    class: String,
    payload: Value,
    console: String,
}

fn result(resp: MiResponse) -> Result<Value, DebugError> {
    if resp.class == "error" {
        let msg = resp
            .payload
            .get("msg")
            .and_then(|v| v.as_str())
            .unwrap_or("GDB reported an error");
        Err(err(msg.to_string()))
    } else {
        Ok(resp.payload)
    }
}

// ---------------------------------------------------------------------------
// Pure response shapers (mirror tools/debug.py; unit-tested without hardware)
// ---------------------------------------------------------------------------

fn field(v: &Value, k: &str) -> Value {
    v.get(k).cloned().unwrap_or(Value::Null)
}

fn field2(v: &Value, k1: &str, k2: &str) -> Value {
    match v.get(k1) {
        Some(x) if !x.is_null() => x.clone(),
        _ => v.get(k2).cloned().unwrap_or(Value::Null),
    }
}

pub fn shape_registers(names: &Value, values: &Value) -> Value {
    let names = names.get("register-names").and_then(|v| v.as_array());
    let vals = values.get("register-values").and_then(|v| v.as_array());
    let mut map = Map::new();
    if let (Some(names), Some(vals)) = (names, vals) {
        for entry in vals {
            if let Some(num) = entry.get("number").and_then(|v| v.as_str()) {
                if let Ok(idx) = num.parse::<usize>() {
                    if let Some(Value::String(name)) = names.get(idx) {
                        if !name.is_empty() {
                            map.insert(name.clone(), field(entry, "value"));
                        }
                    }
                }
            }
        }
    }
    json!({ "registers": Value::Object(map) })
}

pub fn shape_call_stack(payload: &Value) -> Value {
    let frames: Vec<Value> = payload
        .get("stack")
        .and_then(|v| v.as_array())
        .map(|s| {
            s.iter()
                .map(|f| {
                    json!({
                        "level": field(f, "level"),
                        "function": field(f, "func"),
                        "file": field2(f, "file", "fullname"),
                        "line": field(f, "line"),
                        "address": field(f, "addr"),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    json!({ "frames": frames })
}

pub fn shape_variables(frame: i64, payload: &Value) -> Value {
    let vars: Vec<Value> = payload
        .get("variables")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .map(|v| json!({ "name": field(v, "name"), "value": field(v, "value") }))
                .collect()
        })
        .unwrap_or_default();
    json!({ "frame": frame, "variables": vars })
}

pub fn shape_expand(expr: &str, created: &Value, children: &Value) -> Value {
    let kids: Vec<Value> = children
        .get("children")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .map(|c| {
                    json!({
                        "name": field(c, "exp"),
                        "value": field(c, "value"),
                        "type": field(c, "type"),
                    })
                })
                .collect()
        })
        .unwrap_or_default();
    json!({
        "expression": expr,
        "value": field(created, "value"),
        "type": field(created, "type"),
        "children": kids,
    })
}

pub fn shape_memory(address: &str, count: i64, payload: &Value) -> Value {
    let block = payload.get("memory").and_then(|v| v.as_array()).and_then(|a| a.first());
    let contents = block
        .and_then(|b| b.get("contents"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let begin = block
        .and_then(|b| b.get("begin"))
        .and_then(|v| v.as_str())
        .unwrap_or(address)
        .to_string();
    json!({
        "address": address,
        "begin": begin,
        "count": count,
        "hex": contents,
        "dump": hex_dump(&begin, &contents),
    })
}

pub fn shape_breakpoint(location: &str, payload: &Value) -> Value {
    let b = payload.get("bkpt").cloned().unwrap_or(Value::Null);
    json!({
        "number": field(&b, "number"),
        "location": location,
        "function": field(&b, "func"),
        "file": field2(&b, "file", "fullname"),
        "line": field(&b, "line"),
        "address": field(&b, "addr"),
    })
}

/// Render a hex string as an offset-prefixed dump, 16 bytes per line.
pub fn hex_dump(begin: &str, contents: &str) -> String {
    let base = i64::from_str_radix(begin.trim_start_matches("0x"), 16).unwrap_or(0);
    let mut out: Vec<String> = Vec::new();
    let chars: Vec<char> = contents.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let row: Vec<char> = chars[i..(i + 32).min(chars.len())].to_vec();
        let pairs: Vec<String> = row
            .chunks(2)
            .map(|c| c.iter().collect::<String>())
            .collect();
        out.push(format!("0x{:08x}: {}", base + (i / 2) as i64, pairs.join(" ")));
        i += 32;
    }
    out.join("\n")
}

// ---------------------------------------------------------------------------
// DebugSession
// ---------------------------------------------------------------------------

pub struct DebugSession {
    pub chip: String,
    pub elf: Option<PathBuf>,
    openocd: Child,
    gdb: Child,
    stdin: ChildStdin,
    reader: BufReader<ChildStdout>,
    pub halted: bool,
}

impl DebugSession {
    fn start(
        chip: String,
        elf: Option<PathBuf>,
        openocd_path: &str,
        gdb_path: &str,
        cfg_args: &[String],
    ) -> Result<DebugSession, DebugError> {
        let (mut openocd, out_buf) = spawn_openocd(openocd_path, cfg_args)?;
        if let Err(e) = wait_for_gdb_server(&mut openocd, &out_buf) {
            let _ = openocd.kill();
            return Err(e);
        }
        let (gdb, stdin, reader) = match spawn_gdb(gdb_path) {
            Ok(v) => v,
            Err(e) => {
                let _ = openocd.kill();
                return Err(e);
            }
        };
        let mut session = DebugSession {
            chip,
            elf,
            openocd,
            gdb,
            stdin,
            reader,
            halted: false,
        };
        if let Err(e) = session.handshake() {
            session.stop();
            return Err(e);
        }
        Ok(session)
    }

    fn handshake(&mut self) -> Result<(), DebugError> {
        self.drain_to_prompt()?;
        if let Some(elf) = self.elf.clone() {
            let posix = elf.to_string_lossy().replace('\\', "/");
            result(self.exec(&format!("-file-exec-and-symbols \"{posix}\""))?)?;
        }
        result(self.exec(&format!("-target-select remote 127.0.0.1:{GDB_PORT}"))?)?;
        self.exec("-interpreter-exec console \"monitor reset halt\"")?;
        self.halted = true;
        Ok(())
    }

    fn stop(&mut self) {
        let _ = self.exec("-gdb-exit");
        let _ = self.gdb.kill();
        let _ = self.gdb.wait();
        let _ = self.openocd.kill();
        let _ = self.openocd.wait();
    }

    /// Drain GDB's startup banner up to the first `(gdb)` prompt.
    fn drain_to_prompt(&mut self) -> Result<(), DebugError> {
        loop {
            let mut line = String::new();
            if self.reader.read_line(&mut line)? == 0 {
                return Ok(());
            }
            if line.trim_end() == "(gdb)" {
                return Ok(());
            }
        }
    }

    fn exec(&mut self, command: &str) -> Result<MiResponse, DebugError> {
        writeln!(self.stdin, "{command}")?;
        self.stdin.flush()?;
        let deadline = Instant::now() + Duration::from_secs(MI_READ_TIMEOUT_SECS);
        let mut class = String::new();
        let mut payload = Value::Object(Map::new());
        let mut console = String::new();
        loop {
            if Instant::now() > deadline {
                return Err(err(format!("GDB timed out on `{command}`")));
            }
            let mut line = String::new();
            if self.reader.read_line(&mut line)? == 0 {
                break; // EOF
            }
            let t = line.trim_end_matches(['\r', '\n']);
            if t.trim_end() == "(gdb)" {
                break;
            } else if let Some(rest) = t
                .strip_prefix('~')
                .or_else(|| t.strip_prefix('@'))
                .or_else(|| t.strip_prefix('&'))
            {
                // console (~), target (@), and log (&) stream records — `monitor` output
                // arrives on the target/log streams, so capture all three (matches Python).
                console.push_str(&unquote(rest));
            } else if t.starts_with('^') {
                if let Some((c, v)) = parse_result_record(t) {
                    class = c;
                    payload = v;
                }
            }
        }
        Ok(MiResponse { class, payload, console })
    }

    fn require_halted(&self) -> Result<(), DebugError> {
        if self.halted {
            Ok(())
        } else {
            Err(err("target is running — call pause_execution first"))
        }
    }

    pub fn session_info(&mut self) -> Result<Value, DebugError> {
        let elf = self.elf.as_ref().map(|p| p.to_string_lossy().into_owned());
        let mut info = json!({ "chip": self.chip, "elf": elf, "halted": self.halted });
        if self.halted {
            if let Ok(p) = self.exec("-stack-info-frame").and_then(result) {
                let f = field(&p, "frame");
                info["frame"] = json!({
                    "function": field(&f, "func"),
                    "file": field2(&f, "file", "fullname"),
                    "line": field(&f, "line"),
                    "address": field(&f, "addr"),
                });
            }
        }
        Ok(info)
    }

    pub fn call_stack(&mut self) -> Result<Value, DebugError> {
        self.require_halted()?;
        let p = result(self.exec("-stack-list-frames")?)?;
        Ok(shape_call_stack(&p))
    }

    pub fn variables(&mut self, frame: i64) -> Result<Value, DebugError> {
        self.require_halted()?;
        self.exec(&format!("-stack-select-frame {frame}"))?;
        let p = result(self.exec("-stack-list-variables --all-values")?)?;
        Ok(shape_variables(frame, &p))
    }

    pub fn expand_variable(&mut self, expr: &str) -> Result<Value, DebugError> {
        self.require_halted()?;
        let created = result(self.exec(&format!("-var-create - * \"{expr}\""))?)?;
        let name = created.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string();
        let children = if name.is_empty() {
            Value::Object(Map::new())
        } else {
            self.exec(&format!("-var-list-children --all-values \"{name}\""))
                .and_then(result)
                .unwrap_or(Value::Object(Map::new()))
        };
        if !name.is_empty() {
            let _ = self.exec(&format!("-var-delete \"{name}\""));
        }
        Ok(shape_expand(expr, &created, &children))
    }

    pub fn registers(&mut self) -> Result<Value, DebugError> {
        self.require_halted()?;
        let names = result(self.exec("-data-list-register-names")?)?;
        let values = result(self.exec("-data-list-register-values x")?)?;
        Ok(shape_registers(&names, &values))
    }

    pub fn memory(&mut self, address: &str, count: i64) -> Result<Value, DebugError> {
        self.require_halted()?;
        let p = result(self.exec(&format!("-data-read-memory-bytes {address} {count}"))?)?;
        Ok(shape_memory(address, count, &p))
    }

    pub fn evaluate(&mut self, expr: &str) -> Result<Value, DebugError> {
        self.require_halted()?;
        let p = result(self.exec(&format!("-data-evaluate-expression \"{expr}\""))?)?;
        Ok(json!({ "expression": expr, "value": field(&p, "value") }))
    }

    pub fn set_breakpoint(&mut self, location: &str) -> Result<Value, DebugError> {
        let p = result(self.exec(&format!("-break-insert {location}"))?)?;
        Ok(shape_breakpoint(location, &p))
    }

    pub fn pause(&mut self) -> Result<Value, DebugError> {
        self.exec("-exec-interrupt")?;
        self.halted = true;
        self.session_info()
    }

    pub fn cont(&mut self) -> Result<Value, DebugError> {
        self.exec("-exec-continue")?;
        self.halted = false;
        Ok(json!({ "state": "running" }))
    }

    pub fn step(&mut self, kind: &str) -> Result<Value, DebugError> {
        self.require_halted()?;
        let mi = match kind {
            "over" => "-exec-next",
            "into" => "-exec-step",
            "out" => "-exec-finish",
            _ => return Err(err(format!("unknown step kind {kind:?} — use over | into | out"))),
        };
        self.exec(mi)?;
        self.session_info()
    }

    pub fn gdb_command(&mut self, command: &str) -> Result<Value, DebugError> {
        let command = command.trim();
        if command.starts_with('-') {
            let payload = result(self.exec(command)?)?;
            Ok(json!({ "command": command, "result": payload }))
        } else {
            let resp = self.exec(&format!("-interpreter-exec console \"{command}\""))?;
            Ok(json!({ "command": command, "output": resp.console }))
        }
    }
}

impl Drop for DebugSession {
    fn drop(&mut self) {
        self.stop();
    }
}

fn spawn_openocd(
    openocd: &str,
    cfg_args: &[String],
) -> Result<(Child, Arc<Mutex<String>>), DebugError> {
    let mut child = Command::new(openocd)
        .args(cfg_args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let buf = Arc::new(Mutex::new(String::new()));
    // Drain stdout+stderr on threads so OpenOCD never blocks on a full pipe, and so we can
    // surface its diagnostics if it dies before the GDB server comes up.
    for pipe in [
        child.stdout.take().map(DrainSource::Out),
        child.stderr.take().map(DrainSource::Err),
    ]
    .into_iter()
    .flatten()
    {
        let buf = buf.clone();
        std::thread::spawn(move || {
            let mut s = String::new();
            match pipe {
                DrainSource::Out(mut r) => {
                    let _ = r.read_to_string(&mut s);
                }
                DrainSource::Err(mut r) => {
                    let _ = r.read_to_string(&mut s);
                }
            }
            if !s.is_empty() {
                buf.lock().unwrap().push_str(&s);
            }
        });
    }
    Ok((child, buf))
}

enum DrainSource {
    Out(ChildStdout),
    Err(std::process::ChildStderr),
}

fn spawn_gdb(gdb: &str) -> Result<(Child, ChildStdin, BufReader<ChildStdout>), DebugError> {
    let mut child = Command::new(gdb)
        .args(["--nx", "--quiet", "--interpreter=mi3"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let stdin = child.stdin.take().ok_or_else(|| err("gdb stdin not piped"))?;
    let reader = BufReader::new(child.stdout.take().ok_or_else(|| err("gdb stdout not piped"))?);
    Ok((child, stdin, reader))
}

fn wait_for_gdb_server(child: &mut Child, buf: &Arc<Mutex<String>>) -> Result<(), DebugError> {
    let deadline = Instant::now() + Duration::from_secs(OPENOCD_STARTUP_TIMEOUT_SECS);
    let addr = format!("127.0.0.1:{GDB_PORT}").parse().unwrap();
    loop {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
            return Ok(());
        }
        if let Ok(Some(_)) = child.try_wait() {
            let out = buf.lock().unwrap().clone();
            return Err(err(format!(
                "OpenOCD exited before the GDB server came up:\n{}",
                out.trim()
            )));
        }
        if Instant::now() >= deadline {
            let out = buf.lock().unwrap().clone();
            return Err(err(format!(
                "OpenOCD did not start a GDB server on :{GDB_PORT} within \
                 {OPENOCD_STARTUP_TIMEOUT_SECS}s\n{}",
                out.trim()
            )));
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

/// Discovery + construction: resolve the chip/binaries/cfg/ELF and start a halted session.
pub fn open_session(
    elf: Option<&str>,
    board: Option<&str>,
    interface: Option<&str>,
) -> Result<DebugSession, DebugError> {
    let chip = detect_chip(board.map(String::from).or_else(autodetect_board));
    let openocd = find_openocd(&chip).ok_or_else(|| {
        err("OpenOCD not found — install it via PlatformIO \
             (`pio pkg install -g -t platformio/tool-openocd`) or put `openocd` on PATH")
    })?;
    let gdb = find_gdb(&chip).ok_or_else(|| {
        let hint = if family(&chip) == "arm" {
            "Arm GNU (gccarmnoneeabi)"
        } else {
            "Espressif"
        };
        err(format!(
            "GDB for {chip} not found — install the {hint} toolchain via PlatformIO \
             (build once for this board) or put the gdb on PATH"
        ))
    })?;
    // Symbols are optional: an explicit but missing elf= is an error, but with no build we
    // still attach (registers/memory/raw-GDB) without source views.
    let explicit_elf = elf.filter(|s| !s.is_empty()).is_some();
    let elf_path = match resolve_elf(elf) {
        Ok(p) => Some(p),
        Err(e) => {
            if explicit_elf {
                return Err(e);
            }
            None
        }
    };
    let mut cfg_args = openocd_config(&chip, interface)?;
    if let Some(scripts) = openocd_scripts_dir(&openocd) {
        let mut prefixed = vec!["-s".to_string(), scripts.to_string_lossy().into_owned()];
        prefixed.append(&mut cfg_args);
        cfg_args = prefixed;
    }
    DebugSession::start(chip, elf_path, &openocd, &gdb, &cfg_args)
}

#[cfg(test)]
#[allow(clippy::items_after_test_module)]
mod tests {
    use super::*;

    #[test]
    fn family_classification() {
        assert_eq!(family("stm32f4"), "arm");
        assert_eq!(family("esp32c3"), "riscv");
        assert_eq!(family("esp32s3"), "xtensa");
        assert_eq!(family("esp32"), "xtensa");
    }

    #[test]
    fn stm32_family_extraction() {
        assert_eq!(stm32_family(&["nucleo_f401re".into()]), "f4");
        assert_eq!(stm32_family(&["genericSTM32F103C8".into()]), "f1");
        assert_eq!(stm32_family(&["bluepill_f103c8".into()]), "f1");
        assert_eq!(stm32_family(&["STMicroelectronics:stm32:Nucleo_64".into()]), "");
    }

    #[test]
    fn openocd_config_stm32_stlink() {
        assert_eq!(
            openocd_config("stm32f4", None).unwrap(),
            vec!["-f", "interface/stlink.cfg", "-f", "target/stm32f4x.cfg"]
        );
    }

    #[test]
    fn openocd_config_stm32_unknown_family_errors() {
        assert!(openocd_config("stm32", None).is_err());
    }

    #[test]
    fn openocd_config_esp32_builtin() {
        assert_eq!(
            openocd_config("esp32s3", None).unwrap(),
            vec!["-f", "board/esp32s3-builtin.cfg"]
        );
    }

    #[test]
    fn openocd_config_classic_esp32_needs_interface() {
        assert!(openocd_config("esp32", None).is_err());
    }

    #[test]
    fn openocd_config_external_interface() {
        assert_eq!(
            openocd_config("esp32", Some("ftdi/esp32_devkitj_v1")).unwrap(),
            vec!["-f", "interface/ftdi/esp32_devkitj_v1.cfg", "-f", "target/esp32.cfg"]
        );
    }

    #[test]
    fn mi_parses_register_values() {
        let (class, payload) =
            parse_result_record(r#"^done,register-values=[{number="0",value="0x1"},{number="2",value="0x40"}]"#)
                .unwrap();
        assert_eq!(class, "done");
        let names = json!({ "register-names": ["pc", "", "a0"] });
        let out = shape_registers(&names, &payload);
        assert_eq!(out["registers"]["pc"], "0x1");
        assert_eq!(out["registers"]["a0"], "0x40");
    }

    #[test]
    fn mi_parses_stack() {
        let (_c, p) = parse_result_record(
            r#"^done,stack=[frame={level="0",func="loop",file="m.cpp",line="12",addr="0x8"},frame={level="1",func="main",file="m.cpp",line="3",addr="0x9"}]"#,
        )
        .unwrap();
        let out = shape_call_stack(&p);
        assert_eq!(out["frames"][0]["function"], "loop");
        assert_eq!(out["frames"][1]["function"], "main");
    }

    #[test]
    fn mi_error_record() {
        let (class, payload) = parse_result_record(r#"^error,msg="No symbol \"x\" in current context.""#).unwrap();
        assert_eq!(class, "error");
        let r = result(MiResponse { class, payload, console: String::new() });
        assert!(r.is_err());
        assert!(format!("{}", r.unwrap_err()).contains("No symbol"));
    }

    #[test]
    fn mi_parses_memory_and_dumps() {
        let (_c, p) =
            parse_result_record(r#"^done,memory=[{begin="0x3ffb0000",offset="0x0",end="0x4",contents="deadbeef"}]"#)
                .unwrap();
        let out = shape_memory("0x3ffb0000", 4, &p);
        assert_eq!(out["hex"], "deadbeef");
        assert_eq!(out["dump"], "0x3ffb0000: de ad be ef");
    }

    #[test]
    fn mi_parses_var_children() {
        let (_c, created) = parse_result_record(r#"^done,name="var1",value="{...}",type="Point""#).unwrap();
        let (_c2, kids) = parse_result_record(
            r#"^done,children=[child={name="var1.x",exp="x",value="1",type="int"},child={name="var1.y",exp="y",value="2",type="int"}]"#,
        )
        .unwrap();
        let out = shape_expand("pt", &created, &kids);
        assert_eq!(out["type"], "Point");
        assert_eq!(out["children"][0]["name"], "x");
        assert_eq!(out["children"][1]["value"], "2");
    }

    #[test]
    fn hex_dump_format() {
        assert_eq!(hex_dump("0x3ffb0000", "0011223344556677"), "0x3ffb0000: 00 11 22 33 44 55 66 77");
    }
}
