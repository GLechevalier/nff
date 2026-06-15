//! `nff provision batch` — fleet enrollment provisioning.
//!
//! Creates ONE shared bootstrap credential for a whole batch of devices. You flash the resulting
//! credentials.h into a single firmware image and push it to the entire batch with one OTA: every
//! device announces itself, shows up in the dashboard Enroll tab, and — once accepted —
//! automatically rolls over to a unique per-device certificate. No per-device credential
//! generation, no codes.

use std::time::Duration;

use anyhow::{anyhow, Context};

use crate::cli::BatchArgs;

/// Resolve fleet URL + secret from flags, falling back to env vars.
fn resolve_fleet(
    fleet_url: Option<&str>,
    secret: Option<&str>,
) -> anyhow::Result<(String, String)> {
    let url = fleet_url
        .map(String::from)
        .or_else(|| std::env::var("NFF_FLEET_URL").ok())
        .ok_or_else(|| anyhow!("fleet URL required: pass --fleet-url or set NFF_FLEET_URL"))?;
    let secret = secret
        .map(String::from)
        .or_else(|| std::env::var("NFF_FLEET_SECRET").ok())
        .ok_or_else(|| anyhow!("fleet secret required: pass --secret or set NFF_FLEET_SECRET"))?;
    Ok((url.trim_end_matches('/').to_string(), secret))
}

pub fn run_batch(args: &BatchArgs) -> anyhow::Result<()> {
    let (fleet_url, secret) = resolve_fleet(args.fleet_url.as_deref(), args.secret.as_deref())?;

    let mut body = serde_json::json!({ "project_id": args.project });
    if let Some(count) = args.count {
        body["count"] = serde_json::json!(count);
    }

    let client = reqwest::blocking::Client::new();
    let resp = client
        .post(format!("{fleet_url}/internal/provision-batch"))
        .header("X-Fleet-Secret", secret)
        .json(&body)
        .timeout(Duration::from_secs(30))
        .send()
        .with_context(|| format!("could not reach fleet at {fleet_url}"))?;

    let status = resp.status();
    if !status.is_success() {
        let text = resp.text().unwrap_or_default();
        let detail = serde_json::from_str::<serde_json::Value>(&text)
            .ok()
            .and_then(|v| v.get("error").and_then(|e| e.as_str()).map(String::from))
            .unwrap_or(text);
        return Err(anyhow!("fleet returned {}: {detail}", status.as_u16()));
    }

    let data: serde_json::Value = resp.json().context("invalid response from fleet")?;
    let header = data
        .get("bootstrap_header")
        .and_then(|h| h.as_str())
        .ok_or_else(|| anyhow!("fleet did not return the bootstrap header content"))?;

    std::fs::write(&args.out, header)
        .with_context(|| format!("could not write {}", args.out.display()))?;

    let batch_id = data.get("batch_id").and_then(|b| b.as_str()).unwrap_or("?");
    let hours = data.get("expires_in_hours").and_then(|h| h.as_u64()).unwrap_or(24);
    println!("OK: batch {batch_id} created for project {}", args.project);
    println!("  credentials.h written to {}", args.out.display());
    match args.count {
        Some(n) => println!("  valid {hours}h, quota {n} device(s)"),
        None => println!("  valid {hours}h, no quota"),
    }
    println!(
        "  build ONE image with this header and flash/OTA the whole batch; \
         accept devices in the dashboard Enroll tab."
    );
    Ok(())
}
