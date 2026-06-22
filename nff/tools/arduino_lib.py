"""Fetch the nff Arduino library from GitHub and install it for arduino-cli.

`nff init` onboarding compiles a sketch that does `#include <nff.h>`, so the nff
Arduino library must be present in arduino-cli's libraries directory. The library's
source of truth is the nff-sdk-c repo, which is NOT shipped in this pip wheel — so we
download it on demand and apply the same flatten transform as
``nff-sdk-c/tools/sync_arduino_lib.py``:

The repo uses a nested layout (include/ + src/ + src/port/) and supports four platforms
via mutually-exclusive #if-guarded port files. The Arduino IDE/CLI needs a *flat*
library: every file under src/ is compiled, and the ESP32 Arduino port carries C++ so it
must have a .cpp extension. ESP32 only — the esp8266 / esp32-idf / posix ports are
excluded so the Arduino build never tries to compile a non-Arduino port.
"""

from __future__ import annotations

import datetime
import io
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Callable, Optional

import requests

from nff.tools import toolchain

# Default branch tarball of the nff-sdk-c repo (the `url=` from library.properties).
# Override with NFF_SDK_C_URL to pin a tag/commit or point at a private mirror.
_NFF_SDK_TARBALL = "https://github.com/nff-io/nff-sdk-c/archive/refs/heads/main.tar.gz"

# The single ESP32 Arduino port (C++), renamed .c -> .cpp in the flat library.
_ARDUINO_PORT_SRC = "nff_port_esp32_arduino.c"
_ARDUINO_PORT_DST = "nff_port_esp32_arduino.cpp"

# Ports excluded from the ESP32-only Arduino library.
_EXCLUDED_PORTS = {
    "nff_port_esp8266_arduino.c",  # ESP8266 (BearSSL)
    "nff_port_esp32_idf.c",        # ESP-IDF native — not Arduino
    "nff_port_posix.c",            # host tests — not Arduino
}

Emit = Callable[[str], None]


class ArduinoLibError(Exception):
    pass


def _tarball_url() -> str:
    return os.environ.get("NFF_SDK_C_URL") or _NFF_SDK_TARBALL


def resolve_lib_dir() -> Path:
    """Where to install the library: <arduino user dir>/libraries/nff.

    Asks arduino-cli for its user (sketchbook) directory; falls back to the
    platform-default Arduino sketchbook location. Mirrors
    ``sync_arduino_lib.py:resolve_dest``.
    """
    try:
        result = toolchain.run_arduino_cli(["config", "get", "directories.user"], timeout=20)
        user_dir = result.stdout.strip()
        if result.success and user_dir:
            return Path(user_dir) / "libraries" / "nff"
    except Exception:
        pass
    return Path.home() / "Documents" / "Arduino" / "libraries" / "nff"


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def flatten_sdk(repo_root: Path, dest: Path) -> Path:
    """Transform a nff-sdk-c checkout into a flat ESP32 Arduino library at ``dest``.

    Port of ``sync_arduino_lib.py:main``. ``repo_root`` must contain include/nff.h,
    include/nff_port.h, src/port/nff_port_esp32_arduino.c, and library.properties.
    Returns ``dest``.
    """
    inc = repo_root / "include"
    src = repo_root / "src"
    port_src = src / "port" / _ARDUINO_PORT_SRC
    lib_props = repo_root / "library.properties"

    missing = [
        p for p in (inc / "nff.h", inc / "nff_port.h", port_src, lib_props) if not p.exists()
    ]
    if missing:
        raise ArduinoLibError(
            "downloaded SDK is missing expected files: "
            + ", ".join(str(p.relative_to(repo_root)) for p in missing)
        )

    dest_src = dest / "src"
    # Wipe src/ so renamed/removed files never linger as stale duplicates.
    if dest_src.exists():
        shutil.rmtree(dest_src)
    dest_src.mkdir(parents=True, exist_ok=True)

    # Header: duplicated to the lib root (for <nff.h>) and src/ (recursive layout).
    _copy(inc / "nff.h", dest / "nff.h")
    _copy(inc / "nff.h", dest_src / "nff.h")
    _copy(inc / "nff_port.h", dest_src / "nff_port.h")

    # Platform-agnostic sources + internal headers (everything in src/ except port/).
    for f in sorted(src.glob("*.c")):
        _copy(f, dest_src / f.name)
    for f in sorted(src.glob("*.h")):
        _copy(f, dest_src / f.name)

    # The single Arduino ESP32 port, renamed .c -> .cpp (it is C++).
    _copy(port_src, dest_src / _ARDUINO_PORT_DST)

    # Library manifest + a marker so we (and arduino-cli) can see what was synced.
    _copy(lib_props, dest / "library.properties")
    m = re.search(r"^version=(.+)$", lib_props.read_text(encoding="utf-8"), re.M)
    version = m.group(1).strip() if m else "unknown"
    synced_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (dest / ".nff_sync_meta").write_text(
        f"synced_from={_tarball_url()}\n"
        f"version={version}\n"
        f"synced_at={synced_at}\n"
        f"ports=esp32_arduino_only\n",
        encoding="utf-8",
    )
    return dest


