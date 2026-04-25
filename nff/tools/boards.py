"""USB vendor/product ID detection and board identification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import serial.tools.list_ports
from serial.tools.list_ports_common import ListPortInfo

# Maps (vendor_id, product_id) hex strings (lower-case) to board metadata.
BOARD_MAP: dict[tuple[str, str], dict[str, str]] = {
    ("2341", "0043"): {"name": "Arduino Uno",      "fqbn": "arduino:avr:uno"},
    ("2341", "0010"): {"name": "Arduino Mega 2560", "fqbn": "arduino:avr:mega"},
    ("2341", "0036"): {"name": "Arduino Leonardo",  "fqbn": "arduino:avr:leonardo"},
    ("2341", "0058"): {"name": "Arduino Nano",      "fqbn": "arduino:avr:nano"},
    ("10c4", "ea60"): {"name": "ESP32 (CP210x)",    "fqbn": "esp32:esp32:esp32"},
    ("1a86", "7523"): {"name": "ESP32 (CH340)",     "fqbn": "esp32:esp32:esp32"},
    ("0403", "6001"): {"name": "ESP8266 (FTDI)",    "fqbn": "esp8266:esp8266:generic"},
}


@dataclass
class DetectedDevice:
    port: str
    board: str
    fqbn: str
    vendor_id: str
    product_id: str


def _normalize_id(raw: int | str | None) -> str:
    """Return a zero-padded 4-char lower-case hex string, or '' if absent."""
    if raw is None:
        return ""
    if isinstance(raw, int):
        return f"{raw:04x}"
    return str(raw).lower().zfill(4)


def _identify(port_info: ListPortInfo) -> DetectedDevice | None:
    """Return a DetectedDevice for *port_info*, or None if unrecognised."""
    vid = _normalize_id(port_info.vid)
    pid = _normalize_id(port_info.pid)
    meta = BOARD_MAP.get((vid, pid))
    if meta is None:
        return None
    return DetectedDevice(
        port=port_info.device,
        board=meta["name"],
        fqbn=meta["fqbn"],
        vendor_id=vid,
        product_id=pid,
    )


def list_devices() -> list[DetectedDevice]:
    """Return all connected USB devices that match a known board."""
    return [d for d in _iter_all_devices() if d is not None]


def _iter_all_devices() -> Iterator[DetectedDevice | None]:
    for port_info in serial.tools.list_ports.comports():
        yield _identify(port_info)


def find_device(port: str | None = None) -> DetectedDevice | None:
    """Return the first recognised device, optionally filtered by *port*."""
    for device in list_devices():
        if port is None or device.port == port:
            return device
    return None
