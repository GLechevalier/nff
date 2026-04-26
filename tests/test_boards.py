"""Tests for nff.tools.boards — ID normalisation, device detection, lookup."""

from unittest.mock import MagicMock, patch

from nff.tools.boards import (
    BOARD_MAP,
    DetectedDevice,
    _identify,
    _normalize_id,
    find_device,
    list_devices,
)


# ---------------------------------------------------------------------------
# _normalize_id
# ---------------------------------------------------------------------------

def test_normalize_none_returns_empty_string():
    assert _normalize_id(None) == ""


def test_normalize_int_pads_to_four_chars():
    assert _normalize_id(0x2341) == "2341"
    assert _normalize_id(0x10C4) == "10c4"
    assert _normalize_id(5) == "0005"


def test_normalize_string_lowercases_and_pads():
    assert _normalize_id("EA60") == "ea60"
    assert _normalize_id("7523") == "7523"
    assert _normalize_id("5") == "0005"


def test_normalize_already_normalized_string():
    assert _normalize_id("10c4") == "10c4"


# ---------------------------------------------------------------------------
# _identify
# ---------------------------------------------------------------------------

def _make_port(vid, pid, device="COM10"):
    p = MagicMock()
    p.vid = vid
    p.pid = pid
    p.device = device
    return p


def test_identify_known_vid_pid_returns_device():
    port = _make_port(0x10C4, 0xEA60)
    device = _identify(port)
    assert device is not None
    assert device.board == "ESP32 (CP210x)"
    assert device.fqbn == "esp32:esp32:esp32"
    assert device.port == "COM10"
    assert device.vendor_id == "10c4"
    assert device.product_id == "ea60"


def test_identify_arduino_uno():
    port = _make_port(0x2341, 0x0043, device="/dev/ttyUSB0")
    device = _identify(port)
    assert device is not None
    assert device.board == "Arduino Uno"
    assert device.fqbn == "arduino:avr:uno"
    assert device.port == "/dev/ttyUSB0"


def test_identify_unknown_vid_pid_returns_none():
    port = _make_port(0xDEAD, 0xBEEF)
    assert _identify(port) is None


def test_identify_none_vid_returns_none():
    port = _make_port(None, None)
    assert _identify(port) is None


# ---------------------------------------------------------------------------
# list_devices
# ---------------------------------------------------------------------------

def test_list_devices_returns_known_boards():
    ports = [
        _make_port(0x10C4, 0xEA60, "COM10"),
        _make_port(0xDEAD, 0xBEEF, "COM11"),  # unknown
        _make_port(0x2341, 0x0043, "COM12"),
    ]
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=ports):
        devices = list_devices()
    assert len(devices) == 2
    assert devices[0].port == "COM10"
    assert devices[1].port == "COM12"


def test_list_devices_returns_empty_when_no_known_boards():
    ports = [_make_port(0xDEAD, 0xBEEF, "COM9")]
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=ports):
        assert list_devices() == []


def test_list_devices_returns_empty_on_no_ports():
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=[]):
        assert list_devices() == []


# ---------------------------------------------------------------------------
# find_device
# ---------------------------------------------------------------------------

def test_find_device_returns_first_without_port_filter():
    ports = [
        _make_port(0x10C4, 0xEA60, "COM10"),
        _make_port(0x2341, 0x0043, "COM12"),
    ]
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=ports):
        device = find_device()
    assert device is not None
    assert device.port == "COM10"


def test_find_device_filters_by_port():
    ports = [
        _make_port(0x10C4, 0xEA60, "COM10"),
        _make_port(0x2341, 0x0043, "COM12"),
    ]
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=ports):
        device = find_device("COM12")
    assert device is not None
    assert device.board == "Arduino Uno"


def test_find_device_returns_none_when_port_not_found():
    ports = [_make_port(0x10C4, 0xEA60, "COM10")]
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=ports):
        assert find_device("COM99") is None


def test_find_device_returns_none_when_no_devices():
    with patch("nff.tools.boards.serial.tools.list_ports.comports", return_value=[]):
        assert find_device() is None


# ---------------------------------------------------------------------------
# BOARD_MAP completeness
# ---------------------------------------------------------------------------

def test_board_map_has_required_boards():
    names = {v["name"] for v in BOARD_MAP.values()}
    assert "Arduino Uno" in names
    assert "ESP32 (CP210x)" in names
    assert "ESP32 (CH340)" in names
    assert "ESP8266 (FTDI)" in names


def test_detected_device_is_dataclass():
    d = DetectedDevice(port="COM1", board="Test", fqbn="a:b:c",
                       vendor_id="1234", product_id="5678")
    assert d.port == "COM1"
    assert d.fqbn == "a:b:c"
