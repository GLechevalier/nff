//! USB board detection.
//!
//! Detection runs two layers, curated-first (kept identical in `nff/tools/boards.py`):
//!
//!   Layer A — the curated `BOARD_MAP` (VID:PID → board). Authoritative: it always wins,
//!     so the shared USB-serial bridges (CP210x/CH340/FTDI) and ST-Link keep their
//!     hand-chosen family default even when a PlatformIO manifest also claims that id.
//!   Layer B — a fallback index built from installed PlatformIO board manifests'
//!     `build.hwids`, consulted only when Layer A misses. It is de-ambiguated (a VID:PID
//!     mapping to >1 board is dropped) and skips the shared-bridge VIDs, so it only ever
//!     adds *unambiguous native-USB* boards. The index is cached under the config dir.
//!
//! A USB-serial bridge chip is shared by hundreds of boards, so VID:PID can only ever be
//! a sensible *default* the user overrides with `--board`.

use serialport::available_ports;
use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

/// Curated USB VID:PID → (name, fqbn, pio_board). `fqbn` is the arduino-cli id; `pio_board`
/// is the PlatformIO board id used by the default backend. One bridge VID:PID covers many
/// boards, so these are defaults, overridable with `--board`.
pub const BOARD_MAP: &[(u16, u16, &str, &str, &str)] = &[
    // Arduino official (VID 0x2341)
    (0x2341, 0x0043, "Arduino Uno", "arduino:avr:uno", "uno"),
    (0x2341, 0x0010, "Arduino Mega 2560", "arduino:avr:mega", "megaatmega2560"),
    (0x2341, 0x0036, "Arduino Leonardo", "arduino:avr:leonardo", "leonardo"),
    (0x2341, 0x0058, "Arduino Nano", "arduino:avr:nano", "nanoatmega328"),
    // Arduino SRL / older "Arduino.org" boards reuse the same PIDs under VID 0x2A03.
    (0x2a03, 0x0043, "Arduino Uno", "arduino:avr:uno", "uno"),
    (0x2a03, 0x0010, "Arduino Mega 2560", "arduino:avr:mega", "megaatmega2560"),
    (0x2a03, 0x0036, "Arduino Leonardo", "arduino:avr:leonardo", "leonardo"),
    (0x2a03, 0x0058, "Arduino Nano", "arduino:avr:nano", "nanoatmega328"),
    // ESP family via shared USB-serial bridges — family defaults, override with --board.
    (0x10c4, 0xea60, "ESP32 (CP210x)", "esp32:esp32:esp32", "esp32dev"),
    (0x1a86, 0x7523, "ESP32 (CH340)", "esp32:esp32:esp32", "esp32dev"),
    (0x0403, 0x6001, "ESP8266 (FTDI)", "esp8266:esp8266:generic", "esp01_1m"),
    // ESP32-S3/C3 native USB-Serial-JTAG. 0x303a:0x1001 is shared across many S3/C3 boards
    // (so Layer B drops it as ambiguous); default to an S3 devkit, override with --board.
    (
        0x303a,
        0x1001,
        "ESP32-S3 (USB-JTAG)",
        "esp32:esp32:esp32s3",
        "esp32-s3-devkitc-1",
    ),
    // STMicroelectronics ST-Link debug+VCP bridges (on-board on Nucleo/Discovery and most
    // STM32 dev boards) and the DFU bootloader. One VID:PID covers many distinct STM32
    // boards, so the fqbn/pio_board are only sensible defaults the user can override.
    (
        0x0483,
        0x3748,
        "STM32 (ST-Link V2)",
        "STMicroelectronics:stm32:Nucleo_64",
        "nucleo_f401re",
    ),
    (
        0x0483,
        0x374b,
        "STM32 (ST-Link V2-1)",
        "STMicroelectronics:stm32:Nucleo_64",
        "nucleo_f401re",
    ),
    (
        0x0483,
        0x374e,
        "STM32 (ST-Link V3)",
        "STMicroelectronics:stm32:Nucleo_64",
        "nucleo_f401re",
    ),
    (
        0x0483,
        0x374f,
        "STM32 (ST-Link V3)",
        "STMicroelectronics:stm32:Nucleo_64",
        "nucleo_f401re",
    ),
    (
        0x0483,
        0xdf11,
        "STM32 (DFU bootloader)",
        "STMicroelectronics:stm32:GenF1",
        "genericSTM32F103C8",
    ),
    // RP2040 Raspberry Pi Pico — arduino-pico CDC serial (0x2e8a:0x000a). The 0x2e8a:0x0003
    // BOOTSEL device is USB mass-storage, never a serial port, so it is intentionally absent.
    (
        0x2e8a,
        0x000a,
        "Raspberry Pi Pico",
        "rp2040:rp2040:rpipico",
        "pico",
    ),
    // Teensy (PJRC) serial. Qualify by the exact pair — bare 0x16c0 is a shared hobby VID.
    // All Teensy models share this pair, so default to a recent one; override with --board.
    (
        0x16c0,
        0x0483,
        "Teensy (PJRC)",
        "teensy:avr:teensy41",
        "teensy41",
    ),
];

