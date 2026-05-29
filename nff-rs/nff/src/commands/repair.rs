use crate::cli::{AuthLoginArgs, RepairArgs};
use crate::tools;
use anyhow::{anyhow, Context, Result};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;

#[derive(Serialize)]
struct RepairRequest<'a> {
    serial_output: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    build_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    board: Option<&'a str>,
}

#[derive(Deserialize, Debug)]
struct DiagnosisOutput {
    crash_class: String,
    root_cause: String,
    confidence: f64,
    #[serde(default)]
    candidates: Vec<Candidate>,
}

#[derive(Deserialize, Debug)]
struct Candidate {
    crash_class: String,
    explanation: String,
}

#[derive(Deserialize, Debug)]
struct RepairOutput {
    diagnosis: DiagnosisOutput,
    build_id_used: String,
}

pub fn run(args: &RepairArgs) -> Result<()> {
    let mut config = tools::config::load()?;
    let server_url = args
        .server
        .as_deref()
        .unwrap_or(&config.diagnosis.server_url)
        .to_string();

    // Ensure the user is authenticated; trigger browser login if not.
    if config.diagnosis.access_token.is_none() {
        eprintln!("Authentication required. Starting login…");
        let login_args = AuthLoginArgs {
            email: None,
            password: None,
            server: Some(server_url.clone()),
        };
        crate::commands::auth::run_login(&login_args)?;
        config = tools::config::load()?;
    }

    let access_token = config
        .diagnosis
        .access_token
        .clone()
        .ok_or_else(|| anyhow!("not authenticated — run `nff auth login`"))?;

    // Collect serial output.
    let serial_output = if let Some(text) = &args.serial {
        text.clone()
    } else {
        let duration_ms = args.capture_ms.unwrap_or(5000);
        eprintln!("Capturing serial for {duration_ms} ms…");
        tools::serial::serial_read(duration_ms as u64, args.port.as_deref(), args.baud)
    };

    if serial_output.trim().is_empty() || serial_output.starts_with("ERROR:") {
        anyhow::bail!(
            "no serial output captured — connect a device or use --serial to pass output directly"
        );
    }

    // Call /repair, with one automatic retry after token refresh on 401.
    match call_repair(
        &server_url,
        &access_token,
        &serial_output,
        args.build_id.as_deref(),
        args.board.as_deref(),
    ) {
        Ok(output) => {
            print_output(&output);
            Ok(())
        }
        Err(e) if is_unauthorized(&e) => {
            // Try refreshing the token once before giving up.
            let Some(refresh) = config.diagnosis.refresh_token.clone() else {
                tools::config::clear_diagnosis_tokens()?;
                anyhow::bail!("session expired — run `nff auth login`");
            };

            eprintln!("Session expired, refreshing…");
            match tools::auth::refresh_tokens(&server_url, &refresh) {
                Ok(new_tokens) => {
                    tools::config::set_diagnosis_tokens(
                        &new_tokens.access_token,
                        &new_tokens.refresh_token,
                    )?;
                    let output = call_repair(
                        &server_url,
                        &new_tokens.access_token,
                        &serial_output,
                        args.build_id.as_deref(),
                        args.board.as_deref(),
                    )?;
                    print_output(&output);
                    Ok(())
                }
                Err(_) => {
                    tools::config::clear_diagnosis_tokens()?;
                    anyhow::bail!("session expired — run `nff auth login` to re-authenticate");
                }
            }
        }
        Err(e) => Err(e),
    }
}

fn call_repair(
    server_url: &str,
    token: &str,
    serial_output: &str,
    build_id: Option<&str>,
    board: Option<&str>,
) -> Result<RepairOutput> {
    let client = Client::new();
    let resp = client
        .post(format!("{server_url}/repair"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&RepairRequest { serial_output, build_id, board })
        .timeout(Duration::from_secs(60))
        .send()
        .context("failed to reach diagnosis server")?;

    let status = resp.status();
    if status == reqwest::StatusCode::UNAUTHORIZED {
        return Err(anyhow!("unauthorized (HTTP 401)"));
    }
    if !status.is_success() {
        let body = resp.text().unwrap_or_default();
        return Err(anyhow!("server returned HTTP {status}: {body}"));
    }

    resp.json::<RepairOutput>().context("failed to parse repair response")
}

fn is_unauthorized(e: &anyhow::Error) -> bool {
    e.to_string().contains("401")
}

fn print_output(output: &RepairOutput) {
    let d = &output.diagnosis;
    println!("─────────────────────────────────────────");
    println!("  Crash class : {}", d.crash_class);
    println!("  Confidence  : {:.0}%", d.confidence * 100.0);
    if output.build_id_used != "unknown" {
        println!("  Build ID    : {}", output.build_id_used);
    }
    println!();
    println!("  Root cause:");
    for line in d.root_cause.lines() {
        println!("    {line}");
    }
    if !d.candidates.is_empty() {
        println!();
        println!("  Alternative diagnoses:");
        for c in &d.candidates {
            println!("    [{}] {}", c.crash_class, c.explanation);
        }
    }
    println!("─────────────────────────────────────────");
}
