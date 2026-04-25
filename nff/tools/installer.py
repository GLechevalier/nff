"""Download and install arduino-cli on Windows, macOS, or Linux without admin rights."""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

_BASE = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest"


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _asset() -> tuple[str, str]:
    """Return (download URL, ext) for the current platform/arch."""
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Windows":
        arch = "64bit" if machine in ("amd64", "x86_64") else "32bit"
        return f"{_BASE}_Windows_{arch}.zip", "zip"

    if system == "Darwin":
        arch = "ARM64" if machine in ("arm64", "aarch64") else "64bit"
        return f"{_BASE}_macOS_{arch}.tar.gz", "tar.gz"

    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            arch = "64bit"
        elif machine in ("aarch64", "arm64"):
            arch = "ARM64"
        elif machine.startswith("armv7"):
            arch = "ARMv7"
        else:
            arch = "64bit"
        return f"{_BASE}_Linux_{arch}.tar.gz", "tar.gz"

    raise RuntimeError(f"Unsupported platform: {system}")


def _install_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Programs" / "arduino-cli"
    return Path.home() / ".local" / "bin"


def _exe_name() -> str:
    return "arduino-cli.exe" if platform.system() == "Windows" else "arduino-cli"


# ---------------------------------------------------------------------------
# Download + extract
# ---------------------------------------------------------------------------

def _show_progress(block: int, block_size: int, total: int) -> None:
    if total <= 0:
        return
    pct = min(100, block * block_size * 100 // total)
    bar = "#" * (pct // 5)
    print(f"\r  [{bar:<20}] {pct:3d}%", end="", flush=True)


def _extract_binary(archive: Path, ext: str, dest_dir: Path) -> Path:
    exe = _exe_name()
    dest = dest_dir / exe

    if ext == "zip":
        with zipfile.ZipFile(archive) as zf:
            match = next((n for n in zf.namelist() if n.endswith(exe)), None)
            if match is None:
                raise FileNotFoundError(f"Could not find {exe} in zip archive")
            with zf.open(match) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    else:
        with tarfile.open(archive) as tf:
            members = tf.getmembers()
            match = next(
                (m for m in members if m.name.endswith("arduino-cli") and m.isfile()),
                None,
            )
            if match is None:
                raise FileNotFoundError("Could not find arduino-cli in tar archive")
            reader = tf.extractfile(match)
            if reader is None:
                raise FileNotFoundError("Could not read arduino-cli from tar archive")
            with open(dest, "wb") as out:
                shutil.copyfileobj(reader, out)

    if platform.system() != "Windows":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return dest


# ---------------------------------------------------------------------------
# PATH management
# ---------------------------------------------------------------------------

def _ensure_on_path(directory: Path) -> None:
    dir_str = str(directory)

    if platform.system() == "Windows":
        result = subprocess.run(
            ["powershell", "-Command",
             '[Environment]::GetEnvironmentVariable("PATH","User")'],
            capture_output=True, text=True,
        )
        current = result.stdout.strip()
        if dir_str.lower() not in current.lower():
            new_path = f"{current};{dir_str}" if current else dir_str
            subprocess.run(
                ["powershell", "-Command",
                 f'[Environment]::SetEnvironmentVariable("PATH","{new_path}","User")'],
                check=True,
            )
            print(f"  Added {dir_str} to user PATH")
        else:
            print(f"  {dir_str} already in user PATH")
        os.environ["PATH"] = os.environ.get("PATH", "") + f";{dir_str}"
        return

    export_line = f'\nexport PATH="$PATH:{dir_str}"'
    candidates = [
        Path.home() / ".bashrc",
        Path.home() / ".zshrc",
        Path.home() / ".profile",
    ]
    for cfg in candidates:
        if cfg.exists():
            if dir_str not in cfg.read_text():
                cfg.write_text(cfg.read_text() + export_line)
                print(f"  Added PATH entry to {cfg}")
                print("  Run: source ~/.bashrc  (or restart your terminal)")
            else:
                print(f"  {dir_str} already in {cfg}")
            os.environ["PATH"] = os.environ.get("PATH", "") + f":{dir_str}"
            return

    profile = Path.home() / ".profile"
    profile.write_text(export_line.lstrip())
    print(f"  Created {profile} with PATH export")
    print("  Run: source ~/.profile  (or restart your terminal)")
    os.environ["PATH"] = os.environ.get("PATH", "") + f":{dir_str}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install(force: bool = False) -> Path:
    """Download, extract, and install arduino-cli. Returns the binary path."""
    url, ext = _asset()
    install_dir = _install_dir()
    exe_path = install_dir / _exe_name()

    if exe_path.exists() and not force:
        print(f"  arduino-cli already installed at {exe_path}")
        return exe_path

    print(f"  Platform  : {platform.system()} {platform.machine()}")
    print(f"  Download  : {url}")
    print(f"  Install   : {install_dir}")
    print()

    install_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / f"arduino-cli.{'zip' if ext == 'zip' else 'tar.gz'}"
        print("  Downloading…")
        urllib.request.urlretrieve(url, archive, reporthook=_show_progress)
        print()
        print("  Extracting…", end=" ", flush=True)
        exe_path = _extract_binary(archive, ext, install_dir)
        print("done")

    _ensure_on_path(install_dir)
    return exe_path


def verify(exe_path: Path) -> bool:
    """Run arduino-cli version and return True on success."""
    try:
        result = subprocess.run(
            [str(exe_path), "version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"\n  ✓ {result.stdout.strip()}")
            return True
    except Exception:
        pass
    return False


def main() -> None:
    """CLI entry point: install arduino-cli (used by scripts/install_arduino_cli.py)."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Overwrite existing installation")
    args = parser.parse_args()

    print("=== arduino-cli installer ===\n")
    exe = install(force=args.force)
    ok = verify(exe)
    sys.exit(0 if ok else 1)