def _extract_repo_root(data: bytes, into: Path) -> Path:
    """Extract a GitHub tarball into ``into`` and return the single top-level dir.

    GitHub archive tarballs wrap everything in one folder (e.g. nff-sdk-c-main/).
    """
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = tf.getmembers()
        tf.extractall(into)
    tops = {m.name.split("/", 1)[0] for m in members if m.name and not m.name.startswith("/")}
    if len(tops) != 1:
        raise ArduinoLibError(
            f"unexpected SDK archive layout: {len(tops)} top-level entries"
        )
    return into / next(iter(tops))


def install_nff_library(emit: Optional[Emit] = None) -> Path:
    """Download nff-sdk-c, flatten it, and install it into arduino-cli's libraries dir.

    Returns the installed library path. Raises ``ArduinoLibError`` on failure.
    """
    emit = emit or (lambda _l: None)
    url = _tarball_url()
    emit(f"fetching nff library from {url}")
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ArduinoLibError(f"could not download nff SDK: {exc}") from exc

    dest = resolve_lib_dir()
    with tempfile.TemporaryDirectory(prefix="nff_sdk_") as tmp:
        try:
            repo_root = _extract_repo_root(resp.content, Path(tmp))
        except (tarfile.TarError, OSError) as exc:
            raise ArduinoLibError(f"could not extract nff SDK: {exc}") from exc
        flatten_sdk(repo_root, dest)
    emit(f"installed nff library -> {dest}")
    return dest


# ---------------------------------------------------------------------------
# Staleness detection — warn when a local SDK source is newer than what's synced
# ---------------------------------------------------------------------------

_SDK_SRC_EXTS = {".c", ".h", ".cpp"}


def read_sync_meta() -> dict[str, str]:
    """Parse the installed library's ``.nff_sync_meta`` into a dict (empty if absent)."""
    meta = resolve_lib_dir() / ".nff_sync_meta"
    if not meta.exists():
        return {}
    fields: dict[str, str] = {}
    for line in meta.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            fields[k.strip()] = v.strip()
    return fields


def _detect_local_sdk_src() -> Optional[Path]:
    """A local nff-sdk-c source tree, if the developer has one checked out.

    Honours ``NFF_SDK_C_SRC`` first, then walks up from the cwd looking for a
    sibling ``nff-sdk-c/`` with the expected layout. Returns None for plain pip
    users (no local checkout), so the staleness warning never fires for them.
    """
    env = os.environ.get("NFF_SDK_C_SRC")
    if env and (Path(env) / "library.properties").exists():
        return Path(env)
    for base in [Path.cwd(), *Path.cwd().parents]:
        cand = base / "nff-sdk-c"
        if (cand / "library.properties").exists() and (cand / "src").is_dir():
            return cand
    return None


def local_sdk_newer_than_synced() -> Optional[str]:
    """Return a human-readable warning if a detected local nff-sdk-c source is
    newer than the installed Arduino library, else None. Never raises.

    This catches the footgun where a developer edits ``nff-sdk-c/src`` and then
    flashes the *stale* synced library, silently shipping old code.
    """
    try:
        src = _detect_local_sdk_src()
        if not src:
            return None
        meta = resolve_lib_dir() / ".nff_sync_meta"
        if not meta.exists():
            return None
        synced_mtime = meta.stat().st_mtime
        newest = max(
            (
                p.stat().st_mtime
                for p in src.rglob("*")
                if p.is_file() and p.suffix in _SDK_SRC_EXTS
            ),
            default=0.0,
        )
        if newest > synced_mtime:
            return (
                f"local nff-sdk-c at {src} has edits newer than the synced "
                f"Arduino library — run `python {src / 'tools' / 'sync_arduino_lib.py'}` "
                f"before flashing"
            )
    except Exception:
        return None
    return None
