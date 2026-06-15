"""Auto-install arduino-cli and wokwi-cli binaries."""

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
_WOKWI_CLI_BASE = "https://github.com/wokwi/wokwi-cli/releases/latest/download"


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
