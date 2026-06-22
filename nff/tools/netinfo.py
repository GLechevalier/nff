"""Best-effort host WiFi detection (SSID + password) for onboarding.

Used by `nff init` to pre-fill the WiFi credentials baked into bootstrap firmware so
the device joins the same network the computer is on. Everything here is best-effort:
any failure returns None and the wizard falls back to prompting. Nothing raises.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def _run(cmd: list[str], timeout: int = 6) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except Exception:
        return ""


# ---- Windows -------------------------------------------------------------
# Labels in `netsh` output are localized (e.g. French "Contenu de la clé"), so we
# never match on the password label. "SSID" is an acronym kept across locales, and
# matching the key exactly excludes "BSSID".


def _win_ssid() -> Optional[str]:
    out = _run(["netsh", "wlan", "show", "interfaces"])
    for line in out.splitlines():
        key, sep, val = line.partition(":")
        if sep and key.strip() == "SSID":
            return val.strip() or None
    return None


def _win_password(ssid: str) -> Optional[str]:
    # Export the saved profile to its XML form and read <keyMaterial> — locale-independent,
    # unlike scraping the translated "Key Content" line from `show profile`.
    with tempfile.TemporaryDirectory() as d:
        _run(["netsh", "wlan", "export", "profile", f"name={ssid}", "key=clear", f"folder={d}"])
        for xml in Path(d).glob("*.xml"):
            try:
                text = xml.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r"<keyMaterial>(.*?)</keyMaterial>", text, re.DOTALL)
            if m:
                return m.group(1).strip() or None
    return None


# ---- macOS ---------------------------------------------------------------

_AIRPORT = (
    "/System/Library/PrivateFrameworks/Apple80211.framework"
    "/Versions/Current/Resources/airport"
)


def _mac_ssid() -> Optional[str]:
    out = _run([_AIRPORT, "-I"])
    for line in out.splitlines():
        key, sep, val = line.partition(":")
        if sep and key.strip() == "SSID":
            return val.strip() or None
    out = _run(["networksetup", "-getairportnetwork", "en0"])
    if ":" in out:
        return out.split(":", 1)[1].strip() or None
    return None


def _mac_password(ssid: str) -> Optional[str]:
    # May surface a keychain authorization dialog; short timeout, failure → None.
    out = _run(["security", "find-generic-password", "-ga", ssid, "-w"], timeout=8)
    return out.strip() or None


# ---- Linux ---------------------------------------------------------------


def _linux_ssid() -> Optional[str]:
    out = _run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"])
    for line in out.splitlines():
        if line.startswith("yes:"):
            return line.split(":", 1)[1].strip() or None
    return _run(["iwgetid", "-r"]).strip() or None


def _linux_password(ssid: str) -> Optional[str]:
    out = _run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", ssid])
    return out.strip() or None


def detect_wifi() -> tuple[Optional[str], Optional[str]]:
    """Return (ssid, password); either may be None. Never raises."""
    try:
        if sys.platform == "win32":
            ssid = _win_ssid()
            return ssid, (_win_password(ssid) if ssid else None)
        if sys.platform == "darwin":
            ssid = _mac_ssid()
            return ssid, (_mac_password(ssid) if ssid else None)
        ssid = _linux_ssid()
        return ssid, (_linux_password(ssid) if ssid else None)
    except Exception:
        return None, None
