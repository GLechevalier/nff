//! Best-effort detection of a Raspberry Pi reachable from this host.
//!
//! Faithful port of the Python `nff/tools/pi.py`. A Pi is a full Linux host
//! reached over the network, so detection leans on three independent signals:
//! the ARP table (Pi-OUI MACs), mDNS hostname resolution, and a TCP/22 probe.
//! Everything is best-effort: any failure yields an empty result, nothing panics.

use std::collections::{BTreeMap, HashSet};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::Path;
use std::process::Command;
use std::sync::OnceLock;
use std::time::Duration;

use regex::Regex;

pub const SSH_PORT: u16 = 22;

// Hostnames worth trying over mDNS. nff-pi is the hostname the setup flow suggests.
const PI_HOSTNAMES: &[&str] = &[
    "nff-pi.local",
    "raspberrypi.local",
    "ubuntu.local",
    "nff-pi",
    "raspberrypi",
];

#[derive(Debug, Clone)]
pub struct Interface {
    pub name: String,
    pub status: String, // "Up" | "Disconnected" | "unknown"
    pub ipv4: Option<String>,
    pub link_local: bool, // 169.254.x (no DHCP) — common on a direct cable
}

#[derive(Debug, Clone)]
pub struct PiCandidate {
    pub ip: String,
    pub mac: Option<String>,
    pub source: String, // arp | mdns | manual | sweep
    pub label: Option<String>,
    pub ssh_open: bool,
}

pub struct ProbeResult {
    pub interfaces: Vec<Interface>,
    pub candidates: Vec<PiCandidate>,
}

impl ProbeResult {
    pub fn link_up(&self) -> bool {
        self.interfaces.iter().any(|i| i.status == "Up")
    }
    pub fn ssh_ready(&self) -> Vec<&PiCandidate> {
        self.candidates.iter().filter(|c| c.ssh_open).collect()
    }
}

/// Raspberry Pi MAC OUI prefix (first 24 bits, lowercase) → label.
fn pi_label(mac: &str) -> Option<&'static str> {
    let norm = norm_mac(mac);
    match norm.get(..6)? {
        "b827eb" => Some("Raspberry Pi (1/2/3/Zero)"),
        "dca632" => Some("Raspberry Pi 4 / 400 / CM4"),
        "e45f01" => Some("Raspberry Pi 4 / CM4"),
        "28cdc1" => Some("Raspberry Pi (Pico W / newer)"),
        "d83add" => Some("Raspberry Pi 5"),
        "2ccf67" => Some("Raspberry Pi 5"),
        _ => None,
    }
}

fn ip_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b").unwrap())
}

fn mac_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\b([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})\b").unwrap())
}

fn norm_mac(mac: &str) -> String {
    mac.chars()
        .filter(|c| c.is_ascii_hexdigit())
        .collect::<String>()
        .to_lowercase()
}

fn run_cmd(program: &str, args: &[&str]) -> String {
    Command::new(program)
        .args(args)
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).into_owned())
        .unwrap_or_default()
}

// ---- ARP table -----------------------------------------------------------

fn arp_entries() -> Vec<(String, String)> {
    let out = if cfg!(target_os = "linux") {
        let o = run_cmd("ip", &["neigh"]);
        if o.is_empty() {
            run_cmd("arp", &["-a"])
        } else {
            o
        }
    } else {
        run_cmd("arp", &["-a"])
    };

    let mut pairs = Vec::new();
    for line in out.lines() {
        if let (Some(ipm), Some(macm)) = (ip_regex().find(line), mac_regex().captures(line)) {
            let ip = ipm.as_str().to_string();
            let mac = norm_mac(macm.get(1).unwrap().as_str());
            pairs.push((ip, mac));
        }
    }
    pairs
}

fn pi_candidates_from_arp() -> Vec<PiCandidate> {
    let mut seen = HashSet::new();
    let mut out = Vec::new();
    for (ip, mac) in arp_entries() {
        if let Some(label) = pi_label(&mac) {
            if seen.insert(ip.clone()) {
                out.push(PiCandidate {
                    ip,
                    mac: Some(mac),
                    source: "arp".into(),
                    label: Some(label.to_string()),
                    ssh_open: false,
                });
            }
        }
    }
    out
}

// ---- mDNS / hostname resolution -----------------------------------------

fn resolve_hostnames() -> Vec<PiCandidate> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();
    for name in PI_HOSTNAMES {
        if let Ok(addrs) = (*name, SSH_PORT).to_socket_addrs() {
            for a in addrs {
                if a.is_ipv4() {
                    let ip = a.ip().to_string();
                    if seen.insert(ip.clone()) {
                        out.push(PiCandidate {
                            ip,
                            mac: None,
                            source: "mdns".into(),
                            label: Some((*name).to_string()),
                            ssh_open: false,
                        });
                    }
                }
            }
        }
    }
    out
}

