use crate::cli::{AuthLoginArgs, AuthLogoutArgs};
use crate::tools;
use anyhow::{Context, Result};
use reqwest::blocking::Client;
use std::time::Duration;

pub fn run_login(args: &AuthLoginArgs) -> Result<()> {
    let config = tools::config::load()?;
    let server_url = args
        .server
        .as_deref()
        .unwrap_or(&config.diagnosis.server_url)
        .to_string();

    if let (Some(email), Some(password)) = (&args.email, &args.password) {
        // Headless / CI path — direct credential exchange
        let tokens = tools::auth::direct_login(&server_url, email, password)?;
        tools::config::set_diagnosis_tokens(&tokens.access_token, &tokens.refresh_token)?;
        println!("Authenticated as {email}");
        return Ok(());
    }

    // Interactive browser flow
    let (listener, port) = tools::auth::bind_callback_server()?;
    let callback_url = format!("http://127.0.0.1:{port}/callback");
    let portal_url = format!(
        "{}/auth/portal?cb={}",
        server_url,
        tools::auth::percent_encode(&callback_url)
    );

    println!("Opening browser to sign in…");
    println!("  {portal_url}");
    println!();
    println!("If the browser does not open, paste the URL above into your browser.");

    tools::auth::open_browser(&portal_url)?;

    println!("Waiting for login (timeout 5 min, Ctrl+C to cancel)…");
    let tokens = tools::auth::wait_for_callback(listener, 300)?;

    tools::config::set_diagnosis_tokens(&tokens.access_token, &tokens.refresh_token)?;
    println!("Authenticated successfully.");
    Ok(())
}

pub fn run_logout(args: &AuthLogoutArgs) -> Result<()> {
    let config = tools::config::load()?;
    let server_url = args
        .server
        .as_deref()
        .unwrap_or(&config.diagnosis.server_url)
        .to_string();

    if let Some(token) = &config.diagnosis.access_token {
        let client = Client::new();
        let _ = client
            .post(format!("{server_url}/api/auth/logout"))
            .header("Authorization", format!("Bearer {token}"))
            .timeout(Duration::from_secs(10))
            .send();
    }

    tools::config::clear_diagnosis_tokens().context("failed to clear tokens from config")?;
    println!("Logged out.");
    Ok(())
}

pub fn run_status() -> Result<()> {
    let config = tools::config::load()?;
    let diag = &config.diagnosis;
    if diag.access_token.is_some() {
        println!("Authenticated  (server: {})", diag.server_url);
        println!("  access_token : saved");
        println!(
            "  refresh_token: {}",
            if diag.refresh_token.is_some() {
                "saved"
            } else {
                "none"
            }
        );
    } else {
        println!("Not authenticated  (server: {})", diag.server_url);
        println!("  Run `nff auth login` to sign in.");
    }
    Ok(())
}
