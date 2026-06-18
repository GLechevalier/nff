"""Tests for nff.tools.pi / nff.commands.pi — Pi detection signals and CLI."""

from click.testing import CliRunner

from nff.commands.pi import pi
from nff.tools import pi as pi_tools


# ---------------------------------------------------------------------------
# MAC normalization + OUI matching
# ---------------------------------------------------------------------------

def test_norm_mac_strips_separators_and_lowercases():
    assert pi_tools._norm_mac("2C-CF-67-D4-F3-07") == "2ccf67d4f307"
    assert pi_tools._norm_mac("b8:27:eb:11:22:33") == "b827eb112233"


def test_pi_label_matches_known_oui():
    assert pi_tools._pi_label("2c:cf:67:d4:f3:07") == "Raspberry Pi 5"
    assert pi_tools._pi_label("B8-27-EB-00-00-00") == "Raspberry Pi (1/2/3/Zero)"


def test_pi_label_returns_none_for_non_pi_oui():
    assert pi_tools._pi_label("00:15:5d:72:aa:d1") is None  # Hyper-V vNIC


# ---------------------------------------------------------------------------
# ARP parsing → Pi candidates
# ---------------------------------------------------------------------------

_WINDOWS_ARP = """
Interface: 192.168.1.11 --- 0x14
  Internet Address      Physical Address      Type
  192.168.1.101         2c-cf-67-d4-f3-07     dynamic
  192.168.1.254         38-07-16-1e-f8-d9     dynamic
  224.0.0.251           01-00-5e-00-00-fb     static
"""


def test_arp_entries_parses_ip_mac_pairs(monkeypatch):
    monkeypatch.setattr(pi_tools, "_run", lambda *a, **k: _WINDOWS_ARP)
    entries = pi_tools.arp_entries()
    assert ("192.168.1.101", "2ccf67d4f307") in entries
    assert ("192.168.1.254", "3807161ef8d9") in entries


def test_pi_candidates_from_arp_keeps_only_pi_ouis(monkeypatch):
    monkeypatch.setattr(pi_tools, "_run", lambda *a, **k: _WINDOWS_ARP)
    cands = pi_tools.pi_candidates_from_arp()
    assert len(cands) == 1
    c = cands[0]
    assert c.ip == "192.168.1.101"
    assert c.label == "Raspberry Pi 5"
    assert c.source == "arp"


# ---------------------------------------------------------------------------
# probe() orchestration (no real network)
# ---------------------------------------------------------------------------

def test_probe_ssh_checks_candidates(monkeypatch):
    monkeypatch.setattr(pi_tools, "list_interfaces", lambda: [])
    monkeypatch.setattr(pi_tools, "pi_candidates_from_arp",
                        lambda: [pi_tools.PiCandidate(ip="10.0.0.5", label="Raspberry Pi 5")])
    monkeypatch.setattr(pi_tools, "resolve_hostnames", lambda: [])
    monkeypatch.setattr(pi_tools, "tcp_open", lambda ip, *a, **k: ip == "10.0.0.5")

    result = pi_tools.probe()
    assert len(result.candidates) == 1
    assert result.candidates[0].ssh_open
    assert result.ssh_ready and result.ssh_ready[0].ip == "10.0.0.5"


def test_probe_host_override_is_included(monkeypatch):
    monkeypatch.setattr(pi_tools, "list_interfaces", lambda: [])
    monkeypatch.setattr(pi_tools, "pi_candidates_from_arp", lambda: [])
    monkeypatch.setattr(pi_tools, "resolve_hostnames", lambda: [])
    monkeypatch.setattr(pi_tools, "tcp_open", lambda ip, *a, **k: False)

    result = pi_tools.probe(host="192.168.1.101")
    assert [c.ip for c in result.candidates] == ["192.168.1.101"]
    assert result.candidates[0].source == "manual"


# ---------------------------------------------------------------------------
# CLI exit codes
# ---------------------------------------------------------------------------

def test_probe_cli_exits_1_when_no_ssh_ready(monkeypatch):
    monkeypatch.setattr(pi_tools, "list_interfaces", lambda: [])
    monkeypatch.setattr(pi_tools, "pi_candidates_from_arp", lambda: [])
    monkeypatch.setattr(pi_tools, "resolve_hostnames", lambda: [])
    monkeypatch.setattr(pi_tools, "tcp_open", lambda *a, **k: False)

    result = CliRunner().invoke(pi, ["probe"])
    assert result.exit_code == 1


def test_probe_cli_exits_0_when_ssh_ready(monkeypatch):
    monkeypatch.setattr(pi_tools, "list_interfaces", lambda: [])
    monkeypatch.setattr(pi_tools, "pi_candidates_from_arp",
                        lambda: [pi_tools.PiCandidate(ip="10.0.0.5", label="Raspberry Pi 5")])
    monkeypatch.setattr(pi_tools, "resolve_hostnames", lambda: [])
    monkeypatch.setattr(pi_tools, "tcp_open", lambda *a, **k: True)

    result = CliRunner().invoke(pi, ["probe"])
    assert result.exit_code == 0
    assert "SSH-ready" in result.output