/// PlatformIO board catalog: board id → platform. Supplies the platform for the common
/// families; any board id is still accepted (PlatformIO resolves + installs the platform
/// on first build), which is what makes nff board-universal.
pub const PIO_BOARD_CATALOG: &[(&str, &str)] = &[
    // ESP32 family
    ("esp32dev", "espressif32"),
    ("esp32-s3-devkitc-1", "espressif32"),
    ("esp32-c3-devkitm-1", "espressif32"),
    ("esp32-c6-devkitc-1", "espressif32"),
    ("esp32-s2-saola-1", "espressif32"),
    // ESP8266
    ("esp01_1m", "espressif8266"),
    ("nodemcuv2", "espressif8266"),
    // RP2040 / Raspberry Pi Pico
    ("pico", "raspberrypi"),
    ("rpipicow", "raspberrypi"),
    // STM32
    ("genericSTM32F103C8", "ststm32"),
    ("nucleo_f401re", "ststm32"),
    ("bluepill_f103c8", "ststm32"),
    // Classic AVR
    ("uno", "atmelavr"),
    ("megaatmega2560", "atmelavr"),
    ("nanoatmega328", "atmelavr"),
    ("leonardo", "atmelavr"),
    // Teensy
    ("teensy41", "teensy"),
];

/// Shared USB-serial bridge VIDs (CP210x / CH340 / FTDI). A board's *real* identity can't
/// be inferred from these, so Layer B never trusts a manifest that claims one — they stay
/// owned by the curated map's family defaults.
const BRIDGE_VIDS: &[u16] = &[0x10c4, 0x1a86, 0x0403];

/// Cache schema version — bump to force a rebuild when the index format changes.
const CACHE_VERSION: u32 = 1;
/// Rebuild the manifest index at least this often (backstops mtime-resolution gaps).
const CACHE_TTL_SECS: u64 = 24 * 60 * 60;

/// Best-effort PlatformIO platform for a board id, or None if unknown.
pub fn pio_platform_for(board: &str) -> Option<&'static str> {
    PIO_BOARD_CATALOG
        .iter()
        .find(|(id, _)| *id == board)
        .map(|(_, platform)| *platform)
}

/// Map an arduino-cli FQBN to a sensible default PlatformIO board id, for `nff init`
/// to seed `build.board` from a USB-detected device. None when there's no obvious match
/// (the user can always pass `--board <pio-id>`).
pub fn fqbn_to_pio_board(fqbn: &str) -> Option<&'static str> {
    BOARD_MAP
        .iter()
        .find(|(_, _, _, f, _)| *f == fqbn)
        .map(|(_, _, _, _, pio)| *pio)
}

#[derive(Debug, Clone)]
pub struct DetectedDevice {
    pub port: String,
    pub board: String,
    pub fqbn: String,
    pub vendor_id: String,
    pub product_id: String,
    pub pio_board: Option<String>,
}

/// The board-identity half of a detection (no port), shared by Layer A and Layer B.
#[derive(Debug, Clone)]
pub struct Identity {
    pub board: String,
    pub fqbn: String,
    pub pio_board: Option<String>,
}

/// One Layer-B manifest hit: a human board name + the PlatformIO board id + platform.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hit {
    pub name: String,
    pub board: String,
    pub platform: String,
}

pub type HwidIndex = HashMap<(u16, u16), Hit>;

