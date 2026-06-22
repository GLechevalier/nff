"""USB board detection via pyserial port enumeration."""

from dataclasses import dataclass, field
from typing import Optional

import serial.tools.list_ports

# USB VID:PID → board identity. ``fqbn`` is the arduino-cli identifier; ``pio_board``
# is the PlatformIO board id used when the platformio backend is active. A USB-serial
# chip (CP210x/CH340/FTDI) is shared by many distinct boards, so ``pio_board`` is only
# a sensible *default* the user can override with --board.
BOARD_MAP: dict[tuple[int, int], dict] = {
    (0x2341, 0x0043): {"name": "Arduino Uno",       "fqbn": "arduino:avr:uno",         "pio_board": "uno",             "wokwi_chip": "wokwi-arduino-uno"},
    (0x2341, 0x0010): {"name": "Arduino Mega 2560", "fqbn": "arduino:avr:mega",        "pio_board": "megaatmega2560",  "wokwi_chip": "wokwi-arduino-mega"},
    (0x2341, 0x0036): {"name": "Arduino Leonardo",  "fqbn": "arduino:avr:leonardo",    "pio_board": "leonardo",        "wokwi_chip": "wokwi-arduino-leonardo"},
    (0x2341, 0x0058): {"name": "Arduino Nano",      "fqbn": "arduino:avr:nano",        "pio_board": "nanoatmega328",   "wokwi_chip": "wokwi-arduino-nano"},
    (0x10c4, 0xea60): {"name": "ESP32 (CP210x)",    "fqbn": "esp32:esp32:esp32",       "pio_board": "esp32dev",        "wokwi_chip": "wokwi-esp32-devkit-v1"},
    (0x1a86, 0x7523): {"name": "ESP32 (CH340)",     "fqbn": "esp32:esp32:esp32",       "pio_board": "esp32dev",        "wokwi_chip": "wokwi-esp32-devkit-v1"},
    (0x0403, 0x6001): {"name": "ESP8266 (FTDI)",    "fqbn": "esp8266:esp8266:generic", "pio_board": "esp01_1m",        "wokwi_chip": "wokwi-esp8266"},
}

# PlatformIO board catalog: board id → {platform, framework, wokwi_chip}. PlatformIO
# supports ~1000 boards and auto-installs the platform toolchain on first build, so
# this is NOT an allow-list — any board id is accepted by the pio backend. The catalog
# only supplies the platform/framework defaults (so the user need only name a board)
# and the Wokwi chip mapping for `--sim`. ``framework`` is "arduino" for everything we
# scaffold here (we generate Arduino-style src/main.cpp).
PIO_BOARD_CATALOG: dict[str, dict] = {
    # ESP32 family
    "esp32dev":               {"platform": "espressif32", "framework": "arduino", "wokwi_chip": "wokwi-esp32-devkit-v1"},
    "esp32-s3-devkitc-1":     {"platform": "espressif32", "framework": "arduino", "wokwi_chip": "board-esp32-s3-devkitc-1"},
    "esp32-c3-devkitm-1":     {"platform": "espressif32", "framework": "arduino", "wokwi_chip": "board-esp32-c3-devkitm-1"},
    "esp32-c6-devkitc-1":     {"platform": "espressif32", "framework": "arduino", "wokwi_chip": "board-esp32-c6-devkitc-1"},
    "esp32-s2-saola-1":       {"platform": "espressif32", "framework": "arduino", "wokwi_chip": None},
    # ESP8266
    "esp01_1m":               {"platform": "espressif8266", "framework": "arduino", "wokwi_chip": "wokwi-esp8266"},
    "nodemcuv2":              {"platform": "espressif8266", "framework": "arduino", "wokwi_chip": "wokwi-esp8266"},
    # RP2040 / Raspberry Pi Pico
    "pico":                   {"platform": "raspberrypi", "framework": "arduino", "wokwi_chip": "wokwi-pi-pico"},
    "rpipicow":               {"platform": "raspberrypi", "framework": "arduino", "wokwi_chip": "wokwi-pi-pico-w"},
    # STM32
    "genericSTM32F103C8":     {"platform": "ststm32", "framework": "arduino", "wokwi_chip": None},
    "nucleo_f401re":          {"platform": "ststm32", "framework": "arduino", "wokwi_chip": None},
    "bluepill_f103c8":        {"platform": "ststm32", "framework": "arduino", "wokwi_chip": None},
    # Classic AVR
    "uno":                    {"platform": "atmelavr", "framework": "arduino", "wokwi_chip": "wokwi-arduino-uno"},
    "megaatmega2560":         {"platform": "atmelavr", "framework": "arduino", "wokwi_chip": "wokwi-arduino-mega"},
    "nanoatmega328":          {"platform": "atmelavr", "framework": "arduino", "wokwi_chip": "wokwi-arduino-nano"},
    "leonardo":               {"platform": "atmelavr", "framework": "arduino", "wokwi_chip": "wokwi-arduino-leonardo"},
}


def pio_platform_for(board: str) -> Optional[str]:
    """Best-effort PlatformIO platform for a board id, or None if unknown (the pio
    backend then omits an explicit platform and lets PlatformIO resolve it)."""
    info = PIO_BOARD_CATALOG.get(board)
    return info.get("platform") if info else None


def wokwi_chip_for(board: str) -> Optional[str]:
    """Wokwi chip for either an arduino FQBN or a PlatformIO board id."""
    info = PIO_BOARD_CATALOG.get(board)
    if info and info.get("wokwi_chip"):
        return info["wokwi_chip"]
    return None


@dataclass
class DetectedDevice:
    port: str
    board: str
    fqbn: str
    vendor_id: str
    product_id: str
    wokwi_chip: Optional[str] = None
    pio_board: Optional[str] = None


def _normalize_id(val) -> str:
    if val is None:
        return ""
    if isinstance(val, int):
        return f"{val:04x}"
    return str(val).lower().zfill(4)


def _identify(port) -> Optional[DetectedDevice]:
    vid = port.vid
    pid = port.pid
    if vid is None or pid is None:
        return None
    info = BOARD_MAP.get((vid, pid))
    if info is None:
        return None
    return DetectedDevice(
        port=port.device,
        board=info["name"],
        fqbn=info["fqbn"],
        vendor_id=_normalize_id(vid),
        product_id=_normalize_id(pid),
        wokwi_chip=info.get("wokwi_chip"),
        pio_board=info.get("pio_board"),
    )


def list_devices() -> list[DetectedDevice]:
    result = []
    for port in serial.tools.list_ports.comports():
        device = _identify(port)
        if device is not None:
            result.append(device)
    return result


def find_device(port: Optional[str] = None) -> Optional[DetectedDevice]:
    for p in serial.tools.list_ports.comports():
        if port is not None and p.device != port:
            continue
        device = _identify(p)
        if device is not None:
            return device
    return None
