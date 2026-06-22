use std::io::{Read, Write};
use std::net::TcpListener;
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use serde::Deserialize;

#[derive(Debug, Clone)]
pub struct TokenResponse {
    pub access_token: String,
    pub refresh_token: String,
    #[allow(dead_code)]
    pub expires_in: u64,
}

#[derive(Deserialize)]
struct RefreshPayload {
    access_token: String,
    refresh_token: String,
    expires_in: u64,
}

#[derive(Deserialize)]
struct LoginPayload {
    access_token: String,
    refresh_token: String,
    expires_in: u64,
}

/// Percent-encode a string for use as a query parameter value.
pub fn percent_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len() * 3);
    for byte in s.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(byte as char)
            }
            b => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// Opens the system browser to the given URL.
pub fn open_browser(url: &str) -> Result<()> {
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", url])
            .spawn()
            .context("failed to open browser")?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(url)
            .spawn()
            .context("failed to open browser")?;
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(url)
            .spawn()
            .context("failed to open browser")?;
    }
    Ok(())
}

/// Bind to 127.0.0.1:0 — the OS assigns an available port.
pub fn bind_callback_server() -> Result<(TcpListener, u16)> {
    let listener =
        TcpListener::bind("127.0.0.1:0").context("failed to bind local callback server")?;
    let port = listener.local_addr()?.port();
    Ok((listener, port))
}

/// Accept exactly one HTTP GET /callback?... connection, parse tokens, respond with a
/// success page. Blocks until a connection arrives or `timeout_secs` elapses.
pub fn wait_for_callback(listener: TcpListener, timeout_secs: u64) -> Result<TokenResponse> {
    let (tx, rx) = std::sync::mpsc::channel::<Result<TokenResponse>>();

    std::thread::spawn(move || {
        let result = accept_one(&listener);
        tx.send(result).ok();
    });

    rx.recv_timeout(Duration::from_secs(timeout_secs))
        .map_err(|_| anyhow!("login timed out — no browser callback received"))?
}

fn accept_one(listener: &TcpListener) -> Result<TokenResponse> {
    let (mut stream, _) = listener.accept().context("accept failed")?;

    let mut buf = [0u8; 8192];
    let n = stream.read(&mut buf).unwrap_or(0);
    let request = std::str::from_utf8(&buf[..n]).unwrap_or("");

    let tokens = parse_callback_request(request)
        .ok_or_else(|| anyhow!("could not parse auth tokens from browser callback"))?;

    let body = concat!(
        "<!DOCTYPE html><html><head><title>nff</title></head><body>",
        "<h2 style=\"font-family:sans-serif;margin:2rem\">",
        "Authenticated! You can close this tab.",
        "</h2></body></html>"
    );
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(),
        body
    );
    stream.write_all(response.as_bytes()).ok();

    Ok(tokens)
}

fn parse_callback_request(request: &str) -> Option<TokenResponse> {
    // First line: "GET /callback?<query> HTTP/1.1"
    let first_line = request.lines().next()?;
    let path = first_line.split_whitespace().nth(1)?;
    let query = path.split_once('?')?.1;

    let mut access_token = None;
    let mut refresh_token = None;
    let mut expires_in = 3600u64;

    for kv in query.split('&') {
        if let Some((k, v)) = kv.split_once('=') {
            let v = url_decode(v);
            match k {
                "access_token" => access_token = Some(v),
                "refresh_token" => refresh_token = Some(v),
                "expires_in" => expires_in = v.parse().unwrap_or(3600),
                _ => {}
            }
        }
    }

    Some(TokenResponse {
        access_token: access_token?,
        refresh_token: refresh_token?,
        expires_in,
    })
}

fn url_decode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hex = std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or("00");
            if let Ok(byte) = u8::from_str_radix(hex, 16) {
                out.push(byte as char);
                i += 3;
                continue;
            }
        } else if bytes[i] == b'+' {
            out.push(' ');
            i += 1;
            continue;
        }
        out.push(bytes[i] as char);
        i += 1;
    }
    out
}

/// POST /api/auth/refresh — exchange a refresh token for new tokens.
pub fn refresh_tokens(server_url: &str, refresh_token: &str) -> Result<TokenResponse> {
    let url = format!("{server_url}/api/auth/refresh");
    let client = reqwest::blocking::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "refresh_token": refresh_token }))
        .timeout(Duration::from_secs(15))
        .send()
        .context("failed to reach diagnosis server for token refresh")?;

    if !resp.status().is_success() {
        return Err(anyhow!("token refresh failed (HTTP {})", resp.status()));
    }

    let data: RefreshPayload = resp
        .json()
        .context("invalid refresh response from server")?;
    Ok(TokenResponse {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in,
    })
}

/// POST /api/auth/login — direct credential login (for CI/headless).
pub fn direct_login(server_url: &str, email: &str, password: &str) -> Result<TokenResponse> {
    let url = format!("{server_url}/api/auth/login");
    let client = reqwest::blocking::Client::new();
    let resp = client
        .post(&url)
        .json(&serde_json::json!({ "email": email, "password": password }))
        .timeout(Duration::from_secs(15))
        .send()
        .context("failed to reach diagnosis server for login")?;

    if !resp.status().is_success() {
        return Err(anyhow!("login failed (HTTP {})", resp.status()));
    }

    let data: LoginPayload = resp.json().context("invalid login response from server")?;
    Ok(TokenResponse {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in,
    })
}