/// Resolve a (vid,pid) to a board identity: curated Layer A first (authoritative), then the
/// Layer B manifest index. Pure — the caller supplies the index, so it's testable offline.
pub fn identify_ids(vid: u16, pid: u16, index: &HwidIndex) -> Option<Identity> {
    if let Some(&(_, _, name, fqbn, pio)) =
        BOARD_MAP.iter().find(|&&(v, p, _, _, _)| v == vid && p == pid)
    {
        return Some(Identity {
            board: name.to_string(),
            fqbn: fqbn.to_string(),
            pio_board: Some(pio.to_string()),
        });
    }
    if let Some(hit) = index.get(&(vid, pid)) {
        return Some(Identity {
            board: hit.name.clone(),
            // No arduino-cli FQBN is derivable from a PlatformIO manifest; the default
            // (pio) backend identifies the board via pio_board instead.
            fqbn: String::new(),
            pio_board: Some(hit.board.clone()),
        });
    }
    None
}

pub fn list_devices() -> Vec<DetectedDevice> {
    let ports = match available_ports() {
        Ok(p) => p,
        Err(_) => return vec![],
    };
    let index = manifest_index();
    let mut devices = Vec::new();
    for info in ports {
        if let serialport::SerialPortType::UsbPort(usb) = &info.port_type {
            let (vid, pid) = (usb.vid, usb.pid);
            if let Some(id) = identify_ids(vid, pid, index) {
                devices.push(DetectedDevice {
                    port: info.port_name.clone(),
                    board: id.board,
                    fqbn: id.fqbn,
                    vendor_id: format!("{:04x}", vid),
                    product_id: format!("{:04x}", pid),
                    pio_board: id.pio_board,
                });
            }
        }
    }
    devices
}

pub fn find_device(port: Option<&str>) -> Option<DetectedDevice> {
    list_devices()
        .into_iter()
        .find(|d| port.is_none() || Some(d.port.as_str()) == port)
}

// ---------------------------------------------------------------------------
// Layer B — PlatformIO manifest hwid index (+ cache)
// ---------------------------------------------------------------------------

/// `<PLATFORMIO_CORE_DIR or ~/.platformio>/platforms`, where installed platforms keep their
/// per-board manifest JSONs.
fn platforms_dir() -> PathBuf {
    let core = std::env::var("PLATFORMIO_CORE_DIR")
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            dirs::home_dir()
                .unwrap_or_else(|| PathBuf::from("."))
                .join(".platformio")
        });
    core.join("platforms")
}

/// Build the (vid,pid) → board index from installed PlatformIO board manifests. Pure: it
/// only reads `platforms_dir`. Skips bridge VIDs and drops any id claimed by >1 board.
pub fn build_manifest_index(platforms_dir: &Path) -> HwidIndex {
    // Accumulate every claim first so we can detect (and drop) ambiguous ids.
    let mut claims: HashMap<(u16, u16), Hit> = HashMap::new();
    let mut board_ids: HashMap<(u16, u16), HashSet<String>> = HashMap::new();

    let platform_dirs = match std::fs::read_dir(platforms_dir) {
        Ok(rd) => rd,
        Err(_) => return HashMap::new(),
    };
    for platform_entry in platform_dirs.flatten() {
        let platform_path = platform_entry.path();
        if !platform_path.is_dir() {
            continue;
        }
        let platform = platform_entry.file_name().to_string_lossy().into_owned();
        let boards_dir = platform_path.join("boards");
        let board_files = match std::fs::read_dir(&boards_dir) {
            Ok(rd) => rd,
            Err(_) => continue,
        };
        for board_entry in board_files.flatten() {
            let path = board_entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("json") {
                continue;
            }
            let board_id = match path.file_stem().and_then(|s| s.to_str()) {
                Some(s) => s.to_string(),
                None => continue,
            };
            let raw = match std::fs::read_to_string(&path) {
                Ok(s) => s,
                Err(_) => continue, // unreadable manifest — skip
            };
            let json: serde_json::Value = match serde_json::from_str(&raw) {
                Ok(v) => v,
                Err(_) => continue, // malformed manifest — skip
            };
            let hwids = match json.get("build").and_then(|b| b.get("hwids")) {
                Some(serde_json::Value::Array(a)) => a,
                _ => continue,
            };
            let name = json
                .get("name")
                .and_then(|n| n.as_str())
                .unwrap_or(&board_id)
                .to_string();
            for hw in hwids {
                let arr = match hw.as_array() {
                    Some(a) if a.len() >= 2 => a, // ignore any 3rd+ element
                    _ => continue,
                };
                let vid = arr[0].as_str().and_then(parse_hex);
                let pid = arr[1].as_str().and_then(parse_hex);
                let (vid, pid) = match (vid, pid) {
                    (Some(v), Some(p)) => (v, p),
                    _ => continue,
                };
                if BRIDGE_VIDS.contains(&vid) {
                    continue;
                }
                board_ids
                    .entry((vid, pid))
                    .or_default()
                    .insert(board_id.clone());
                claims.entry((vid, pid)).or_insert_with(|| Hit {
                    name: name.clone(),
                    board: board_id.clone(),
                    platform: platform.clone(),
                });
            }
        }
    }

    // Keep only ids that resolve to exactly one board (drop cross-board/platform collisions).
    claims
        .into_iter()
        .filter(|(k, _)| board_ids.get(k).map(|s| s.len()) == Some(1))
        .collect()
}

