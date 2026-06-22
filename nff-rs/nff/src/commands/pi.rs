//! `nff pi probe` — detect and prepare a directly-connected Raspberry Pi.
//!
//! Tells you whether a Pi is reachable and SSH-ready, and if not, exactly which
//! link in the chain is missing (cable/power → IP → SSH). Port of `commands/pi.py`.

use crate::cli::PiProbeArgs;
use crate::tools::pi as pi_tools;
use anyhow::Result;

fn emit_human(result: &pi_tools::ProbeResult) {
    println!("Interfaces:");
    if result.interfaces.is_empty() {
        println!("  (link status not available on this platform)");
    }
    for i in &result.interfaces {
        let icon = match i.status.as_str() {
            "Up" => "ok",
            "Disconnected" => "XX",
            _ => "??",
        };
        let ip = i.ipv4.as_deref().unwrap_or("no IPv4");
        let tag = if i.link_local {
            " [link-local - no DHCP]"
        } else {
            ""
        };
        println!("  [{icon}] {}: {} - {ip}{tag}", i.name, i.status);
    }

    println!("\nRaspberry Pi candidates:");
    if result.candidates.is_empty() {
        println!("  (none found)");
    }
    for c in &result.candidates {
        let icon = if c.ssh_open { "ok" } else { "XX" };
        let mut bits = vec![c.ip.clone()];
        if let Some(label) = &c.label {
            bits.push(label.clone());
        }
        if let Some(mac) = &c.mac {
            bits.push(mac.clone());
        }
        bits.push(format!("via {}", c.source));
        let ssh = if c.ssh_open {
            "SSH:22 open"
        } else {
            "SSH:22 closed"
        };
        println!("  [{icon}] {} - {ssh}", bits.join(" | "));
    }

    println!("\nVerdict:");
    let ready = result.ssh_ready();
    if let Some(first) = ready.first() {
        let ip = &first.ip;
        println!("  [ok] Pi reachable and SSH-ready at {ip}.");
        println!("       Next: ssh <user>@{ip}   (then nff-pentester setup can proceed)");
    } else if let Some(first) = result.candidates.first() {
        let ip = &first.ip;
        println!("  [!]  Pi found at {ip} but SSH (port 22) is not open.");
        println!(
            "       Enable SSH on the Pi (Raspberry Pi Imager -> SSH, or `sudo raspi-config`)"
        );
        println!("       and authorize your public key.");
    } else if !result.link_up() {
        println!("  [XX] No active network link to a Pi.");
        println!("       Check: Pi is powered and booted (~60s), Ethernet cable seated both ends,");
        println!(
            "       link LEDs lit. On a direct cable, enable Windows ICS so the Pi gets an IP."
        );
    } else {
        println!("  [XX] Link is up but no Pi detected (no Pi-OUI MAC, no mDNS, no SSH).");
        println!("       Try `nff pi probe --sweep`, or pass the IP: `nff pi probe --host <ip>`.");
    }
}

pub fn run_probe(args: &PiProbeArgs) -> Result<()> {
    let result = pi_tools::probe(args.host.as_deref(), args.sweep);

    if args.json {
        let payload = serde_json::json!({
            "link_up": result.link_up(),
            "interfaces": result.interfaces.iter().map(|i| serde_json::json!({
                "name": i.name, "status": i.status, "ipv4": i.ipv4, "link_local": i.link_local,
            })).collect::<Vec<_>>(),
            "candidates": result.candidates.iter().map(|c| serde_json::json!({
                "ip": c.ip, "mac": c.mac, "source": c.source, "label": c.label, "ssh_open": c.ssh_open,
            })).collect::<Vec<_>>(),
            "ssh_ready": result.ssh_ready().iter().map(|c| c.ip.clone()).collect::<Vec<_>>(),
        });
        println!("{}", serde_json::to_string_pretty(&payload)?);
    } else {
        emit_human(&result);
    }

    std::process::exit(if result.ssh_ready().is_empty() { 1 } else { 0 });
}
