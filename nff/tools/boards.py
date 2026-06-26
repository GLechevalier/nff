"""USB board detection via pyserial port enumeration.

Detection runs two layers, curated-first (kept identical in `nff-rs/.../tools/boards.rs`):

  Layer A — the curated ``BOARD_MAP`` (VID:PID → board). Authoritative: it always wins, so
    the shared USB-serial bridges (CP210x/CH340/FTDI) and ST-Link keep their hand-chosen
    family default even when a PlatformIO manifest also claims that id.
  Layer B — a fallback index built from installed PlatformIO board manifests' ``build.hwids``,
    consulted only when Layer A misses. It is de-ambiguated (a VID:PID mapping to >1 board is
    dropped) and skips the shared-bridge VIDs, so it only ever adds *unambiguous native-USB*
    boards. The index is cached under the config dir.

A USB-serial bridge chip is shared by hundreds of boards, so VID:PID can only ever be a
sensible *default* the user overrides with --board.
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import serial.tools.list_ports

# USB VID:PID → board identity. ``fqbn`` is the arduino-cli identifier; ``pio_board``
# is the PlatformIO board id used when the platformio backend is active. A USB-serial
# chip (CP210x/CH340/FTDI) is shared by many distinct boards, so ``pio_board`` is only
# a sensible *default* the user can override with --board.
BOARD_MAP: dict[tuple[int, int], dict] = {
    (0x2341, 0x0043): {"name": "Arduino Uno",       "fqbn": "arduino:avr:uno",         "pio_board": "uno"},
    (0x2341, 0x0010): {"name": "Arduino Mega 2560", "fqbn": "arduino:avr:mega",        "pio_board": "megaatmega2560"},
    (0x2341, 0x0036): {"name": "Arduino Leonardo",  "fqbn": "arduino:avr:leonardo",    "pio_board": "leonardo"},
    (0x2341, 0x0058): {"name": "Arduino Nano",      "fqbn": "arduino:avr:nano",        "pio_board": "nanoatmega328"},
    # Arduino SRL / older "Arduino.org" boards reuse the same PIDs under VID 0x2A03.
    (0x2A03, 0x0043): {"name": "Arduino Uno",       "fqbn": "arduino:avr:uno",         "pio_board": "uno"},
    (0x2A03, 0x0010): {"name": "Arduino Mega 2560", "fqbn": "arduino:avr:mega",        "pio_board": "megaatmega2560"},
    (0x2A03, 0x0036): {"name": "Arduino Leonardo",  "fqbn": "arduino:avr:leonardo",    "pio_board": "leonardo"},
    (0x2A03, 0x0058): {"name": "Arduino Nano",      "fqbn": "arduino:avr:nano",        "pio_board": "nanoatmega328"},
    (0x10c4, 0xea60): {"name": "ESP32 (CP210x)",    "fqbn": "esp32:esp32:esp32",       "pio_board": "esp32dev"},
    (0x1a86, 0x7523): {"name": "ESP32 (CH340)",     "fqbn": "esp32:esp32:esp32",       "pio_board": "esp32dev"},
    (0x0403, 0x6001): {"name": "ESP8266 (FTDI)",    "fqbn": "esp8266:esp8266:generic", "pio_board": "esp01_1m"},
    # ESP32-S3/C3 native USB-Serial-JTAG. 0x303a:0x1001 is shared across many S3/C3 boards
    # (so Layer B drops it as ambiguous); default to an S3 devkit, override with --board.
    (0x303a, 0x1001): {"name": "ESP32-S3 (USB-JTAG)", "fqbn": "esp32:esp32:esp32s3",   "pio_board": "esp32-s3-devkitc-1"},
    # STMicroelectronics ST-Link debug+VCP bridges (on-board on Nucleo/Discovery and most
    # STM32 dev boards) and the DFU bootloader. One VID:PID covers many distinct STM32
    # boards, so fqbn/pio_board are only sensible defaults the user can override with --board.
    (0x0483, 0x3748): {"name": "STM32 (ST-Link V2)",         "fqbn": "STMicroelectronics:stm32:Nucleo_64", "pio_board": "nucleo_f401re"},
    (0x0483, 0x374b): {"name": "STM32 (ST-Link V2-1)",       "fqbn": "STMicroelectronics:stm32:Nucleo_64", "pio_board": "nucleo_f401re"},
    (0x0483, 0x374e): {"name": "STM32 (ST-Link V3)",         "fqbn": "STMicroelectronics:stm32:Nucleo_64", "pio_board": "nucleo_f401re"},
    (0x0483, 0x374f): {"name": "STM32 (ST-Link V3)",         "fqbn": "STMicroelectronics:stm32:Nucleo_64", "pio_board": "nucleo_f401re"},
    (0x0483, 0xdf11): {"name": "STM32 (DFU bootloader)",     "fqbn": "STMicroelectronics:stm32:GenF1",      "pio_board": "genericSTM32F103C8"},
    # RP2040 Raspberry Pi Pico — arduino-pico CDC serial (0x2e8a:0x000a). The 0x2e8a:0x0003
    # BOOTSEL device is USB mass-storage, never a serial port, so it is intentionally absent.
    (0x2e8a, 0x000a): {"name": "Raspberry Pi Pico", "fqbn": "rp2040:rp2040:rpipico",   "pio_board": "pico"},
    # Teensy (PJRC) serial. Qualify by the exact pair — bare 0x16c0 is a shared hobby VID.
    # All Teensy models share this pair, so default to a recent one; override with --board.
    (0x16c0, 0x0483): {"name": "Teensy (PJRC)",     "fqbn": "teensy:avr:teensy41",     "pio_board": "teensy41"},
}

# PlatformIO board catalog: board id → {platform, framework}. PlatformIO supports ~1000
# boards and auto-installs the platform toolchain on first build, so this is NOT an
# allow-list — any board id is accepted by the pio backend. The catalog only supplies
# the platform/framework defaults (so the user need only name a board). ``framework``
# is "arduino" for everything we scaffold here (we generate Arduino-style src/main.cpp).
PIO_BOARD_CATALOG: dict[str, dict] = {
    # ESP32 family
    "esp32dev":               {"platform": "espressif32", "framework": "arduino"},
    "esp32-s3-devkitc-1":     {"platform": "espressif32", "framework": "arduino"},
    "esp32-c3-devkitm-1":     {"platform": "espressif32", "framework": "arduino"},
    "esp32-c6-devkitc-1":     {"platform": "espressif32", "framework": "arduino"},
    "esp32-s2-saola-1":       {"platform": "espressif32", "framework": "arduino"},
    # ESP8266
    "esp01_1m":               {"platform": "espressif8266", "framework": "arduino"},
    "nodemcuv2":              {"platform": "espressif8266", "framework": "arduino"},
    # RP2040 / Raspberry Pi Pico
    "pico":                   {"platform": "raspberrypi", "framework": "arduino"},
    "rpipicow":               {"platform": "raspberrypi", "framework": "arduino"},
    # STM32
    "genericSTM32F103C8":     {"platform": "ststm32", "framework": "arduino"},
    "nucleo_f401re":          {"platform": "ststm32", "framework": "arduino"},
    "bluepill_f103c8":        {"platform": "ststm32", "framework": "arduino"},
    # Classic AVR
    "uno":                    {"platform": "atmelavr", "framework": "arduino"},
    "megaatmega2560":         {"platform": "atmelavr", "framework": "arduino"},
    "nanoatmega328":          {"platform": "atmelavr", "framework": "arduino"},
    "leonardo":               {"platform": "atmelavr", "framework": "arduino"},
    # Teensy
    "teensy41":               {"platform": "teensy", "framework": "arduino"},
}

# Shared USB-serial bridge VIDs (CP210x / CH340 / FTDI). A board's *real* identity can't be
# inferred from these, so Layer B never trusts a manifest that claims one — they stay owned
# by the curated map's family defaults.
_BRIDGE_VIDS = frozenset({0x10c4, 0x1a86, 0x0403})

# Cache schema version — bump to force a rebuild when the index format changes.
_CACHE_VERSION = 1
# Rebuild the manifest index at least this often (backstops mtime-resolution gaps).
_CACHE_TTL_SECS = 24 * 60 * 60


def pio_platform_for(board: str) -> Optional[str]:
    """Best-effort PlatformIO platform for a board id, or None if unknown (the pio
    backend then omits an explicit platform and lets PlatformIO resolve it)."""
    info = PIO_BOARD_CATALOG.get(board)
    return info.get("platform") if info else None


def fqbn_to_pio_board(fqbn: str) -> Optional[str]:
    """Map an arduino-cli FQBN to a default PlatformIO board id (via BOARD_MAP), so the
    pio backend works without --board even when build.board was never persisted."""
    for entry in BOARD_MAP.values():
        if entry.get("fqbn") == fqbn:
            return entry.get("pio_board")
    return None


@dataclass
class DetectedDevice:
    port: str
    board: str
    fqbn: str
    vendor_id: str
    product_id: str
    pio_board: Optional[str] = None


def _normalize_id(val) -> str:
    if val is None:
        return ""
    if isinstance(val, int):
        return f"{val:04x}"
    return str(val).lower().zfill(4)


def identify_ids(vid: int, pid: int, index: dict) -> Optional[dict]:
    """Resolve a (vid,pid) to a board identity: curated Layer A first (authoritative),
    then the Layer B manifest ``index``. Pure — the caller supplies the index, so it is
    testable offline. Returns ``{"board", "fqbn", "pio_board"}`` or None."""
    info = BOARD_MAP.get((vid, pid))
    if info is not None:
        return {"board": info["name"], "fqbn": info["fqbn"], "pio_board": info.get("pio_board")}
    hit = index.get((vid, pid))
    if hit is not None:
        # No arduino-cli FQBN is derivable from a PlatformIO manifest; the default (pio)
        # backend identifies the board via pio_board instead.
        return {"board": hit["name"], "fqbn": "", "pio_board": hit["board"]}
    return None


def _identify(port, index: Optional[dict] = None) -> Optional[DetectedDevice]:
    vid = port.vid
    pid = port.pid
    if vid is None or pid is None:
        return None
    if index is None:
        index = manifest_index()
    ident = identify_ids(vid, pid, index)
    if ident is None:
        return None
    return DetectedDevice(
        port=port.device,
        board=ident["board"],
        fqbn=ident["fqbn"],
        vendor_id=_normalize_id(vid),
        product_id=_normalize_id(pid),
        pio_board=ident["pio_board"],
    )


def list_devices() -> list[DetectedDevice]:
    index = manifest_index()
    result = []
    for port in serial.tools.list_ports.comports():
        device = _identify(port, index)
        if device is not None:
            result.append(device)
    return result


def find_device(port: Optional[str] = None) -> Optional[DetectedDevice]:
    index = manifest_index()
    for p in serial.tools.list_ports.comports():
        if port is not None and p.device != port:
            continue
        device = _identify(p, index)
        if device is not None:
            return device
    return None


# ---------------------------------------------------------------------------
# Layer B — PlatformIO manifest hwid index (+ cache)
# ---------------------------------------------------------------------------


def _platforms_dir() -> Path:
    """``<PLATFORMIO_CORE_DIR or ~/.platformio>/platforms``, where installed platforms
    keep their per-board manifest JSONs."""
    core = os.environ.get("PLATFORMIO_CORE_DIR")
    base = Path(core) if core else Path.home() / ".platformio"
    return base / "platforms"


def _parse_hex(s) -> Optional[int]:
    if not isinstance(s, str):
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


def _build_manifest_index(platforms_dir: Path) -> dict[tuple[int, int], dict]:
    """Build the (vid,pid) → hit index from installed PlatformIO board manifests. Pure: it
    only reads ``platforms_dir``. Skips bridge VIDs and drops any id claimed by >1 board.
    Each hit is ``{"name", "board", "platform"}``."""
    claims: dict[tuple[int, int], dict] = {}
    board_ids: dict[tuple[int, int], set] = {}

    if not platforms_dir.is_dir():
        return {}
    for platform_path in platforms_dir.iterdir():
        if not platform_path.is_dir():
            continue
        platform = platform_path.name
        boards_dir = platform_path / "boards"
        if not boards_dir.is_dir():
            continue
        for manifest in boards_dir.glob("*.json"):
            board_id = manifest.stem
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # unreadable or malformed manifest — skip
            hwids = data.get("build", {}).get("hwids")
            if not isinstance(hwids, list):
                continue
            name = data.get("name") or board_id
            for hw in hwids:
                if not isinstance(hw, (list, tuple)) or len(hw) < 2:
                    continue  # ignore malformed; a 3rd+ element is ignored too
                vid = _parse_hex(hw[0])
                pid = _parse_hex(hw[1])
                if vid is None or pid is None:
                    continue
                if vid in _BRIDGE_VIDS:
                    continue
                board_ids.setdefault((vid, pid), set()).add(board_id)
                claims.setdefault((vid, pid), {"name": name, "board": board_id, "platform": platform})

    # Keep only ids that resolve to exactly one board (drop cross-board/platform collisions).
    return {k: v for k, v in claims.items() if len(board_ids.get(k, ())) == 1}


def _cache_path() -> Path:
    from nff import config
    return config.CONFIG_DIR / "board_hwids_cache.json"


def _current_signature(platforms_dir: Path) -> int:
    """Cheap fingerprint of the platforms dir: summed mtime-ns of the dir itself plus each
    immediate platform subdir. Catches platform install/remove (subdir count changes) and
    upgrade (subdir mtime changes) without walking every board manifest."""
    def mtime_ns(p: Path) -> int:
        try:
            return p.stat().st_mtime_ns
        except OSError:
            return 0

    sig = mtime_ns(platforms_dir)
    if platforms_dir.is_dir():
        for entry in platforms_dir.iterdir():
            sig = (sig + mtime_ns(entry)) & 0xFFFFFFFFFFFFFFFF
    return sig


def _parse_key(key: str) -> Optional[tuple[int, int]]:
    parts = key.split(":")
    if len(parts) != 2:
        return None
    vid = _parse_hex(parts[0])
    pid = _parse_hex(parts[1])
    return (vid, pid) if vid is not None and pid is not None else None


def _save_cache(dir_str: str, signature: int, index: dict[tuple[int, int], dict]) -> None:
    path = _cache_path()
    payload = {
        "version": _CACHE_VERSION,
        "platforms_dir": dir_str,
        "signature": signature,
        "built_at_unix": int(time.time()),
        "index": {f"{vid:04x}:{pid:04x}": hit for (vid, pid), hit in index.items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # cache is best-effort


def _resolve_index() -> dict[tuple[int, int], dict]:
    platforms_dir = _platforms_dir()
    dir_str = str(platforms_dir)
    signature = _current_signature(platforms_dir)

    # Use a fresh cache if it matches this platforms dir, version, signature, and TTL.
    try:
        cache = json.loads(_cache_path().read_text(encoding="utf-8"))
        fresh = (
            cache.get("version") == _CACHE_VERSION
            and cache.get("platforms_dir") == dir_str
            and cache.get("signature") == signature
            and (time.time() - cache.get("built_at_unix", 0)) < _CACHE_TTL_SECS
        )
        if fresh:
            out = {}
            for key, hit in cache.get("index", {}).items():
                vid_pid = _parse_key(key)
                if vid_pid is not None:
                    out[vid_pid] = hit
            return out
    except (OSError, ValueError):
        pass

    index = _build_manifest_index(platforms_dir)
    _save_cache(dir_str, signature, index)
    return index


_INDEX_MEMO: Optional[dict[tuple[int, int], dict]] = None


def manifest_index() -> dict[tuple[int, int], dict]:
    """Process-wide memoized Layer B index. The long-lived ``nff mcp`` server builds it at
    most once; a mid-session platform install is only picked up on next start (cache
    TTL/signature are re-checked there). Built from cache when fresh, else rebuilt + cached."""
    global _INDEX_MEMO
    if _INDEX_MEMO is None:
        _INDEX_MEMO = _resolve_index()
    return _INDEX_MEMO