// ---- SSH reachability ----------------------------------------------------

pub fn tcp_open(ip: &str, timeout: Duration) -> bool {
    let Ok(addrs) = format!("{ip}:{SSH_PORT}").to_socket_addrs() else {
        return false;
    };
    for addr in addrs {
        if TcpStream::connect_timeout(&addr, timeout).is_ok() {
            return true;
        }
    }
    false
}

fn ssh_check_all(cands: &mut [PiCandidate]) {
    if cands.is_empty() {
        return;
    }
    std::thread::scope(|s| {
        let handles: Vec<_> = cands
            .iter()
            .map(|c| {
                let ip = c.ip.clone();
                s.spawn(move || tcp_open(&ip, Duration::from_secs(1)))
            })
            .collect();
        for (c, h) in cands.iter_mut().zip(handles) {
            c.ssh_open = c.ssh_open || h.join().unwrap_or(false);
        }
    });
}

// ---- Local interfaces (for link / cable diagnosis) -----------------------

fn interfaces_windows() -> Vec<Interface> {
    let adapters_raw = run_cmd(
        "powershell",
        &[
            "-NoProfile",
            "-Command",
            "Get-NetAdapter | Select-Object Name,Status | ConvertTo-Json -Compress",
        ],
    );
    let addrs_raw = run_cmd(
        "powershell",
        &[
            "-NoProfile",
            "-Command",
            "Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress | ConvertTo-Json -Compress",
        ],
    );

    fn as_list(raw: &str) -> Vec<serde_json::Value> {
        match serde_json::from_str::<serde_json::Value>(raw) {
            Ok(serde_json::Value::Array(a)) => a,
            Ok(v) => vec![v],
            Err(_) => vec![],
        }
    }

    let mut addr_by_name: BTreeMap<String, String> = BTreeMap::new();
    for a in as_list(&addrs_raw) {
        let alias = a.get("InterfaceAlias").and_then(|v| v.as_str());
        let ip = a.get("IPAddress").and_then(|v| v.as_str());
        if let (Some(alias), Some(ip)) = (alias, ip) {
            if !ip.starts_with("127.") {
                addr_by_name
                    .entry(alias.to_string())
                    .or_insert_with(|| ip.to_string());
            }
        }
    }

    let mut out = Vec::new();
    for a in as_list(&adapters_raw) {
        let Some(name) = a.get("Name").and_then(|v| v.as_str()) else {
            continue;
        };
        let ip = addr_by_name.get(name).cloned();
        let link_local = ip
            .as_deref()
            .map(|i| i.starts_with("169.254."))
            .unwrap_or(false);
        out.push(Interface {
            name: name.to_string(),
            status: a
                .get("Status")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown")
                .to_string(),
            ipv4: ip,
            link_local,
        });
    }
    out
}

fn interfaces_linux() -> Vec<Interface> {
    let net = Path::new("/sys/class/net");
    if !net.is_dir() {
        return vec![];
    }
    let mut addr_by_name: BTreeMap<String, String> = BTreeMap::new();
    for line in run_cmd("ip", &["-o", "-4", "addr", "show"]).lines() {
        let parts: Vec<&str> = line.split_whitespace().collect();
        // "2: eth0 inet 192.168.1.5/24 ..."
        if parts.len() >= 4 && parts[2] == "inet" {
            let name = parts[1].to_string();
            let ip = parts[3].split('/').next().unwrap_or("").to_string();
            if !ip.starts_with("127.") {
                addr_by_name.entry(name).or_insert(ip);
            }
        }
    }
    let mut out = Vec::new();
    let Ok(entries) = std::fs::read_dir(net) else {
        return out;
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| n != "lo")
        .collect();
    names.sort();
    for name in names {
        let state = std::fs::read_to_string(net.join(&name).join("operstate"))
            .map(|s| s.trim().to_string())
            .unwrap_or_else(|_| "unknown".into());
        let status = match state.as_str() {
            "up" => "Up",
            "down" => "Disconnected",
            other => other,
        }
        .to_string();
        let ip = addr_by_name.get(&name).cloned();
        let link_local = ip
            .as_deref()
            .map(|i| i.starts_with("169.254."))
            .unwrap_or(false);
        out.push(Interface {
            name,
            status,
            ipv4: ip,
            link_local,
        });
    }
    out
}

pub fn list_interfaces() -> Vec<Interface> {
    if cfg!(windows) {
        interfaces_windows()
    } else if cfg!(target_os = "linux") {
        interfaces_linux()
    } else {
        vec![] // macOS / other: link status not enumerated (best-effort)
    }
}

// ---- Optional /24 SSH sweep ---------------------------------------------

