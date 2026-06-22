"""Tests for nff.tools.netinfo.detect_wifi (best-effort, never raises)."""

from unittest.mock import patch

from nff.tools import netinfo


def _fake_run(mapping):
    """Return a _run replacement that keys off the first token of the command."""
    def runner(cmd, timeout=6):
        return mapping.get(cmd[0], "")
    return runner


def test_detect_wifi_windows(monkeypatch):
    monkeypatch.setattr(netinfo.sys, "platform", "win32")
    # _win_password reads an exported XML; mock it directly to avoid tempdir/glob.
    with patch("nff.tools.netinfo._run",
               side_effect=_fake_run({"netsh": "    SSID                   : HomeNet\n"})), \
         patch("nff.tools.netinfo._win_password", return_value="s3cret"):
        ssid, pw = netinfo.detect_wifi()
    assert ssid == "HomeNet"
    assert pw == "s3cret"


def test_detect_wifi_linux_nmcli(monkeypatch):
    monkeypatch.setattr(netinfo.sys, "platform", "linux")
    mapping = {
        "nmcli": "no:OtherNet\nyes:HomeNet\n",  # _linux_ssid picks the active "yes:" line
    }

    # second nmcli call (password) needs a different return; route by args instead.
    def runner(cmd, timeout=6):
        if cmd[0] == "nmcli" and "802-11-wireless-security.psk" in cmd:
            return "wifipass\n"
        if cmd[0] == "nmcli":
            return mapping["nmcli"]
        return ""

    with patch("nff.tools.netinfo._run", side_effect=runner):
        ssid, pw = netinfo.detect_wifi()
    assert ssid == "HomeNet"
    assert pw == "wifipass"


def test_detect_wifi_macos(monkeypatch):
    monkeypatch.setattr(netinfo.sys, "platform", "darwin")

    def runner(cmd, timeout=6):
        if cmd[0].endswith("airport"):
            return "     SSID: MacNet\n"
        if cmd[0] == "security":
            return "macpass\n"
        return ""

    with patch("nff.tools.netinfo._run", side_effect=runner):
        ssid, pw = netinfo.detect_wifi()
    assert ssid == "MacNet"
    assert pw == "macpass"


def test_detect_wifi_returns_none_when_no_ssid(monkeypatch):
    monkeypatch.setattr(netinfo.sys, "platform", "linux")
    with patch("nff.tools.netinfo._run", return_value=""):
        ssid, pw = netinfo.detect_wifi()
    assert ssid is None
    assert pw is None


def test_detect_wifi_never_raises(monkeypatch):
    monkeypatch.setattr(netinfo.sys, "platform", "linux")
    with patch("nff.tools.netinfo._linux_ssid", side_effect=RuntimeError("boom")):
        assert netinfo.detect_wifi() == (None, None)


def test_run_swallows_subprocess_errors():
    with patch("nff.tools.netinfo.subprocess.run", side_effect=OSError("nope")):
        assert netinfo._run(["anything"]) == ""
