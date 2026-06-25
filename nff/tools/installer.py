"""Auto-install the arduino-cli binary."""

import io
import os
import platform
import stat
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

import requests

_ARDUINO_CLI_BASE = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest"


def _arduino_asset() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Windows":
        suffix = "_Windows_64bit.zip" if "64" in machine or "x86_64" in machine else "_Windows_32bit.zip"
        return f"{_ARDUINO_CLI_BASE}{suffix}", "zip"
    elif system == "Darwin":
        suffix = "_macOS_ARM64.tar.gz" if "arm" in machine or "aarch" in machine else "_macOS_64bit.tar.gz"
        return f"{_ARDUINO_CLI_BASE}{suffix}", "tar.gz"
    else:
        if "aarch64" in machine:
            suffix = "_Linux_ARM64.tar.gz"
        elif "arm" in machine:
            suffix = "_Linux_ARMv7.tar.gz"
        else:
            suffix = "_Linux_64bit.tar.gz"
        return f"{_ARDUINO_CLI_BASE}{suffix}", "tar.gz"


def _install_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", str(Path.home()))
        return Path(base) / "Programs" / "arduino-cli"
    return Path.home() / ".local" / "bin"


def _exe_name() -> str:
    return "arduino-cli.exe" if sys.platform == "win32" else "arduino-cli"


def _extract_binary(data: bytes, ext: str, dest_dir: Path) -> Path:
    exe = _exe_name()
    dest_dir.mkdir(parents=True, exist_ok=True)
    if ext == "zip":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if name.endswith(exe) or name == exe:
                    content = zf.read(name)
                    out = dest_dir / exe
                    out.write_bytes(content)
                    return out
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("arduino-cli") or member.name == "arduino-cli":
                    f = tf.extractfile(member)
                    if f:
                        out = dest_dir / exe
                        out.write_bytes(f.read())
                        if sys.platform != "win32":
                            out.chmod(out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
                        return out
    raise RuntimeError(f"Could not find {exe} in archive")


def _ensure_on_path(dir: Path) -> None:
    dir_str = str(dir)
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS)
            try:
                current, _ = winreg.QueryValueEx(key, "PATH")
            except FileNotFoundError:
                current = ""
            if dir_str not in current:
                new_path = current + ";" + dir_str if current else dir_str
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)
        except Exception:
            pass
    else:
        for rc in [Path.home() / ".bashrc", Path.home() / ".zshrc", Path.home() / ".profile"]:
            if rc.exists():
                line = f'\nexport PATH="$PATH:{dir_str}"\n'
                if dir_str not in rc.read_text(encoding="utf-8"):
                    rc.write_text(rc.read_text(encoding="utf-8") + line, encoding="utf-8")
                break
    current_path = os.environ.get("PATH", "")
    if dir_str not in current_path:
        os.environ["PATH"] = current_path + os.pathsep + dir_str


def install(force: bool = False) -> Path:
    exe = _install_dir() / _exe_name()
    if exe.exists() and not force:
        return exe
    url, ext = _arduino_asset()
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    binary = _extract_binary(resp.content, ext, _install_dir())
    _ensure_on_path(_install_dir())
    return binary


def verify(exe: Path) -> bool:
    import subprocess
    try:
        r = subprocess.run([str(exe), "version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ESP32 toolchain for `nff init` onboarding (core + libraries + nff lib)
# ---------------------------------------------------------------------------

# Espressif's Arduino board-manager index. Passed per-command via --additional-urls
# so installing the esp32 core never mutates the user's global arduino-cli config.
_ESP32_BOARD_INDEX_URL = (
    "https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json"
)


def install_esp32_core(emit=print) -> bool:
    """Install the esp32:esp32 Arduino core. Idempotent (arduino-cli no-ops if present)."""
    from nff.tools import toolchain
    extra = ["--additional-urls", _ESP32_BOARD_INDEX_URL]
    try:
        for args in (["core", "update-index", *extra], ["core", "install", "esp32:esp32", *extra]):
            stream = toolchain.stream_arduino_cli(args)
            for line in stream:
                emit(line)
            if stream.returncode != 0:
                return False
    except toolchain.ToolchainError as exc:
        emit(str(exc))
        return False
    return True


def install_arduino_library(name: str, emit=print) -> bool:
    """Install an Arduino library by name via `arduino-cli lib install`."""
    from nff.tools import toolchain
    try:
        stream = toolchain.stream_arduino_cli(["lib", "install", name])
        for line in stream:
            emit(line)
        return stream.returncode == 0
    except toolchain.ToolchainError as exc:
        emit(str(exc))
        return False


def ensure_onboarding_toolchain(emit=print) -> tuple[bool, str]:
    """Ensure everything the onboarding firmware needs to compile is installed:
    arduino-cli, the esp32 core, PubSubClient, and the nff Arduino library.

    Returns (ok, message). The first hard failure short-circuits with an
    actionable message; callers should abort the compile when ok is False.
    """
    from nff.tools import arduino_lib, toolchain

    if not toolchain.find_arduino_cli():
        emit("installing arduino-cli…")
        try:
            install()
        except Exception as exc:
            return False, f"could not install arduino-cli: {exc}"

    if not install_esp32_core(emit):
        return False, "esp32 core install failed"

    if not install_arduino_library("PubSubClient", emit):
        return False, "PubSubClient install failed"

    try:
        arduino_lib.install_nff_library(emit)
    except arduino_lib.ArduinoLibError as exc:
        return False, str(exc)

    return True, "toolchain ready"