fn sweep_subnets(interfaces: &[Interface]) -> Vec<String> {
    let mut prefixes = Vec::new();
    for i in interfaces {
        if let Some(ip) = &i.ipv4 {
            // ICS hands out 192.168.137.x; link-local /16 is too big to sweep.
            if ip.starts_with("192.168.137.") {
                if let Some((prefix, _)) = ip.rsplit_once('.') {
                    if !prefixes.contains(&prefix.to_string()) {
                        prefixes.push(prefix.to_string());
                    }
                }
            }
        }
    }
    prefixes
}

fn ssh_sweep(prefixes: &[String], timeout: Duration) -> Vec<PiCandidate> {
    let targets: Vec<String> = prefixes
        .iter()
        .flat_map(|p| (1..255).map(move |h| format!("{p}.{h}")))
        .collect();
    let mut found = Vec::new();
    if targets.is_empty() {
        return found;
    }
    std::thread::scope(|s| {
        let handles: Vec<_> = targets
            .iter()
            .map(|t| {
                let t = t.clone();
                s.spawn(move || (t.clone(), tcp_open(&t, timeout)))
            })
            .collect();
        for h in handles {
            if let Ok((ip, true)) = h.join() {
                found.push(PiCandidate {
                    ip,
                    mac: None,
                    source: "sweep".into(),
                    label: None,
                    ssh_open: true,
                });
            }
        }
    });
    found
}

// ---- Top-level probe -----------------------------------------------------

fn merge(by_ip: &mut BTreeMap<String, PiCandidate>, cands: Vec<PiCandidate>) {
    for c in cands {
        by_ip
            .entry(c.ip.clone())
            .and_modify(|e| {
                if e.mac.is_none() {
                    e.mac = c.mac.clone();
                }
                if e.label.is_none() {
                    e.label = c.label.clone();
                }
            })
            .or_insert(c);
    }
}

pub fn probe(host: Option<&str>, sweep: bool) -> ProbeResult {
    let interfaces = list_interfaces();
    let mut by_ip: BTreeMap<String, PiCandidate> = BTreeMap::new();

    if let Some(h) = host {
        by_ip.insert(
            h.to_string(),
            PiCandidate {
                ip: h.to_string(),
                mac: None,
                source: "manual".into(),
                label: None,
                ssh_open: false,
            },
        );
    }
    merge(&mut by_ip, pi_candidates_from_arp());
    merge(&mut by_ip, resolve_hostnames());
    if sweep {
        merge(
            &mut by_ip,
            ssh_sweep(&sweep_subnets(&interfaces), Duration::from_millis(400)),
        );
    }

    let mut candidates: Vec<PiCandidate> = by_ip.into_values().collect();
    ssh_check_all(&mut candidates);
    // Pi-OUI / SSH-ready first, then mDNS, then bare.
    candidates.sort_by_key(|c| (!c.ssh_open, c.label.is_none(), c.source.clone()));

    ProbeResult {
        interfaces,
        candidates,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn norm_mac_strips_separators() {
        assert_eq!(norm_mac("B8-27-EB-12-34-56"), "b827eb123456");
        assert_eq!(norm_mac("dc:a6:32:aa:bb:cc"), "dca632aabbcc");
    }

    #[test]
    fn pi_label_matches_known_ouis() {
        assert_eq!(
            pi_label("b8-27-eb-00-00-00"),
            Some("Raspberry Pi (1/2/3/Zero)")
        );
        assert_eq!(pi_label("d8-3a-dd-00-00-00"), Some("Raspberry Pi 5"));
        assert_eq!(pi_label("00-11-22-33-44-55"), None);
    }

    #[test]
    fn arp_regexes_extract_ip_and_mac() {
        let line = "  192.168.137.42       b8-27-eb-aa-bb-cc     dynamic";
        assert_eq!(ip_regex().find(line).unwrap().as_str(), "192.168.137.42");
        let mac = mac_regex().captures(line).unwrap().get(1).unwrap().as_str();
        assert_eq!(norm_mac(mac), "b827ebaabbcc");
    }

    #[test]
    fn sweep_subnets_only_ics_range() {
        let ifaces = vec![
            Interface {
                name: "eth0".into(),
                status: "Up".into(),
                ipv4: Some("192.168.137.1".into()),
                link_local: false,
            },
            Interface {
                name: "wifi".into(),
                status: "Up".into(),
                ipv4: Some("192.168.1.20".into()),
                link_local: false,
            },
            Interface {
                name: "ll".into(),
                status: "Up".into(),
                ipv4: Some("169.254.1.1".into()),
                link_local: true,
            },
        ];
        assert_eq!(sweep_subnets(&ifaces), vec!["192.168.137".to_string()]);
    }

    #[test]
    fn probe_does_not_panic() {
        let _ = probe(None, false);
    }
}
