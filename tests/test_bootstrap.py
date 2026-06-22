"""Tests for nff.tools.bootstrap — onboarding sketch prep + claim watching."""

from unittest.mock import patch

import pytest

from nff.tools import bootstrap
from nff.tools.bootstrap import BootstrapError


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------

def test_c_escape_handles_quotes_and_backslashes():
    assert bootstrap._c_escape(r'p\a"ss') == r'p\\a\"ss'


def test_template_defines_rewrites_only_listed_names():
    ino = '\n'.join([
        '#define WIFI_SSID "old"',
        '#define WIFI_PASS "old"',
        '#define KEEP_ME "untouched"',
        'void setup(){}',
    ])
    out = bootstrap._template_defines(ino, {"WIFI_SSID": "home", "WIFI_PASS": 'p"w'})
    assert '#define WIFI_SSID "home"' in out
    assert '#define WIFI_PASS "p\\"w"' in out
    assert '#define KEEP_ME "untouched"' in out  # not in values → left alone
    assert 'void setup(){}' in out


# ---------------------------------------------------------------------------
# prepare_bootstrap_sketch — against the real bundled asset sketch
# ---------------------------------------------------------------------------

def test_prepare_bootstrap_sketch_templates_and_writes_credentials(tmp_path):
    dest = tmp_path / "sketch"
    result = bootstrap.prepare_bootstrap_sketch(
        credentials_h="// creds\n#define X 1\n",
        ssid="MyNet",
        password=r'se\cr"et',
        broker_host="10.0.0.5",
        dest_dir=dest,
    )
    assert result == dest
    creds = (dest / "credentials.h").read_text(encoding="utf-8")
    assert "#define X 1" in creds

    ino = (dest / "arduino_bootstrap.ino").read_text(encoding="utf-8")
    # placeholders replaced (spacing in the #define is preserved, so match on the value)
    assert '"YOUR_WIFI_SSID"' not in ino
    assert '"MyNet"' in ino
    assert '"10.0.0.5"' in ino
    # password is C-escaped into the literal
    assert r'"se\\cr\"et"' in ino


def test_prepare_bootstrap_sketch_overwrites_existing_dest(tmp_path):
    dest = tmp_path / "sketch"
    dest.mkdir()
    (dest / "leftover.txt").write_text("stale", encoding="utf-8")
    bootstrap.prepare_bootstrap_sketch("c", "S", "P", "h", dest_dir=dest)
    assert not (dest / "leftover.txt").exists()  # copytree wiped + recreated


def test_prepare_bootstrap_sketch_raises_when_asset_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "ASSET_DIR", tmp_path / "does_not_exist")
    with pytest.raises(BootstrapError, match="bootstrap sketch missing"):
        bootstrap.prepare_bootstrap_sketch("c", "S", "P", "h", dest_dir=tmp_path / "x")


# ---------------------------------------------------------------------------
# watch_for_claim
# ---------------------------------------------------------------------------

def test_watch_for_claim_detects_claimed_marker():
    lines = ["BOOTSTRAP mode", "connecting…", "CLAIMED mode", "should-not-reach"]
    with patch("nff.tools.bootstrap.serial_tools.stream_lines", return_value=iter(lines)):
        results = list(bootstrap.watch_for_claim("COM3", 115200, timeout_s=5))
    # last yielded tuple is the claim, with result True
    assert results[-1] == ("CLAIMED mode", True)
    assert all(r[1] is None for r in results[:-1])
    # iteration stops at the claim — the trailing line is never yielded
    assert all(line != "should-not-reach" for line, _ in results)


def test_watch_for_claim_timeout_yields_no_true():
    lines = ["BOOTSTRAP mode", "still trying…"]
    with patch("nff.tools.bootstrap.serial_tools.stream_lines", return_value=iter(lines)):
        results = list(bootstrap.watch_for_claim("COM3", 115200, timeout_s=5))
    assert all(result is None for _line, result in results)


def test_watch_for_claim_wraps_serial_errors():
    with patch("nff.tools.bootstrap.serial_tools.stream_lines",
               side_effect=OSError("port busy")):
        with pytest.raises(BootstrapError, match="port busy"):
            list(bootstrap.watch_for_claim("COM3"))
