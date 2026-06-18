"""nff pi — detect and prepare a directly-connected Raspberry Pi.

`nff pi probe` tells you whether a Pi is reachable and SSH-ready, and if not,
exactly which link in the chain is missing (cable/power → IP → SSH).
"""

import json as _json

import click

from nff.tools import pi as pi_tools


def _emit_human(result: pi_tools.ProbeResult) -> None:
    click.echo("Interfaces:")
    if not result.interfaces:
        click.echo("  (link status not available on this platform)")
    for i in result.interfaces:
        icon = "ok" if i.status == "Up" else ("XX" if i.status == "Disconnected" else "??")
        ip = i.ipv4 or "no IPv4"
        tag = " [link-local - no DHCP]" if i.link_local else ""
        click.echo(f"  [{icon}] {i.name}: {i.status} - {ip}{tag}")

    click.echo("\nRaspberry Pi candidates:")
    if not result.candidates:
        click.echo("  (none found)")
    for c in result.candidates:
        icon = "ok" if c.ssh_open else "XX"
        bits = [c.ip]
        if c.label:
            bits.append(c.label)
        if c.mac:
            bits.append(c.mac)
        bits.append(f"via {c.source}")
        ssh = "SSH:22 open" if c.ssh_open else "SSH:22 closed"
        click.echo(f"  [{icon}] {' | '.join(bits)} - {ssh}")

    click.echo("\nVerdict:")
    ready = result.ssh_ready
    if ready:
        ip = ready[0].ip
        click.echo(f"  [ok] Pi reachable and SSH-ready at {ip}.")
        click.echo(f"       Next: ssh <user>@{ip}   (then nff-pentester setup can proceed)")
    elif result.candidates:
        ip = result.candidates[0].ip
        click.echo(f"  [!]  Pi found at {ip} but SSH (port 22) is not open.")
        click.echo("       Enable SSH on the Pi (Raspberry Pi Imager -> SSH, or `sudo raspi-config`)")
        click.echo("       and authorize your public key.")
    elif not result.link_up:
        click.echo("  [XX] No active network link to a Pi.")
        click.echo("       Check: Pi is powered and booted (~60s), Ethernet cable seated both ends,")
        click.echo("       link LEDs lit. On a direct cable, enable Windows ICS so the Pi gets an IP.")
    else:
        click.echo("  [XX] Link is up but no Pi detected (no Pi-OUI MAC, no mDNS, no SSH).")
        click.echo("       Try `nff pi probe --sweep`, or pass the IP: `nff pi probe --host <ip>`.")


@click.group()
def pi():
    """Detect and prepare a directly-connected Raspberry Pi."""


@pi.command()
@click.option("--host", default=None, help="Probe a specific IP/hostname directly.")
@click.option("--sweep/--no-sweep", default=False,
              help="Also TCP/22-sweep direct-link /24 subnets (e.g. ICS 192.168.137.x).")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def probe(host, sweep, as_json):
    """Test whether a Raspberry Pi is connected and SSH-ready."""
    result = pi_tools.probe(host=host, sweep=sweep)

    if as_json:
        payload = {
            "link_up": result.link_up,
            "interfaces": [vars(i) for i in result.interfaces],
            "candidates": [vars(c) for c in result.candidates],
            "ssh_ready": [c.ip for c in result.ssh_ready],
        }
        click.echo(_json.dumps(payload, indent=2))
    else:
        _emit_human(result)

    raise SystemExit(0 if result.ssh_ready else 1)
