"""Tests for nff.tools.boards — ID normalisation, device detection, lookup."""

from unittest.mock import MagicMock, patch

import json

from nff.tools.boards import (
    BOARD_MAP,
    DetectedDevice,
    _build_manifest_index,
    _identify,
    _normalize_id,
    find_device,
    identify_ids,
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


def test_board_map_has_new_native_families():
    # Layer A native-USB additions resolve via identify_ids (curated, empty Layer B index).
    cases = {
        (0x2e8a, 0x000a): "pico",                # RP2040 Pico CDC
        (0x16c0, 0x0483): "teensy41",            # Teensy
        (0x303a, 0x1001): "esp32-s3-devkitc-1",  # ESP32-S3 USB-JTAG
        (0x2A03, 0x0043): "uno",                 # Arduino SRL VID
    }
    for (vid, pid), want in cases.items():
        ident = identify_ids(vid, pid, {})
        assert ident is not None, f"{vid:04x}:{pid:04x} not in BOARD_MAP"
        assert ident["pio_board"] == want


# ---------------------------------------------------------------------------
# Layer B — PlatformIO manifest hwid index + precedence
# ---------------------------------------------------------------------------

def _write_manifest(boards_dir, board_id, name, hwids):
    boards_dir.mkdir(parents=True, exist_ok=True)
    body = {"name": name, "build": {"mcu": "x", "hwids": hwids}}
    (boards_dir / f"{board_id}.json").write_text(json.dumps(body), encoding="utf-8")


def test_build_manifest_index_native_board(tmp_path):
    boards = tmp_path / "ststm32" / "boards"
    _write_manifest(boards, "bluepill_f103c8", "BluePill F103C8",
                    [["0x1EAF", "0x0003"], ["0x1EAF", "0x0004"]])
    idx = _build_manifest_index(tmp_path)
    hit = idx[(0x1EAF, 0x0003)]
    assert hit["board"] == "bluepill_f103c8"
    assert hit["platform"] == "ststm32"
    assert hit["name"] == "BluePill F103C8"


def test_build_manifest_index_drops_ambiguous(tmp_path):
    boards = tmp_path / "espressif32" / "boards"
    _write_manifest(boards, "board_a", "Board A", [["0x303a", "0x4001"]])
    _write_manifest(boards, "board_b", "Board B", [["0x303a", "0x4001"]])
    idx = _build_manifest_index(tmp_path)
    assert (0x303a, 0x4001) not in idx


def test_build_manifest_index_skips_bridge_vid(tmp_path):
    boards = tmp_path / "espressif32" / "boards"
    _write_manifest(boards, "esp32-evb", "Olimex EVB", [["0x1a86", "0x7523"]])
    idx = _build_manifest_index(tmp_path)
    assert (0x1a86, 0x7523) not in idx


def test_build_manifest_index_tolerates_malformed(tmp_path):
    boards = tmp_path / "ststm32" / "boards"
    boards.mkdir(parents=True, exist_ok=True)
    (boards / "broken.json").write_text("{ not json", encoding="utf-8")
    _write_manifest(boards, "good", "Good Board",
                    [["0xCAFE", "0x0001", "extra"], ["zz", "yy"], ["0xCAFE", "0x0002"]])
    idx = _build_manifest_index(tmp_path)
    assert idx[(0xCAFE, 0x0001)]["board"] == "good"
    assert idx[(0xCAFE, 0x0002)]["board"] == "good"


def test_build_manifest_index_missing_dir(tmp_path):
    assert _build_manifest_index(tmp_path / "nope" / "platforms") == {}


def test_identify_curated_wins_over_manifest():
    # Even if a manifest surfaces the CH340 id, the curated default wins.
    index = {(0x1a86, 0x7523): {"name": "Some Olimex", "board": "esp32-evb", "platform": "espressif32"}}
    ident = identify_ids(0x1a86, 0x7523, index)
    assert ident["board"] == "ESP32 (CH340)"
    assert ident["pio_board"] == "esp32dev"


def test_identify_layer_b_hit_has_empty_fqbn():
    index = {(0x1EAF, 0x0003): {"name": "BluePill F103C8", "board": "bluepill_f103c8", "platform": "ststm32"}}
    ident = identify_ids(0x1EAF, 0x0003, index)
    assert ident["fqbn"] == ""
    assert ident["pio_board"] == "bluepill_f103c8"


def test_identify_unknown_returns_none_with_empty_index():
    assert identify_ids(0xDEAD, 0xBEEF, {}) is None