fn parse_hex(s: &str) -> Option<u16> {
    let s = s
        .strip_prefix("0x")
        .or_else(|| s.strip_prefix("0X"))
        .unwrap_or(s);
    u16::from_str_radix(s, 16).ok()
}

/// Process-wide memoized index. The long-lived `nff mcp` server builds it at most once;
/// a mid-session platform install is only picked up on next start (cache TTL/signature are
/// re-checked there). Built from cache when fresh, else rebuilt and re-cached.
pub fn manifest_index() -> &'static HwidIndex {
    static INDEX: OnceLock<HwidIndex> = OnceLock::new();
    INDEX.get_or_init(resolve_index)
}

#[derive(Serialize, Deserialize)]
struct CacheFile {
    version: u32,
    platforms_dir: String,
    signature: u64,
    built_at_unix: u64,
    index: HashMap<String, Hit>,
}

fn cache_path() -> PathBuf {
    crate::tools::config::config_dir().join("board_hwids_cache.json")
}

fn now_unix() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Cheap fingerprint of the platforms dir: summed mtime-ns of the dir itself plus each
/// immediate platform subdir. Catches platform install/remove (subdir count changes) and
/// upgrade (subdir mtime changes) without walking every board manifest.
fn current_signature(platforms_dir: &Path) -> u64 {
    fn mtime_ns(p: &Path) -> u64 {
        std::fs::metadata(p)
            .and_then(|m| m.modified())
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_nanos() as u64)
            .unwrap_or(0)
    }
    let mut sig = mtime_ns(platforms_dir);
    if let Ok(rd) = std::fs::read_dir(platforms_dir) {
        for entry in rd.flatten() {
            sig = sig.wrapping_add(mtime_ns(&entry.path()));
        }
    }
    sig
}

fn key_str(vid: u16, pid: u16) -> String {
    format!("{vid:04x}:{pid:04x}")
}

fn parse_key(k: &str) -> Option<(u16, u16)> {
    let (v, p) = k.split_once(':')?;
    Some((parse_hex(v)?, parse_hex(p)?))
}

fn resolve_index() -> HwidIndex {
    let dir = platforms_dir();
    let dir_str = dir.to_string_lossy().into_owned();
    let signature = current_signature(&dir);

    // Use a fresh cache if it matches this platforms dir, version, signature, and TTL.
    if let Ok(raw) = std::fs::read_to_string(cache_path()) {
        if let Ok(cache) = serde_json::from_str::<CacheFile>(&raw) {
            let fresh = cache.version == CACHE_VERSION
                && cache.platforms_dir == dir_str
                && cache.signature == signature
                && now_unix().saturating_sub(cache.built_at_unix) < CACHE_TTL_SECS;
            if fresh {
                return cache
                    .index
                    .into_iter()
                    .filter_map(|(k, v)| parse_key(&k).map(|kk| (kk, v)))
                    .collect();
            }
        }
    }

    let index = build_manifest_index(&dir);
    let cache = CacheFile {
        version: CACHE_VERSION,
        platforms_dir: dir_str,
        signature,
        built_at_unix: now_unix(),
        index: index
            .iter()
            .map(|(&(v, p), hit)| (key_str(v, p), hit.clone()))
            .collect(),
    };
    save_cache(&cache);
    index
}

