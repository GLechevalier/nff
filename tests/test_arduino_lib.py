"""Tests for nff.tools.arduino_lib — GitHub fetch + flatten of the nff SDK."""

import io
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nff.tools import arduino_lib
from nff.tools.arduino_lib import ArduinoLibError
from nff.tools.toolchain import RunResult


# ---------------------------------------------------------------------------
# Helpers — build a synthetic nff-sdk-c checkout
# ---------------------------------------------------------------------------

def _make_sdk_tree(root: Path) -> Path:
    """Create a minimal nff-sdk-c repo layout under root and return it."""
    (root / "include").mkdir(parents=True)
    (root / "src" / "port").mkdir(parents=True)
    (root / "include" / "nff.h").write_text("// nff.h\n", encoding="utf-8")
    (root / "include" / "nff_port.h").write_text("// nff_port.h\n", encoding="utf-8")
    (root / "src" / "nff_core.c").write_text("// core\n", encoding="utf-8")
    (root / "src" / "nff_internal.h").write_text("// internal\n", encoding="utf-8")
    (root / "src" / "port" / "nff_port_esp32_arduino.c").write_text("// esp32\n", encoding="utf-8")
    (root / "src" / "port" / "nff_port_esp8266_arduino.c").write_text("// 8266\n", encoding="utf-8")
    (root / "src" / "port" / "nff_port_posix.c").write_text("// posix\n", encoding="utf-8")
    (root / "library.properties").write_text("name=nff\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# flatten_sdk
# ---------------------------------------------------------------------------

def test_flatten_sdk_produces_flat_esp32_library(tmp_path):
    repo = _make_sdk_tree(tmp_path / "repo")
    dest = tmp_path / "libraries" / "nff"

    arduino_lib.flatten_sdk(repo, dest)

    # Header duplicated to lib root (for <nff.h>) and src/ (recursive layout).
    assert (dest / "nff.h").exists()
    assert (dest / "src" / "nff.h").exists()
    assert (dest / "src" / "nff_port.h").exists()
    # Platform-agnostic sources + internal headers land in src/.
    assert (dest / "src" / "nff_core.c").exists()
    assert (dest / "src" / "nff_internal.h").exists()
    # ESP32 port renamed .c -> .cpp.
    assert (dest / "src" / "nff_port_esp32_arduino.cpp").exists()
    assert not (dest / "src" / "nff_port_esp32_arduino.c").exists()
    # Manifest at root.
    assert (dest / "library.properties").exists()


def test_flatten_sdk_excludes_non_esp32_ports(tmp_path):
    repo = _make_sdk_tree(tmp_path / "repo")
    dest = tmp_path / "lib"

    arduino_lib.flatten_sdk(repo, dest)

    names = {p.name for p in (dest / "src").iterdir()}
    assert "nff_port_esp8266_arduino.c" not in names
    assert "nff_port_posix.c" not in names
    assert "nff_port_esp32_idf.c" not in names


def test_flatten_sdk_wipes_stale_src(tmp_path):
    repo = _make_sdk_tree(tmp_path / "repo")
    dest = tmp_path / "lib"
    (dest / "src").mkdir(parents=True)
    stale = dest / "src" / "stale_old.c"
    stale.write_text("// stale\n", encoding="utf-8")

    arduino_lib.flatten_sdk(repo, dest)

    assert not stale.exists()


def test_flatten_sdk_raises_on_missing_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(ArduinoLibError, match="missing expected files"):
        arduino_lib.flatten_sdk(repo, tmp_path / "lib")


# ---------------------------------------------------------------------------
# resolve_lib_dir
# ---------------------------------------------------------------------------

def test_resolve_lib_dir_uses_arduino_cli_user_dir():
    rr = RunResult(success=True, stdout="/home/u/Arduino\n", stderr="", returncode=0)
    with patch("nff.tools.arduino_lib.toolchain.run_arduino_cli", return_value=rr):
        result = arduino_lib.resolve_lib_dir()
    assert result == Path("/home/u/Arduino") / "libraries" / "nff"


def test_resolve_lib_dir_falls_back_when_cli_missing():
    from nff.tools.toolchain import ToolchainError
    with patch("nff.tools.arduino_lib.toolchain.run_arduino_cli", side_effect=ToolchainError("no cli")):
        result = arduino_lib.resolve_lib_dir()
    assert result == Path.home() / "Documents" / "Arduino" / "libraries" / "nff"


def test_resolve_lib_dir_falls_back_on_empty_output():
    rr = RunResult(success=True, stdout="   \n", stderr="", returncode=0)
    with patch("nff.tools.arduino_lib.toolchain.run_arduino_cli", return_value=rr):
        result = arduino_lib.resolve_lib_dir()
    assert result == Path.home() / "Documents" / "Arduino" / "libraries" / "nff"


# ---------------------------------------------------------------------------
# install_nff_library (download + extract + flatten, all mocked)
# ---------------------------------------------------------------------------

def _make_github_tarball(tmp_path: Path) -> bytes:
    """Build a GitHub-style tarball (single top-level dir) of a synthetic SDK."""
    repo = _make_sdk_tree(tmp_path / "nff-sdk-c-main")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(repo, arcname="nff-sdk-c-main")
    return buf.getvalue()


def test_install_nff_library_end_to_end(tmp_path):
    tarball = _make_github_tarball(tmp_path)
    dest = tmp_path / "out" / "libraries" / "nff"

    mock_resp = MagicMock()
    mock_resp.content = tarball
    mock_resp.raise_for_status = MagicMock()

    with patch("nff.tools.arduino_lib.requests.get", return_value=mock_resp), \
         patch("nff.tools.arduino_lib.resolve_lib_dir", return_value=dest):
        result = arduino_lib.install_nff_library()

    assert result == dest
    assert (dest / "nff.h").exists()
    assert (dest / "src" / "nff_port_esp32_arduino.cpp").exists()
    assert (dest / ".nff_sync_meta").exists()


def test_install_nff_library_wraps_download_error():
    import requests
    with patch("nff.tools.arduino_lib.requests.get",
               side_effect=requests.RequestException("boom")):
        with pytest.raises(ArduinoLibError, match="could not download"):
            arduino_lib.install_nff_library()


def test_install_nff_library_respects_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NFF_SDK_C_URL", "https://example.test/custom.tar.gz")
    tarball = _make_github_tarball(tmp_path)
    mock_resp = MagicMock()
    mock_resp.content = tarball
    mock_resp.raise_for_status = MagicMock()

    with patch("nff.tools.arduino_lib.requests.get", return_value=mock_resp) as mget, \
         patch("nff.tools.arduino_lib.resolve_lib_dir", return_value=tmp_path / "nff"):
        arduino_lib.install_nff_library()

    mget.assert_called_once()
    assert mget.call_args[0][0] == "https://example.test/custom.tar.gz"
