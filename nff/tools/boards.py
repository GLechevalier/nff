"""USB board detection via pyserial port enumeration."""

from dataclasses import dataclass, field
from typing import Optional

import serial.tools.list_ports

BOARD_MAP: dict[tuple[int, int], dict] = {
    (0x2341, 0x0043): {"name": "Arduino Uno",       "fqbn": "arduino:avr:uno",         "wokwi_chip": "wokwi-arduino-uno"},
    (0x2341, 0x0010): {"name": "Arduino Mega 2560", "fqbn": "arduino:avr:mega",        "wokwi_chip": "wokwi-arduino-mega"},
    (0x2341, 0x0036): {"name": "Arduino Leonardo",  "fqbn": "arduino:avr:leonardo",    "wokwi_chip": "wokwi-arduino-leonardo"},
    (0x2341, 0x0058): {"name": "Arduino Nano",      "fqbn": "arduino:avr:nano",        "wokwi_chip": "wokwi-arduino-nano"},
    (0x10c4, 0xea60): {"name": "ESP32 (CP210x)",    "fqbn": "esp32:esp32:esp32",       "wokwi_chip": "wokwi-esp32-devkit-v1"},
    (0x1a86, 0x7523): {"name": "ESP32 (CH340)",     "fqbn": "esp32:esp32:esp32",       "wokwi_chip": "wokwi-esp32-devkit-v1"},
    (0x0403, 0x6001): {"name": "ESP8266 (FTDI)",    "fqbn": "esp8266:esp8266:generic", "wokwi_chip": "wokwi-esp8266"},
}


@dataclass
class DetectedDevice:
    port: str
    board: str
    fqbn: str
    vendor_id: str
    product_id: str
    wokwi_chip: Optional[str] = None


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