fn save_cache(cache: &CacheFile) {
    let path = cache_path();
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(json) = serde_json::to_string_pretty(cache) {
        let tmp = path.with_extension("json.tmp");
        if std::fs::write(&tmp, json).is_ok() {
            let _ = std::fs::rename(&tmp, &path);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_index() -> HwidIndex {
        HashMap::new()
    }

    #[test]
    fn board_map_contains_arduino_uno() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, _, fqbn, _)| {
                vid == 0x2341 && pid == 0x0043 && fqbn == "arduino:avr:uno"
            }),
            "Arduino Uno (2341:0043) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_contains_esp32_cp210x() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, _, fqbn, _)| {
                vid == 0x10c4 && pid == 0xea60 && fqbn == "esp32:esp32:esp32"
            }),
            "ESP32 CP210x (10c4:ea60) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_contains_stlink_v2_1() {
        assert!(
            BOARD_MAP.iter().any(|&(vid, pid, name, _, _)| {
                vid == 0x0483 && pid == 0x374b && name == "STM32 (ST-Link V2-1)"
            }),
            "STM32 ST-Link V2-1 (0483:374b) missing from BOARD_MAP"
        );
    }

    #[test]
    fn board_map_contains_new_native_families() {
        // Layer A native-USB additions resolve via identify_ids (curated, empty Layer B).
        let idx = empty_index();
        for (vid, pid, want) in [
            (0x2e8a, 0x000a, "pico"),               // RP2040 Pico CDC
            (0x16c0, 0x0483, "teensy41"),           // Teensy
            (0x303a, 0x1001, "esp32-s3-devkitc-1"), // ESP32-S3 USB-JTAG
            (0x2a03, 0x0043, "uno"),                // Arduino SRL VID
        ] {
            let id = identify_ids(vid, pid, &idx)
                .unwrap_or_else(|| panic!("{vid:04x}:{pid:04x} not in BOARD_MAP"));
            assert_eq!(id.pio_board.as_deref(), Some(want));
        }
    }

    #[test]
    fn board_map_pio_boards_nonempty() {
        for &(vid, pid, name, _, pio) in BOARD_MAP {
            assert!(vid > 0, "vid == 0 for {name}");
            assert!(pid > 0, "pid == 0 for {name}");
            assert!(!pio.is_empty(), "empty pio_board for {name}");
        }
    }

    #[test]
    fn board_map_fqbns_have_two_colons() {
        for &(_, _, name, fqbn, _) in BOARD_MAP {
            assert_eq!(
                fqbn.chars().filter(|&c| c == ':').count(),
                2,
                "FQBN '{fqbn}' for {name} should have exactly 2 colons"
            );
        }
    }

    #[test]
    fn list_devices_does_not_panic() {
        let devices = list_devices();
        for d in &devices {
            assert!(!d.port.is_empty(), "device port should not be empty");
            // A device is identified by either an arduino FQBN (Layer A) or a pio_board
            // (Layer A/B); at least one must be present.
            assert!(
                !d.fqbn.is_empty() || d.pio_board.is_some(),
                "device must carry an fqbn or pio_board"
            );
            assert_eq!(d.vendor_id.len(), 4, "vendor_id should be 4 hex chars");
            assert_eq!(d.product_id.len(), 4, "product_id should be 4 hex chars");
        }
    }

    #[test]
    fn find_device_with_explicit_port_returns_none_when_not_connected() {
        let result = find_device(Some("COM_FAKE_999"));
        assert!(result.is_none());
    }

    #[test]
    fn pio_platform_lookup_known_and_unknown() {
        assert_eq!(pio_platform_for("esp32dev"), Some("espressif32"));
        assert_eq!(pio_platform_for("pico"), Some("raspberrypi"));
        assert_eq!(pio_platform_for("some_exotic_board"), None);
    }

    // ---- Layer B builder + precedence ----

    fn write_manifest(boards_dir: &Path, board_id: &str, name: &str, hwids_json: &str) {
        std::fs::create_dir_all(boards_dir).unwrap();
        let body =
            format!(r#"{{"name":"{name}","build":{{"mcu":"x","hwids":{hwids_json}}}}}"#);
        std::fs::write(boards_dir.join(format!("{board_id}.json")), body).unwrap();
    }

    #[test]
    fn manifest_index_indexes_unambiguous_native_board() {
        let tmp = std::env::temp_dir().join("nff_bt_idx_native");
        let _ = std::fs::remove_dir_all(&tmp);
        let boards = tmp.join("ststm32").join("boards");
        write_manifest(
            &boards,
            "bluepill_f103c8",
            "BluePill F103C8",
            r#"[["0x1EAF","0x0003"],["0x1EAF","0x0004"]]"#,
        );
        let idx = build_manifest_index(&tmp);
        let hit = idx.get(&(0x1eaf, 0x0003)).expect("1eaf:0003 indexed");
        assert_eq!(hit.board, "bluepill_f103c8");
        assert_eq!(hit.platform, "ststm32");
        assert_eq!(hit.name, "BluePill F103C8");
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn manifest_index_drops_ambiguous_id() {
        let tmp = std::env::temp_dir().join("nff_bt_idx_ambig");
        let _ = std::fs::remove_dir_all(&tmp);
        let boards = tmp.join("espressif32").join("boards");
        write_manifest(&boards, "board_a", "Board A", r#"[["0x303a","0x4001"]]"#);
        write_manifest(&boards, "board_b", "Board B", r#"[["0x303a","0x4001"]]"#);
        let idx = build_manifest_index(&tmp);
        assert!(
            !idx.contains_key(&(0x303a, 0x4001)),
            "ambiguous id must be dropped"
        );
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn manifest_index_skips_bridge_vids() {
        let tmp = std::env::temp_dir().join("nff_bt_idx_bridge");
        let _ = std::fs::remove_dir_all(&tmp);
        let boards = tmp.join("espressif32").join("boards");
        write_manifest(&boards, "esp32-evb", "Olimex EVB", r#"[["0x1a86","0x7523"]]"#);
        let idx = build_manifest_index(&tmp);
        assert!(
            !idx.contains_key(&(0x1a86, 0x7523)),
            "bridge VID must be skipped"
        );
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn manifest_index_tolerates_malformed() {
        let tmp = std::env::temp_dir().join("nff_bt_idx_bad");
        let _ = std::fs::remove_dir_all(&tmp);
        let boards = tmp.join("ststm32").join("boards");
        std::fs::create_dir_all(&boards).unwrap();
        std::fs::write(boards.join("broken.json"), "{ not json").unwrap();
        // 3-element hwid + non-hex sibling, plus one good entry.
        write_manifest(
            &boards,
            "good",
            "Good Board",
            r#"[["0xCAFE","0x0001","extra"],["zz","yy"],["0xCAFE","0x0002"]]"#,
        );
        let idx = build_manifest_index(&tmp);
        assert_eq!(
            idx.get(&(0xcafe, 0x0001)).map(|h| h.board.as_str()),
            Some("good")
        );
        assert_eq!(
            idx.get(&(0xcafe, 0x0002)).map(|h| h.board.as_str()),
            Some("good")
        );
        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn curated_wins_over_manifest_for_shared_chip() {
        // Even if a manifest somehow surfaces the CH340 id, the curated default wins.
        let mut idx = empty_index();
        idx.insert(
            (0x1a86, 0x7523),
            Hit {
                name: "Some Olimex Board".into(),
                board: "esp32-evb".into(),
                platform: "espressif32".into(),
            },
        );
        let id = identify_ids(0x1a86, 0x7523, &idx).unwrap();
        assert_eq!(id.board, "ESP32 (CH340)");
        assert_eq!(id.pio_board.as_deref(), Some("esp32dev"));
    }

    #[test]
    fn layer_b_hit_has_empty_fqbn_and_pio_board() {
        let mut idx = empty_index();
        idx.insert(
            (0x1eaf, 0x0003),
            Hit {
                name: "BluePill F103C8".into(),
                board: "bluepill_f103c8".into(),
                platform: "ststm32".into(),
            },
        );
        let id = identify_ids(0x1eaf, 0x0003, &idx).unwrap();
        assert_eq!(id.fqbn, "");
        assert_eq!(id.pio_board.as_deref(), Some("bluepill_f103c8"));
    }

    #[test]
    fn missing_platforms_dir_yields_empty_index() {
        let idx = build_manifest_index(Path::new("/nope/does/not/exist/platforms"));
        assert!(idx.is_empty());
    }
}
