"""Best-effort detection of a Raspberry Pi reachable from this host.

Backs `nff pi probe`. A Pi (unlike an ESP32) is a full Linux host reached over
the network, so detection leans on three independent signals:

  1. ARP table  — entries whose MAC matches a known Raspberry Pi OUI.
  2. mDNS       — resolving common Pi hostnames (raspberrypi.local, nff-pi.local…).
  3. SSH probe  — a TCP connect to port 22 on each candidate, since SSH is how
                  we actually drive the Pi.

Everything here is best-effort in the spirit of netinfo.py: any failure returns
an empty/falsey result, nothing raises. Works on Windows / Linux / macOS; link
status is richest on Windows (Get-NetAdapter) and Linux (/sys/class/net).
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SSH_PORT = 22

# Raspberry Pi MAC OUI prefixes (first 24 bits, lowercase, no separators) → label.
# Sources: IEEE registry assignments to the Raspberry Pi Foundation / Pi Ltd.
PI_OUIS: dict[str, str] = {
    "b827eb": "Raspberry Pi (1/2/3/Zero)",
    "dca632": "Raspberry Pi 4 / 400 / CM4",
    "e45f01": "Raspberry Pi 4 / CM4",
    "28cdc1": "Raspberry Pi (Pico W / newer)",
    "d83add": "Raspberry Pi 5",
    "2ccf67": "Raspberry Pi 5",
}

# Hostnames worth trying over mDNS. nff-pi is the hostname suggested by the setup flow.
PI_HOSTNAMES = ("nff-pi.local", "raspberrypi.local", "ubuntu.local", "nff-pi", "raspberrypi")

_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC_RE = re.compile(r"\b([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\b")


@dataclass
class Interface:
    name: str
    status: str  # "Up" | "Disconnected" | "unknown"
    ipv4: Optional[str] = None
    link_local: bool = False  # 169.254.x (no DHCP) — common on a direct cable


@dataclass
class PiCandidate:
    ip: str
    mac: Optional[str] = None
    source: str = "arp"  # arp | mdns | manual | sweep
    label: Optional[str] = None
    ssh_open: bool = False


@dataclass
class ProbeResult:
    interfaces: list[Interface] = field(default_factory=list)
    candidates: list[PiCandidate] = field(default_factory=list)

    @property
    def link_up(self) -> bool:
        return any(i.status == "Up" for i in self.interfaces)

    @property
    def ssh_ready(self) -> list[PiCandidate]:
        return [c for c in self.candidates if c.ssh_open]


def _run(cmd: list[str], timeout: int = 8) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout or ""
    except Exception:
        return ""


def _norm_mac(mac: str) -> str:
    """Lowercase, separator-stripped MAC (e.g. 'B8-27-EB-x' -> 'b827eb...')."""
    return re.sub(r"[^0-9a-fA-F]", "", mac).lower()


def _pi_label(mac: str) -> Optional[str]:
    return PI_OUIS.get(_norm_mac(mac)[:6])


# ---- ARP table -----------------------------------------------------------


def arp_entries() -> list[tuple[str, str]]:
    """Return (ip, normalized_mac) pairs from the OS ARP/neighbor table."""
    if sys.platform == "win32":
        out = _run(["arp", "-a"])
    elif sys.platform == "darwin":
        out = _run(["arp", "-a"])
    else:  # linux
        out = _run(["ip", "neigh"]) or _run(["arp", "-a"])

    pairs: list[tuple[str, str]] = []
    for line in out.splitlines():
        ip_m = _IP_RE.search(line)
        mac_m = _MAC_RE.search(line)
        if ip_m and mac_m:
            pairs.append((ip_m.group(1), _norm_mac(mac_m.group(1))))
    return pairs


def pi_candidates_from_arp() -> list[PiCandidate]:
    seen: set[str] = set()
    out: list[PiCandidate] = []
    for ip, mac in arp_entries():
        label = _pi_label(mac)
        if label and ip not in seen:
            seen.add(ip)
            out.append(PiCandidate(ip=ip, mac=mac, source="arp", label=label))
    return out


# ---- mDNS / hostname resolution -----------------------------------------


def resolve_hostnames(names: tuple[str, ...] = PI_HOSTNAMES) -> list[PiCandidate]:
    out: list[PiCandidate] = []
    seen: set[str] = set()
    for name in names:
        try:
            infos = socket.getaddrinfo(name, SSH_PORT, socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            continue
        for info in infos:
            ip = info[4][0]
            if ip not in seen:
                seen.add(ip)
                out.append(PiCandidate(ip=ip, source="mdns", label=name))
    return out


# ---- SSH reachability ----------------------------------------------------


def tcp_open(ip: str, port: int = SSH_PORT, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---- Local interfaces (for link / cable diagnosis) -----------------------


def _interfaces_windows() -> list[Interface]:
    adapters_raw = _run([
        "powershell", "-NoProfile", "-Command",
        "Get-NetAdapter | Select-Object Name,Status | ConvertTo-Json -Compress",
    ])
    addrs_raw = _run([
        "powershell", "-NoProfile", "-Command",
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Select-Object InterfaceAlias,IPAddress | ConvertTo-Json -Compress",
    ])

    def _as_list(raw: str) -> list[dict]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
        return data if isinstance(data, list) else [data]

    addr_by_name: dict[str, str] = {}
    for a in _as_list(addrs_raw):
        alias, ip = a.get("InterfaceAlias"), a.get("IPAddress")
        if alias and ip and not ip.startswith("127."):
            addr_by_name.setdefault(alias, ip)

    out: list[Interface] = []
    for a in _as_list(adapters_raw):
        name = a.get("Name")
        if not name:
            continue
        ip = addr_by_name.get(name)
        out.append(Interface(
            name=name,
            status=a.get("Status") or "unknown",
            ipv4=ip,
            link_local=bool(ip and ip.startswith("169.254.")),
        ))
    return out


def _interfaces_linux() -> list[Interface]:
    out: list[Interface] = []
    net = Path("/sys/class/net")
    if not net.is_dir():
        return out
    addr_lines = _run(["ip", "-o", "-4", "addr", "show"]).splitlines()
    addr_by_name: dict[str, str] = {}
    for line in addr_lines:
        parts = line.split()
        # "2: eth0 inet 192.168.1.5/24 ..."
        if len(parts) >= 4 and parts[2] == "inet":
            name = parts[1]
            ip = parts[3].split("/")[0]
            if not ip.startswith("127."):
                addr_by_name.setdefault(name, ip)
    for iface in sorted(net.iterdir()):
        name = iface.name
        if name == "lo":
            continue
        try:
            state = (iface / "operstate").read_text().strip()
        except OSError:
            state = "unknown"
        status = "Up" if state == "up" else ("Disconnected" if state == "down" else state)
        ip = addr_by_name.get(name)
        out.append(Interface(
            name=name, status=status, ipv4=ip,
            link_local=bool(ip and ip.startswith("169.254.")),
        ))
    return out


def list_interfaces() -> list[Interface]:
    try:
        if sys.platform == "win32":
            return _interfaces_windows()
        if sys.platform.startswith("linux"):
            return _interfaces_linux()
    except Exception:
        return []
    return []  # macOS / other: link status not enumerated (best-effort)


# ---- Optional /24 SSH sweep ---------------------------------------------


def _sweep_subnets(interfaces: list[Interface]) -> list[str]:
    """Sweepable /24 prefixes — direct-link ranges only, never the whole LAN."""
    prefixes: list[str] = []
    for i in interfaces:
        if not i.ipv4:
            continue
        # ICS hands out 192.168.137.x; link-local is /16 (too big to sweep).
        if i.ipv4.startswith("192.168.137."):
            prefixes.append(i.ipv4.rsplit(".", 1)[0])
    return list(dict.fromkeys(prefixes))


def ssh_sweep(prefixes: list[str], timeout: float = 0.4) -> list[PiCandidate]:
    targets = [f"{p}.{h}" for p in prefixes for h in range(1, 255)]
    found: list[PiCandidate] = []
    if not targets:
        return found
    with ThreadPoolExecutor(max_workers=64) as pool:
        for ip, ok in zip(targets, pool.map(lambda t: tcp_open(t, SSH_PORT, timeout), targets)):
            if ok:
                found.append(PiCandidate(ip=ip, source="sweep", ssh_open=True))
    return found


# ---- Top-level probe -----------------------------------------------------


def probe(host: Optional[str] = None, sweep: bool = False) -> ProbeResult:
    """Run all detection signals and return a merged, SSH-checked result."""
    interfaces = list_interfaces()

    by_ip: dict[str, PiCandidate] = {}

    def _merge(cands: list[PiCandidate]) -> None:
        for c in cands:
            existing = by_ip.get(c.ip)
            if existing is None:
                by_ip[c.ip] = c
            else:
                existing.mac = existing.mac or c.mac
                existing.label = existing.label or c.label

    if host:
        by_ip[host] = PiCandidate(ip=host, source="manual")
    _merge(pi_candidates_from_arp())
    _merge(resolve_hostnames())
    if sweep:
        _merge(ssh_sweep(_sweep_subnets(interfaces)))

    candidates = list(by_ip.values())
    # SSH-check each candidate concurrently.
    if candidates:
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = pool.map(lambda c: tcp_open(c.ip), candidates)
            for c, ok in zip(candidates, results):
                c.ssh_open = c.ssh_open or ok

    # Pi-OUI / SSH-ready first, then mDNS, then bare.
    candidates.sort(key=lambda c: (not c.ssh_open, c.label is None, c.source))
    return ProbeResult(interfaces=interfaces, candidates=candidates)
