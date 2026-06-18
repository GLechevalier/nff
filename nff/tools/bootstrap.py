"""Prepare the bootstrap sketch for onboarding and watch the device claim.

`nff init` provisions a credentials.h and detects the host WiFi, then calls
``prepare_bootstrap_sketch`` to produce a ready-to-compile sketch directory with the
WiFi/broker values templated in (templating, not -D, because WiFi passwords routinely
contain characters arduino-cli's --build-property tokenizer mangles).
"""

import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Generator, Optional

from nff.tools import serial as serial_tools

# Packaged bootstrap sketch (.ino + build_opt.h). Shipped as package data because the
# nff-sdk-c repo is not part of the pip wheel.
ASSET_DIR = Path(__file__).resolve().parent.parent / "assets" / "arduino_bootstrap"

# Serial markers the bootstrap firmware prints (nff_claim.c / the sketch).
_CLAIMED_MARKER = "CLAIMED mode"
_BOOTSTRAP_MARKER = "BOOTSTRAP mode"


class BootstrapError(Exception):
    pass


def _c_escape(value: str) -> str:
    """Escape a Python string for a C string literal body."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _template_defines(ino_text: str, values: dict[str, str]) -> str:
    """Rewrite `#define NAME "..."` lines for each NAME in values (C-escaped)."""
    out = []
    pattern = re.compile(r"^(\s*#define\s+(\w+)\s+).*$")
    for line in ino_text.splitlines():
        m = pattern.match(line)
        if m and m.group(2) in values:
            out.append(f'{m.group(1)}"{_c_escape(values[m.group(2)])}"')
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def prepare_bootstrap_sketch(
    credentials_h: str,
    ssid: str,
    password: str,
    broker_host: str,
    dest_dir: Optional[Path] = None,
) -> Path:
    """Copy the bundled bootstrap sketch to a temp dir, write credentials.h, and
    template WiFi/broker values into the .ino. Returns the sketch directory."""
    if not ASSET_DIR.exists():
        raise BootstrapError(f"bundled bootstrap sketch missing at {ASSET_DIR}")

    if dest_dir is None:
        dest_dir = Path(tempfile.mkdtemp(prefix="nff_onboard_")) / "arduino_bootstrap"
    dest_dir = Path(dest_dir)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(ASSET_DIR, dest_dir)

    (dest_dir / "credentials.h").write_text(credentials_h, encoding="utf-8")

    ino = dest_dir / "arduino_bootstrap.ino"
    templated = _template_defines(
        ino.read_text(encoding="utf-8"),
        {"WIFI_SSID": ssid, "WIFI_PASS": password, "HOST_IP": broker_host},
    )
    ino.write_text(templated, encoding="utf-8")
    return dest_dir


def watch_for_claim(
    port: str, baud: int = 115200, timeout_s: float = 150.0
) -> Generator[tuple[str, Optional[bool]], None, None]:
    """Stream serial lines while the device boots and claims.

    Yields (line, result) for each line: result is None until a terminal state, then
    True when "CLAIMED mode" is seen (success). The device reboots once after rollover,
    which keeps the same serial port, so we read straight through. On timeout the
    generator simply stops without yielding a True — the caller treats that as unknown.
    """
    deadline = time.monotonic() + timeout_s
    try:
        for line in serial_tools.stream_lines(port, baud, timeout_s=timeout_s):
            if _CLAIMED_MARKER in line:
                yield line, True
                return
            yield line, None
            if time.monotonic() >= deadline:
                return
    except Exception as exc:  # serial dropped mid-reboot, port busy, etc.
        raise BootstrapError(str(exc))
