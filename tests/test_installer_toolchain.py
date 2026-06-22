"""Tests for the arduino-cli runners (toolchain) and the ESP32 install helpers
(installer) added for `nff init` onboarding."""

from unittest.mock import MagicMock, patch

from nff.tools import installer, toolchain
from nff.tools.toolchain import ToolchainError


class _FakeStream:
    """Stand-in for toolchain.ProcessStream: iterable of lines + a returncode."""

    def __init__(self, lines, returncode=0):
        self._lines = lines
        self.returncode = returncode

    def __iter__(self):
        yield from self._lines


# ---------------------------------------------------------------------------
# toolchain.run_arduino_cli / stream_arduino_cli
# ---------------------------------------------------------------------------

def test_run_arduino_cli_invokes_cli_with_args():
    proc = MagicMock(returncode=0, stdout="ok", stderr="")
    with patch("nff.tools.toolchain.find_arduino_cli", return_value="/bin/arduino-cli"), \
         patch("nff.tools.toolchain.subprocess.run", return_value=proc) as mrun:
        result = toolchain.run_arduino_cli(["config", "get", "directories.user"])
    assert result.success
    assert result.stdout == "ok"
    assert mrun.call_args[0][0] == ["/bin/arduino-cli", "config", "get", "directories.user"]


def test_run_arduino_cli_raises_without_cli():
    with patch("nff.tools.toolchain.find_arduino_cli", return_value=None):
        try:
            toolchain.run_arduino_cli(["version"])
            assert False, "expected ToolchainError"
        except ToolchainError:
            pass


def test_stream_arduino_cli_builds_command():
    with patch("nff.tools.toolchain.find_arduino_cli", return_value="/bin/arduino-cli"):
        stream = toolchain.stream_arduino_cli(["lib", "install", "PubSubClient"])
    assert stream._cmd == ["/bin/arduino-cli", "lib", "install", "PubSubClient"]


# ---------------------------------------------------------------------------
# installer.install_esp32_core
# ---------------------------------------------------------------------------

def test_install_esp32_core_success_passes_additional_urls():
    calls = []

    def fake_stream(args):
        calls.append(args)
        return _FakeStream(["downloading…"], returncode=0)

    with patch("nff.tools.toolchain.stream_arduino_cli", side_effect=fake_stream):
        ok = installer.install_esp32_core(emit=lambda _l: None)

    assert ok is True
    # both update-index and install carry --additional-urls with the esp32 index
    assert calls[0][:2] == ["core", "update-index"]
    assert calls[1][:3] == ["core", "install", "esp32:esp32"]
    assert installer._ESP32_BOARD_INDEX_URL in calls[1]


def test_install_esp32_core_short_circuits_on_failure():
    calls = []

    def fake_stream(args):
        calls.append(args)
        return _FakeStream(["err"], returncode=1)

    with patch("nff.tools.toolchain.stream_arduino_cli", side_effect=fake_stream):
        ok = installer.install_esp32_core(emit=lambda _l: None)

    assert ok is False
    assert len(calls) == 1  # stopped after update-index failed


def test_install_esp32_core_handles_missing_cli():
    with patch("nff.tools.toolchain.stream_arduino_cli", side_effect=ToolchainError("no cli")):
        ok = installer.install_esp32_core(emit=lambda _l: None)
    assert ok is False


# ---------------------------------------------------------------------------
# installer.install_arduino_library
# ---------------------------------------------------------------------------

def test_install_arduino_library_success():
    with patch("nff.tools.toolchain.stream_arduino_cli",
               return_value=_FakeStream(["installed"], returncode=0)):
        assert installer.install_arduino_library("PubSubClient", emit=lambda _l: None) is True


def test_install_arduino_library_failure():
    with patch("nff.tools.toolchain.stream_arduino_cli",
               return_value=_FakeStream(["nope"], returncode=2)):
        assert installer.install_arduino_library("PubSubClient", emit=lambda _l: None) is False


# ---------------------------------------------------------------------------
# installer.ensure_onboarding_toolchain (orchestrator)
# ---------------------------------------------------------------------------

def test_ensure_onboarding_toolchain_happy_path():
    with patch("nff.tools.toolchain.find_arduino_cli", return_value="/bin/arduino-cli"), \
         patch("nff.tools.installer.install_esp32_core", return_value=True), \
         patch("nff.tools.installer.install_arduino_library", return_value=True), \
         patch("nff.tools.arduino_lib.install_nff_library", return_value="/lib/nff") as mlib:
        ok, msg = installer.ensure_onboarding_toolchain(emit=lambda _l: None)
    assert ok is True
    mlib.assert_called_once()


def test_ensure_onboarding_toolchain_installs_cli_when_missing():
    with patch("nff.tools.toolchain.find_arduino_cli", return_value=None), \
         patch("nff.tools.installer.install") as minstall, \
         patch("nff.tools.installer.install_esp32_core", return_value=True), \
         patch("nff.tools.installer.install_arduino_library", return_value=True), \
         patch("nff.tools.arduino_lib.install_nff_library", return_value="/lib/nff"):
        ok, _msg = installer.ensure_onboarding_toolchain(emit=lambda _l: None)
    assert ok is True
    minstall.assert_called_once()


def test_ensure_onboarding_toolchain_aborts_on_core_failure():
    with patch("nff.tools.toolchain.find_arduino_cli", return_value="/bin/arduino-cli"), \
         patch("nff.tools.installer.install_esp32_core", return_value=False), \
         patch("nff.tools.installer.install_arduino_library") as mlib:
        ok, msg = installer.ensure_onboarding_toolchain(emit=lambda _l: None)
    assert ok is False
    assert "esp32 core" in msg
    mlib.assert_not_called()  # short-circuited


def test_ensure_onboarding_toolchain_reports_nff_lib_failure():
    from nff.tools.arduino_lib import ArduinoLibError
    with patch("nff.tools.toolchain.find_arduino_cli", return_value="/bin/arduino-cli"), \
         patch("nff.tools.installer.install_esp32_core", return_value=True), \
         patch("nff.tools.installer.install_arduino_library", return_value=True), \
         patch("nff.tools.arduino_lib.install_nff_library",
               side_effect=ArduinoLibError("download failed")):
        ok, msg = installer.ensure_onboarding_toolchain(emit=lambda _l: None)
    assert ok is False
    assert "download failed" in msg
