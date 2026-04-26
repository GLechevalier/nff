"""Download and install wokwi-cli on Windows, macOS, or Linux without admin rights."""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import urllib.request
from pathlib import Path

_GITHUB_API = "https://api.github.com/repos/wokwi/wokwi-cli/releases/latest"


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _asset_name() -> str:
    """Return the release asset filename for the current platform/arch."""
    system = platform.system()
    machine = platform.machine().lower()
    is_arm = machine in ("arm64", "aarch64")

    if system == "Windows":
        return "wokwi-cli-win-x64.exe"

    if system == "Darwin":
        return "wokwi-cli-macos-arm64" if is_arm else "wokwi-cli-macos-x64"

    if system == "Linux":
        return "wokwi-cli-linuxstatic-arm64" if is_arm else "wokwi-cli-linuxstatic-x64"

    raise RuntimeError(f"Unsupported platform: {system}")


def _install_dir() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Programs" / "wokwi-cli"
    return Path.home() / ".local" / "bin"


def _exe_name() -> str:
    return "wokwi-cli.exe" if platform.system() == "Windows" else "wokwi-cli"


# ---------------------------------------------------------------------------
# GitHub release lookup
# ---------------------------------------------------------------------------

def _get_download_url() -> tuple[str, str]:
    """Return (download_url, tag_name) for the latest wokwi-cli release."""
    req = urllib.request.Request(
        _GITHUB_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "nff-installer"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    tag = data["tag_name"]
    wanted = _asset_name()
    for asset in data["assets"]:
        if asset["name"] == wanted:
            return asset["browser_download_url"], tag

    raise RuntimeError(
        f"Asset '{wanted}' not found in release {tag}. "
        f"Available: {[a['name'] for a in data['assets']]}"
    )


# ---------------------------------------------------------------------------
# Download + install
# ---------------------------------------------------------------------------

def _show_progress(block: int, block_size: int, total: int) -> None:
    if total <= 0:
        return
    pct = min(100, block * block_size * 100 // total)
    bar = "#" * (pct // 5)
    print(f"\r  [{bar:<20}] {pct:3d}%", end="", flush=True)


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
    """Download and install wokwi-cli. Returns the binary path."""
    install_dir = _install_dir()
    exe_path = install_dir / _exe_name()

    if exe_path.exists() and not force:
        print(f"  wokwi-cli already installed at {exe_path}")
        return exe_path

    print(f"  Platform  : {platform.system()} {platform.machine()}")
    print("  Fetching latest release info…")
    url, tag = _get_download_url()
    print(f"  Release   : {tag}")
    print(f"  Download  : {url}")
    print(f"  Install   : {install_dir}")
    print()

    install_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_bin = Path(tmp) / _exe_name()
        print("  Downloading…")
        urllib.request.urlretrieve(url, tmp_bin, reporthook=_show_progress)
        print()

        if platform.system() != "Windows":
            tmp_bin.chmod(
                tmp_bin.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )

        shutil.copy2(tmp_bin, exe_path)

    _ensure_on_path(install_dir)
    return exe_path


def verify(exe_path: Path) -> bool:
    """Run wokwi-cli --version and return True on success."""
    try:
        result = subprocess.run(
            [str(exe_path), "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"\n  ✓ {result.stdout.strip()}")
            return True
    except Exception:
        pass
    return False
