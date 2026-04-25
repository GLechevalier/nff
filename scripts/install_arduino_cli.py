#!/usr/bin/env python3
"""Install arduino-cli on Windows, macOS, or Linux without admin rights.

Usage:
    python scripts/install_arduino_cli.py
    python scripts/install_arduino_cli.py --force   # overwrite existing
"""

from __future__ import annotations

import argparse

# Windows PowerShell defaults to cp1252; reconfigure before any Unicode output.
import sys as _sys
if _sys.platform == "win32" and hasattr(_sys.stdout, "reconfigure"):
    _sys.stdout.reconfigure(encoding="utf-8")
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

# Base URL for official arduino-cli downloads.
_BASE = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest"


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _asset() -> tuple[str, str]:
    """Return (download URL, 'zip'|'tar.gz') for the current platform/arch."""
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
            arch = "64bit"  # best guess for unknown arch
        return f"{_BASE}_Linux_{arch}.tar.gz", "tar.gz"

    print(f"ERROR: unsupported platform '{system}'", file=sys.stderr)
    sys.exit(1)


def _install_dir() -> Path:
    """Return the install directory for this platform (no admin needed)."""
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
    """Pull the arduino-cli binary out of the archive into *dest_dir*."""
    exe = _exe_name()
    dest = dest_dir / exe

    if ext == "zip":
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            match = next((n for n in names if n.endswith(exe)), None)
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

    # Ensure executable bit on POSIX
    if platform.system() != "Windows":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return dest


# ---------------------------------------------------------------------------
# PATH management
# ---------------------------------------------------------------------------

def _ensure_on_path(directory: Path) -> None:
    """Add *directory* to the user's permanent PATH if not already present."""
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
        # Make available in the current process too
        os.environ["PATH"] = os.environ.get("PATH", "") + f";{dir_str}"
        return

    # POSIX — append to the first existing shell config we find
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

    # No existing config — create .profile
    profile = Path.home() / ".profile"
    profile.write_text(export_line.lstrip())
    print(f"  Created {profile} with PATH export")
    print("  Run: source ~/.profile  (or restart your terminal)")
    os.environ["PATH"] = os.environ.get("PATH", "") + f":{dir_str}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def install(force: bool = False) -> Path:
    """Download, extract, and install arduino-cli. Returns the binary path."""
    url, ext = _asset()
    install_dir = _install_dir()
    exe_path = install_dir / _exe_name()

    if exe_path.exists() and not force:
        print(f"  arduino-cli already installed at {exe_path}")
        print("  Pass --force to reinstall.")
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
        print()  # newline after progress bar

        print("  Extracting…", end=" ", flush=True)
        exe_path = _extract_binary(archive, ext, install_dir)
        print("done")

    _ensure_on_path(install_dir)
    return exe_path


def verify(exe_path: Path) -> bool:
    """Run arduino-cli version and print the result. Returns True on success."""
    try:
        result = subprocess.run(
            [str(exe_path), "version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"\n  ✓ {result.stdout.strip()}")
            return True
        print(f"\n  ✗ arduino-cli exited with code {result.returncode}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"\n  ✗ Could not run arduino-cli: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing installation")
    args = parser.parse_args()

    print("=== arduino-cli installer ===\n")
    exe = install(force=args.force)
    ok = verify(exe)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
