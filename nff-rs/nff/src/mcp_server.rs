use std::net::TcpListener;
use std::sync::{Arc, Mutex};

use rmcp::{
    ServerHandler,
    handler::server::wrapper::Parameters,
    model::{Implementation, ServerCapabilities, ServerInfo},
    tool, tool_handler, tool_router,
};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{json, Value};

/// Shared MCP server state. Cloned per session by the streamable-HTTP factory, so
/// the `Arc` is shared across all sessions — `authenticate` stashes a pending
/// browser-callback listener here that `complete_authentication` later drains.
#[derive(Clone, Default)]
pub struct NffServer {
    pending_auth: Arc<Mutex<Option<TcpListener>>>,
}

// ---------------------------------------------------------------------------
// Parameter types
// ---------------------------------------------------------------------------

#[derive(Deserialize, JsonSchema)]
struct FlashParams {
    /// Path to a .ino file or sketch folder (preferred).
    sketch: Option<String>,
    /// Full Arduino/C++ sketch source code (alternative to sketch=).
    code: Option<String>,
    /// Board FQBN, e.g. 'arduino:avr:uno'. Defaults to config.
    board: Option<String>,
    /// Serial port, e.g. 'COM3'. Defaults to config.
    port: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct CompileParams {
    /// Path to a .ino file or sketch folder (preferred).
    sketch: Option<String>,
    /// Full Arduino/C++ sketch source code (alternative to sketch=).
    code: Option<String>,
    /// Board FQBN; defaults to the configured board.
    board: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct SerialReadParams {
    /// How long to listen in milliseconds
    #[serde(default = "default_3000_u64")]
    duration_ms: u64,
    /// Serial port. Defaults to config.
    port: Option<String>,
    /// Baud rate. Defaults to config (9600).
    baud: Option<u32>,
}
fn default_3000_u64() -> u64 {
    3000
}

#[derive(Deserialize, JsonSchema)]
struct SerialWriteParams {
    /// String to transmit. A newline is appended if absent.
    data: String,
    /// Serial port. Defaults to config.
    port: Option<String>,
    /// Baud rate. Defaults to config (9600).
    baud: Option<u32>,
}

#[derive(Deserialize, JsonSchema)]
struct PortParam {
    /// Serial port. Defaults to config.
    port: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct WokwiFlashParams {
    /// Full Arduino/C++ sketch source code
    code: String,
    /// Board FQBN. Defaults to config.
    board: Option<String>,
    /// Simulation wall-clock timeout in milliseconds
    #[serde(default = "default_5000")]
    timeout_ms: u32,
}
fn default_5000() -> u32 {
    5000
}

#[derive(Deserialize, JsonSchema)]
struct WokwiSerialReadParams {
    /// Full Arduino/C++ sketch source code
    code: String,
    /// Board FQBN. Defaults to config.
    board: Option<String>,
    /// Simulation duration in milliseconds
    #[serde(default = "default_3000_u32")]
    duration_ms: u32,
}
fn default_3000_u32() -> u32 {
    3000
}

#[derive(Deserialize, JsonSchema)]
struct BoardParam {
    /// Board FQBN, e.g. 'arduino:avr:uno'
    board: String,
}

#[derive(Deserialize, JsonSchema)]
struct RepairParams {
    /// Raw serial/crash output to diagnose
    serial_output: String,
    /// Firmware build ID (hex hash of ELF). Enables symbol resolution when provided.
    build_id: Option<String>,
    /// Board FQBN hint for the diagnosis server
    board: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct AuthLoginParams {
    /// Email for direct login. Omit both email and password to open a browser OAuth flow instead.
    email: Option<String>,
    /// Password for direct login. Required when email is provided.
    password: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct CompleteAuthParams {
    /// How long to wait for the browser login to complete, in seconds.
    #[serde(default = "default_120_u32")]
    timeout: u32,
}
fn default_120_u32() -> u32 {
    120
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn resolve_fqbn(board: Option<String>) -> Result<String, String> {
    let fqbn = board
        .or_else(|| {
            crate::tools::config::get_default_device()
                .ok()
                .and_then(|d| d.fqbn)
        })
        .unwrap_or_default();
    if fqbn.is_empty() {
        Err("Missing board FQBN (pass board= or run `nff init`)".into())
    } else {
        Ok(fqbn)
    }
}

fn json_sim_error(serial_output: &str, compile_output: &str, exit_code: i32) -> String {
    json!({
        "serial_output": serial_output,
        "compile_output": compile_output,
        "exit_code": exit_code,
        "simulated": true,
    })
    .to_string()
}

// ---------------------------------------------------------------------------
// Auth helpers (shared by the authenticate / auth_reconnect tools)
// ---------------------------------------------------------------------------

/// Direct email+password login, saving the tokens. Returns an `OK:`/`ERROR:` string.
/// MUST run on a plain OS thread — reqwest::blocking panics under the Tokio runtime.
fn direct_login_and_save(email: &str, password: &str) -> String {
    match login_blocking(Some(email.to_string()), Some(password.to_string())) {
        Ok(()) => "OK: authenticated".into(),
        Err(e) => format!("ERROR: {e}"),
    }
}

/// Perform a full login (direct or synchronous browser flow) and persist the tokens.
/// MUST run on a plain OS thread (uses reqwest::blocking via direct_login).
fn login_blocking(email: Option<String>, password: Option<String>) -> Result<(), String> {
    let cfg = crate::tools::config::load().map_err(|e| e.to_string())?;
    let tokens = match (email, password) {
        (Some(email), Some(password)) => {
            crate::tools::auth::direct_login(&cfg.diagnosis.server_url, &email, &password)
                .map_err(|e| e.to_string())?
        }
        (None, None) => {
            let (listener, port) =
                crate::tools::auth::bind_callback_server().map_err(|e| e.to_string())?;
            let callback_url = format!("http://127.0.0.1:{port}/callback");
            let login_url = format!(
                "{}/login?cb={}",
                cfg.diagnosis.frontend_url,
                crate::tools::auth::percent_encode(&callback_url)
            );
            let _ = crate::tools::auth::open_browser(&login_url);
            crate::tools::auth::wait_for_callback(listener, 300).map_err(|e| e.to_string())?
        }
        _ => return Err("provide both email and password, or neither for browser login".into()),
    };
    crate::tools::config::set_diagnosis_tokens(&tokens.access_token, &tokens.refresh_token)
        .map_err(|e| e.to_string())
}

/// Re-register the nff MCP server with the Claude Code CLI (HTTP transport).
fn reregister_claude() -> String {
    let url = crate::commands::init::MCP_URL;
    let Ok(claude) = which::which("claude") else {
        return format!("`claude` CLI not found — register manually: claude mcp add --scope user --transport http nff {url}");
    };
    // Remove any stale registration first; ignore failure if none exists.
    let _ = std::process::Command::new(&claude)
        .args(["mcp", "remove", "--scope", "user", "nff"])
        .output();
    let out = std::process::Command::new(&claude)
        .args(["mcp", "add", "--scope", "user", "--transport", "http", "nff", url])
        .output();
    match out {
        Ok(o) if o.status.success() => "Re-registered with Claude Code.".into(),
        _ => format!("Could not re-register; run: claude mcp add --scope user --transport http nff {url}"),
    }
}

// ---------------------------------------------------------------------------
// OAuth 2.1 proxy — mints opaque MCP tokens decoupled from the diagnosis JWT.
//
// Claude Code authorizes once via the browser; the proxy hands it an opaque
// access+refresh pair (nff_at_/nff_rt_) with a 24h TTL and refreshes it silently,
// so the MCP session does not expire with the upstream (short-lived) Supabase JWT.
// ---------------------------------------------------------------------------

use std::collections::HashMap;

use axum::{
    extract::{Extension, Path as AxumPath, RawQuery, State},
    http::{header, StatusCode},
    middleware::Next,
    response::{IntoResponse, Redirect, Response},
};

/// Lifetime of the opaque MCP access token handed to Claude Code (24h).
const MCP_TOKEN_TTL: u64 = 86_400;

#[derive(Clone)]
struct OAuthSession {
    redirect_uri: String,
    state: String,
}

/// Ephemeral OAuth proxy state — cleared on server restart, which forces a fresh login.
struct OAuthState {
    base: String,
    sessions: Mutex<HashMap<String, OAuthSession>>,
    auth_codes: Mutex<HashMap<String, String>>, // auth code -> minted MCP access token
}

/// 32 random bytes hex-encoded behind `prefix` — an opaque, unguessable token.
fn random_token(prefix: &str) -> String {
    let mut buf = [0u8; 32];
    getrandom::fill(&mut buf).expect("OS RNG unavailable");
    let mut s = String::with_capacity(prefix.len() + 64);
    s.push_str(prefix);
    for b in buf {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

/// Mint and persist a fresh opaque access+refresh pair, invalidating any prior pair.
/// Returns the new access token (the refresh token is read back from config).
fn mint_mcp_session() -> String {
    let access = random_token("nff_at_");
    let refresh = random_token("nff_rt_");
    let _ = crate::tools::config::set_mcp_tokens(&access, &refresh);
    access
}

fn json_response(status: StatusCode, value: &Value) -> Response {
    (
        status,
        [(header::CONTENT_TYPE, "application/json")],
        value.to_string(),
    )
        .into_response()
}

fn parse_query(q: &Option<String>) -> HashMap<String, String> {
    let mut map = HashMap::new();
    if let Some(q) = q {
        for (k, v) in form_urlencoded::parse(q.as_bytes()) {
            map.insert(k.into_owned(), v.into_owned());
        }
    }
    map
}

/// Bearer guard on `/mcp`: accept the opaque MCP access token OR (legacy) the raw
/// diagnosis JWT, so sessions authorized before opaque tokens existed keep working.
async fn bearer_auth(
    State(oauth): State<Arc<OAuthState>>,
    request: axum::extract::Request,
    next: Next,
) -> Response {
    let presented = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(str::to_string)
        .filter(|t| !t.is_empty());
    let cfg = crate::tools::config::load().ok();
    let mcp_token = cfg.as_ref().and_then(|c| c.mcp.access_token.clone());
    let legacy_token = cfg.as_ref().and_then(|c| c.diagnosis.access_token.clone());
    let authed = matches!(&presented, Some(t) if Some(t) == mcp_token.as_ref() || Some(t) == legacy_token.as_ref());
    if authed {
        next.run(request).await
    } else {
        let rm = format!("{}/.well-known/oauth-protected-resource", oauth.base);
        (
            StatusCode::UNAUTHORIZED,
            [(
                header::WWW_AUTHENTICATE,
                format!("Bearer realm=\"nff\", resource_metadata=\"{rm}\""),
            )],
            json!({ "error": "unauthorized" }).to_string(),
        )
            .into_response()
    }
}

async fn wk_resource(Extension(oauth): Extension<Arc<OAuthState>>) -> Response {
    json_response(
        StatusCode::OK,
        &json!({ "resource": oauth.base, "authorization_servers": [oauth.base] }),
    )
}

async fn wk_authorization_server(Extension(oauth): Extension<Arc<OAuthState>>) -> Response {
    let b = &oauth.base;
    json_response(
        StatusCode::OK,
        &json!({
            "issuer": b,
            "authorization_endpoint": format!("{b}/oauth/authorize"),
            "token_endpoint": format!("{b}/oauth/token"),
            "registration_endpoint": format!("{b}/oauth/register"),
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
        }),
    )
}

async fn oauth_register() -> Response {
    json_response(
        StatusCode::CREATED,
        &json!({
            "client_id": "nff-mcp",
            "client_secret": "unused",
            "redirect_uris": [],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }),
    )
}

async fn oauth_authorize(
    Extension(oauth): Extension<Arc<OAuthState>>,
    RawQuery(q): RawQuery,
) -> Response {
    let params = parse_query(&q);
    let Some(redirect_uri) = params.get("redirect_uri").cloned() else {
        return json_response(StatusCode::BAD_REQUEST, &json!({ "error": "missing redirect_uri" }));
    };
    let state = params.get("state").cloned().unwrap_or_default();
    let cfg = crate::tools::config::load().unwrap_or_default();

    // Fast path: diagnosis tokens already present — no browser round-trip needed.
    if cfg.diagnosis.access_token.is_some() {
        let code = random_token("code_");
        oauth.auth_codes.lock().unwrap().insert(code.clone(), mint_mcp_session());
        let sep = if redirect_uri.contains('?') { '&' } else { '?' };
        return Redirect::to(&format!("{redirect_uri}{sep}code={code}&state={state}")).into_response();
    }

    let session_id = random_token("sess_");
    oauth
        .sessions
        .lock()
        .unwrap()
        .insert(session_id.clone(), OAuthSession { redirect_uri, state });
    let callback_url = format!("{}/oauth/callback/{session_id}", oauth.base);
    let login_url = format!(
        "{}/login?cb={}",
        cfg.diagnosis.frontend_url,
        crate::tools::auth::percent_encode(&callback_url)
    );
    Redirect::to(&login_url).into_response()
}

async fn oauth_callback(
    Extension(oauth): Extension<Arc<OAuthState>>,
    AxumPath(session_id): AxumPath<String>,
    RawQuery(q): RawQuery,
) -> Response {
    let params = parse_query(&q);
    let Some(access_token) = params.get("access_token").cloned() else {
        return json_response(
            StatusCode::BAD_REQUEST,
            &json!({ "error": "missing access_token in callback" }),
        );
    };
    let refresh_token = params.get("refresh_token").cloned().unwrap_or_default();
    let _ = crate::tools::config::set_diagnosis_tokens(&access_token, &refresh_token);

    let session = oauth.sessions.lock().unwrap().remove(&session_id);
    let Some(session) = session else {
        // Session expired (server restarted mid-flow). Tokens are saved anyway.
        return (
            StatusCode::OK,
            [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
            "<h2>Authenticated!</h2><p>Tokens saved. Please reconnect the nff MCP server in \
             Claude Code (Settings &rsaquo; MCP &rsaquo; nff &rsaquo; Reconnect) to complete \
             the handshake.</p>"
                .to_string(),
        )
            .into_response();
    };
    let code = random_token("code_");
    oauth.auth_codes.lock().unwrap().insert(code.clone(), mint_mcp_session());
    let sep = if session.redirect_uri.contains('?') { '&' } else { '?' };
    Redirect::to(&format!(
        "{}{sep}code={code}&state={}",
        session.redirect_uri, session.state
    ))
    .into_response()
}

async fn oauth_token(Extension(oauth): Extension<Arc<OAuthState>>, body: String) -> Response {
    let params = parse_query(&Some(body));
    let grant_type = params.get("grant_type").map(String::as_str).unwrap_or("");

    if grant_type == "refresh_token" {
        let presented = params.get("refresh_token").cloned().unwrap_or_default();
        let stored = crate::tools::config::get_mcp_tokens().ok().and_then(|m| m.refresh_token);
        if presented.is_empty() || stored.as_deref() != Some(presented.as_str()) {
            return json_response(StatusCode::BAD_REQUEST, &json!({ "error": "invalid_grant" }));
        }
        // Rotate: mint a fresh pair, invalidating the old one.
        let access = mint_mcp_session();
        let refresh = crate::tools::config::get_mcp_tokens()
            .ok()
            .and_then(|m| m.refresh_token)
            .unwrap_or_default();
        return json_response(
            StatusCode::OK,
            &json!({
                "access_token": access, "refresh_token": refresh,
                "token_type": "bearer", "expires_in": MCP_TOKEN_TTL,
            }),
        );
    }

    let code = params.get("code").cloned().unwrap_or_default();
    let access = oauth.auth_codes.lock().unwrap().remove(&code);
    let Some(access) = access else {
        return json_response(StatusCode::BAD_REQUEST, &json!({ "error": "invalid_grant" }));
    };
    let refresh = crate::tools::config::get_mcp_tokens()
        .ok()
        .and_then(|m| m.refresh_token)
        .unwrap_or_default();
    json_response(
        StatusCode::OK,
        &json!({
            "access_token": access, "refresh_token": refresh,
            "token_type": "bearer", "expires_in": MCP_TOKEN_TTL,
        }),
    )
}

// ---------------------------------------------------------------------------
// MCP server
// ---------------------------------------------------------------------------

#[tool_router]
impl NffServer {
    #[tool(description = "List all connected USB/serial devices with board identification")]
    fn list_devices(&self) -> String {
        let devices = crate::tools::boards::list_devices();
        let list: Vec<Value> = devices
            .iter()
            .map(|d| {
                json!({
                    "port": d.port,
                    "board": d.board,
                    "fqbn": d.fqbn,
                    "vendor_id": d.vendor_id,
                    "product_id": d.product_id,
                    "wokwi_chip": d.wokwi_chip,
                })
            })
            .collect();
        json!({ "devices": list }).to_string()
    }

    #[tool(description = "Compile a sketch ONLY — no board or port needed. Use this to verify a sketch builds. Pass sketch= (path to a .ino file or folder, preferred) or code=. board= defaults to the configured FQBN. Returns JSON: {ok, fqbn, elf, image, artifacts, errors, output}.")]
    fn compile(&self, Parameters(p): Parameters<CompileParams>) -> String {
        use crate::tools::{config, toolchain};
        let fqbn = p
            .board
            .or_else(|| config::get_default_device().ok().and_then(|d| d.fqbn))
            .unwrap_or_default();
        let source = p.sketch.as_ref().map(std::path::PathBuf::from);
        match toolchain::compile_only(&fqbn, p.code.as_deref(), source.as_deref()) {
            Ok(r) => r.to_json().to_string(),
            Err(e) => format!("ERROR: {e}"),
        }
    }

    #[tool(description = "Compile AND upload a sketch to the connected board (needs a port). To only check that a sketch builds, use `compile` instead. Pass sketch= (path, preferred) or code=. Returns OK: on success or ERROR: on failure.")]
    fn flash(&self, Parameters(p): Parameters<FlashParams>) -> String {
        use crate::tools::{config, toolchain};
        let device = config::get_default_device().unwrap_or_default();
        let fqbn = p.board.or_else(|| device.fqbn.clone()).unwrap_or_default();
        let port = p
            .port
            .or_else(|| device.port.clone().filter(|s| !s.is_empty()))
            .unwrap_or_default();
        if fqbn.is_empty() {
            return "ERROR: Missing board FQBN (pass board= or run `nff init`)".into();
        }
        if port.is_empty() {
            return "ERROR: Missing port (pass port= or run `nff init`)".into();
        }
        let source = p.sketch.as_ref().map(std::path::PathBuf::from);
        let sketch_dir = match toolchain::resolve_sketch_dir(p.code.as_deref(), source.as_deref()) {
            Ok(d) => d,
            Err(e) => return format!("ERROR: {e}"),
        };
        toolchain::flash_sketch(&sketch_dir, &fqbn, &port)
    }

    #[tool(description = "Capture serial output from the device for a given duration. Returns captured text or ERROR:.")]
    fn serial_read(&self, Parameters(p): Parameters<SerialReadParams>) -> String {
        crate::tools::serial::serial_read(p.duration_ms, p.port.as_deref(), p.baud)
    }

    #[tool(description = "Send a string to the device over serial. Returns OK: wrote N bytes or ERROR:.")]
    fn serial_write(&self, Parameters(p): Parameters<SerialWriteParams>) -> String {
        crate::tools::serial::serial_write(&p.data, p.port.as_deref(), p.baud)
    }

    #[tool(description = "Toggle DTR to hardware-reset the board. Returns OK: or ERROR:.")]
    fn reset_device(&self, Parameters(p): Parameters<PortParam>) -> String {
        crate::tools::serial::reset_device(p.port.as_deref())
    }

    #[tool(description = "Return detailed information about the connected device as JSON")]
    fn get_device_info(&self, Parameters(p): Parameters<PortParam>) -> String {
        use crate::tools::{boards, config, serial};
        let port = match serial::resolve_port(p.port.as_deref()) {
            Ok(p) => p,
            Err(e) => return json!({"error": e.to_string()}).to_string(),
        };
        let device = boards::find_device(Some(&port));
        let baud = config::get_default_device().map(|d| d.baud).unwrap_or(9600);
        if let Some(d) = device {
            json!({
                "port": d.port,
                "board": d.board,
                "fqbn": d.fqbn,
                "baud": baud,
                "vendor_id": d.vendor_id,
                "product_id": d.product_id,
                "wokwi_chip": d.wokwi_chip,
            })
            .to_string()
        } else {
            let cfg = config::get_default_device().unwrap_or_default();
            json!({
                "port": port,
                "board": cfg.board.unwrap_or_else(|| "Unknown".into()),
                "fqbn": cfg.fqbn.unwrap_or_default(),
                "baud": baud,
                "vendor_id": "",
                "product_id": "",
                "wokwi_chip": null,
            })
            .to_string()
        }
    }

    #[tool(description = "Compile a sketch and run it in the Wokwi simulator. No hardware needed. Returns JSON with serial_output, compile_output, exit_code, simulated.")]
    fn wokwi_flash(&self, Parameters(p): Parameters<WokwiFlashParams>) -> String {
        use crate::tools::{toolchain, wokwi};
        let fqbn = match resolve_fqbn(p.board) {
            Ok(f) => f,
            Err(e) => return json_sim_error("", &e, 1),
        };
        let sketch_dir = match toolchain::write_sketch(&p.code, None) {
            Ok(d) => d,
            Err(e) => return json_sim_error("", &e.to_string(), 1),
        };
        let compile_result = match toolchain::compile_sketch(&sketch_dir, &fqbn) {
            Ok(r) => r,
            Err(e) => return json_sim_error("", &format!("compile error: {e}"), 1),
        };
        let compile_output = compile_result.output();
        if !compile_result.success {
            return json_sim_error("", &compile_output, compile_result.returncode);
        }
        let elf_path = match toolchain::locate_compiled_elf(&sketch_dir, &fqbn) {
            Ok(p) => p,
            Err(e) => return json_sim_error("", &format!("{compile_output}\nelf locate error: {e}"), 1),
        };
        let diagram = match wokwi::generate_diagram(&fqbn) {
            Ok(d) => d,
            Err(e) => {
                return json_sim_error("", &format!("{compile_output}\nwokwi setup error: {e}"), 1)
            }
        };
        if let Err(e) = std::fs::write(
            sketch_dir.join("diagram.json"),
            serde_json::to_string_pretty(&diagram).unwrap_or_default(),
        ) {
            return json_sim_error(
                "",
                &format!("{compile_output}\ndiagram.json write error: {e}"),
                1,
            );
        }
        if let Err(e) = wokwi::write_wokwi_toml(&sketch_dir, &elf_path) {
            return json_sim_error("", &format!("{compile_output}\nwokwi.toml error: {e}"), 1);
        }
        match wokwi::run_simulation(&sketch_dir, p.timeout_ms, Some(&elf_path)) {
            Ok(r) => json!({
                "serial_output": r.serial_output,
                "compile_output": compile_output,
                "exit_code": r.exit_code,
                "simulated": true,
            })
            .to_string(),
            Err(e) => json_sim_error(&format!("wokwi error: {e}"), &compile_output, 1),
        }
    }

    #[tool(description = "Compile and simulate a sketch, returning only the serial output string")]
    fn wokwi_serial_read(&self, Parameters(p): Parameters<WokwiSerialReadParams>) -> String {
        use crate::tools::{toolchain, wokwi};
        let fqbn = match resolve_fqbn(p.board) {
            Ok(f) => f,
            Err(e) => return format!("ERROR: {e}"),
        };
        let sketch_dir = match toolchain::write_sketch(&p.code, None) {
            Ok(d) => d,
            Err(e) => return format!("ERROR: {e}"),
        };
        let compile_result = match toolchain::compile_sketch(&sketch_dir, &fqbn) {
            Ok(r) => r,
            Err(e) => return format!("ERROR: compile failed: {e}"),
        };
        if !compile_result.success {
            return format!("ERROR: compile failed:\n{}", compile_result.output());
        }
        let elf_path = match toolchain::locate_compiled_elf(&sketch_dir, &fqbn) {
            Ok(p) => p,
            Err(e) => return format!("ERROR: {e}"),
        };
        let diagram = match wokwi::generate_diagram(&fqbn) {
            Ok(d) => d,
            Err(e) => return format!("ERROR: {e}"),
        };
        if let Err(e) = std::fs::write(
            sketch_dir.join("diagram.json"),
            serde_json::to_string_pretty(&diagram).unwrap_or_default(),
        ) {
            return format!("ERROR: {e}");
        }
        if let Err(e) = wokwi::write_wokwi_toml(&sketch_dir, &elf_path) {
            return format!("ERROR: {e}");
        }
        match wokwi::run_simulation(&sketch_dir, p.duration_ms, Some(&elf_path)) {
            Ok(r) => r.serial_output,
            Err(e) => format!("ERROR: {e}"),
        }
    }

    #[tool(description = "Log in to the nff diagnosis server. Provide email+password for a direct login, or omit both to open the browser login page — then call complete_authentication once you have signed in.")]
    fn authenticate(&self, Parameters(p): Parameters<AuthLoginParams>) -> String {
        match (p.email, p.password) {
            (Some(email), Some(password)) => {
                // reqwest::blocking panics under the rmcp Tokio runtime — offload.
                std::thread::spawn(move || direct_login_and_save(&email, &password))
                    .join()
                    .unwrap_or_else(|_| "ERROR: auth thread panicked".into())
            }
            (None, None) => {
                let cfg = match crate::tools::config::load() {
                    Ok(c) => c,
                    Err(e) => return format!("ERROR: {e}"),
                };
                let (listener, port) = match crate::tools::auth::bind_callback_server() {
                    Ok(v) => v,
                    Err(e) => return format!("ERROR: {e}"),
                };
                let callback_url = format!("http://127.0.0.1:{port}/callback");
                let login_url = format!(
                    "{}/login?cb={}",
                    cfg.diagnosis.frontend_url,
                    crate::tools::auth::percent_encode(&callback_url)
                );
                let _ = crate::tools::auth::open_browser(&login_url);
                *self.pending_auth.lock().unwrap() = Some(listener);
                format!(
                    "OK: browser opened for login. After you sign in, call complete_authentication. \
                     If the browser did not open, visit: {login_url}"
                )
            }
            _ => "ERROR: provide both email and password, or neither for browser login".into(),
        }
    }

    #[tool(description = "Wait for a browser login started by authenticate() to complete and save the tokens. Optional timeout in seconds (default 120).")]
    fn complete_authentication(&self, Parameters(p): Parameters<CompleteAuthParams>) -> String {
        let listener = match self.pending_auth.lock().unwrap().take() {
            Some(l) => l,
            None => {
                return "ERROR: no pending browser login — call authenticate (with no email/password) first".into()
            }
        };
        match crate::tools::auth::wait_for_callback(listener, p.timeout as u64) {
            Ok(t) => {
                match crate::tools::config::set_diagnosis_tokens(&t.access_token, &t.refresh_token) {
                    Ok(_) => "OK: authenticated".into(),
                    Err(e) => format!("ERROR: could not save tokens: {e}"),
                }
            }
            Err(e) => format!("ERROR: {e}"),
        }
    }

    #[tool(description = "Force-clear stored auth tokens locally without calling the server. Use when the server is unreachable or tokens are corrupted.")]
    fn auth_clear(&self) -> String {
        let _ = crate::tools::config::clear_diagnosis_tokens();
        match crate::tools::config::clear_mcp_tokens() {
            Ok(_) => "OK: tokens cleared".into(),
            Err(e) => format!("ERROR: {e}"),
        }
    }

    #[tool(description = "Re-authenticate with the diagnosis server and re-register the MCP connection in Claude Code. Provide email+password for direct login, or omit both for browser OAuth. Restart Claude Code afterwards.")]
    fn auth_reconnect(&self, Parameters(p): Parameters<AuthLoginParams>) -> String {
        let auth_result = std::thread::spawn(move || login_blocking(p.email, p.password))
            .join()
            .unwrap_or_else(|_| Err("auth thread panicked".into()));
        if let Err(e) = auth_result {
            return format!("ERROR: {e}");
        }
        let reg = reregister_claude();
        format!("OK: reconnected. {reg} Restart Claude Code to pick up the new connection.")
    }

    #[tool(description = "Log out from the nff diagnosis server and clear stored tokens.")]
    fn auth_logout(&self) -> String {
        std::thread::spawn(move || {
            let config = match crate::tools::config::load() {
                Ok(c) => c,
                Err(e) => return format!("ERROR: {e}"),
            };
            if let Some(token) = &config.diagnosis.access_token {
                let client = reqwest::blocking::Client::new();
                let _ = client
                    .post(format!("{}/api/auth/logout", config.diagnosis.server_url))
                    .header("Authorization", format!("Bearer {token}"))
                    .timeout(std::time::Duration::from_secs(10))
                    .send();
            }
            match crate::tools::config::clear_diagnosis_tokens() {
                Ok(_) => "OK: logged out".into(),
                Err(e) => format!("ERROR: {e}"),
            }
        })
        .join()
        .unwrap_or_else(|_| "ERROR: logout thread panicked".into())
    }

    #[tool(description = "Return authentication status for the nff diagnosis server. Call this before `repair` to check whether the user is logged in.")]
    fn auth_status(&self) -> String {
        match crate::tools::config::load() {
            Err(e) => format!("ERROR: {e}"),
            Ok(c) => match c.diagnosis.access_token {
                Some(_) => "OK: authenticated".into(),
                None => "ERROR: not authenticated — run `nff auth login`".into(),
            },
        }
    }

    #[tool(description = "Send serial/crash output to the nff diagnosis server and return a structured diagnosis as JSON. Requires prior authentication — run `nff auth login` from the terminal if not yet logged in.")]
    fn repair(&self, Parameters(p): Parameters<RepairParams>) -> String {
        let config = match crate::tools::config::load() {
            Ok(c) => c,
            Err(e) => return format!("ERROR: {e}"),
        };
        let server_url = config.diagnosis.server_url.clone();
        let Some(access_token) = config.diagnosis.access_token.clone() else {
            return "ERROR: not authenticated — run `nff auth login`".into();
        };
        let refresh_token = config.diagnosis.refresh_token.clone();
        let serial_output = p.serial_output;
        let build_id = p.build_id;
        let board = p.board;

        // reqwest::blocking panics when called from within a Tokio runtime (the MCP
        // server runs under one via rmcp). Offload all HTTP work to a plain OS thread.
        std::thread::spawn(move || {
            let result = crate::commands::repair::call_repair(
                &server_url,
                &access_token,
                &serial_output,
                build_id.as_deref(),
                board.as_deref(),
            );
            match result {
                Ok(output) => {
                    serde_json::to_string(&output).unwrap_or_else(|e| format!("ERROR: {e}"))
                }
                Err(e) if e.to_string().contains("401") => {
                    let Some(refresh) = refresh_token else {
                        let _ = crate::tools::config::clear_diagnosis_tokens();
                        return "ERROR: session expired — run `nff auth login`".into();
                    };
                    match crate::tools::auth::refresh_tokens(&server_url, &refresh) {
                        Ok(new_tokens) => {
                            let _ = crate::tools::config::set_diagnosis_tokens(
                                &new_tokens.access_token,
                                &new_tokens.refresh_token,
                            );
                            match crate::commands::repair::call_repair(
                                &server_url,
                                &new_tokens.access_token,
                                &serial_output,
                                build_id.as_deref(),
                                board.as_deref(),
                            ) {
                                Ok(output) => serde_json::to_string(&output)
                                    .unwrap_or_else(|e| format!("ERROR: {e}")),
                                Err(e) => format!("ERROR: {e}"),
                            }
                        }
                        Err(_) => {
                            let _ = crate::tools::config::clear_diagnosis_tokens();
                            "ERROR: session expired — run `nff auth login` to re-authenticate"
                                .into()
                        }
                    }
                }
                Err(e) => format!("ERROR: {e}"),
            }
        })
        .join()
        .unwrap_or_else(|_| "ERROR: repair thread panicked".into())
    }

    #[tool(description = "Return a minimal diagram.json for the given board FQBN as a pretty-printed JSON string")]
    fn wokwi_get_diagram(&self, Parameters(p): Parameters<BoardParam>) -> String {
        match crate::tools::wokwi::generate_diagram(&p.board) {
            Ok(d) => serde_json::to_string_pretty(&d).unwrap_or_else(|e| format!("ERROR: {e}")),
            Err(e) => format!("ERROR: {e}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flash_params_full() {
        let p: FlashParams = serde_json::from_str(
            r#"{"code":"void setup(){}","board":"arduino:avr:uno","port":"COM3"}"#,
        )
        .unwrap();
        assert_eq!(p.code, Some("void setup(){}".into()));
        assert_eq!(p.board, Some("arduino:avr:uno".into()));
        assert_eq!(p.port, Some("COM3".into()));
    }

    #[test]
    fn flash_params_accepts_sketch_path() {
        let p: FlashParams =
            serde_json::from_str(r#"{"sketch":"sketches/blink_esp32"}"#).unwrap();
        assert_eq!(p.sketch, Some("sketches/blink_esp32".into()));
        assert!(p.code.is_none());
    }

    #[test]
    fn flash_params_optional_fields_absent() {
        let p: FlashParams = serde_json::from_str(r#"{"code":"void setup(){}"}"#).unwrap();
        assert!(p.board.is_none());
        assert!(p.port.is_none());
        assert!(p.sketch.is_none());
    }

    #[test]
    fn compile_params_parse() {
        let p: CompileParams =
            serde_json::from_str(r#"{"sketch":"x","board":"esp32:esp32:esp32"}"#).unwrap();
        assert_eq!(p.sketch, Some("x".into()));
        assert_eq!(p.board, Some("esp32:esp32:esp32".into()));
        assert!(p.code.is_none());
    }

    #[test]
    fn complete_auth_default_timeout() {
        let p: CompleteAuthParams = serde_json::from_str(r#"{}"#).unwrap();
        assert_eq!(p.timeout, 120);
    }

    #[test]
    fn serial_read_defaults() {
        let p: SerialReadParams = serde_json::from_str(r#"{}"#).unwrap();
        assert_eq!(p.duration_ms, 3000);
        assert!(p.port.is_none());
        assert!(p.baud.is_none());
    }

    #[test]
    fn serial_read_explicit() {
        let p: SerialReadParams =
            serde_json::from_str(r#"{"duration_ms":5000,"port":"COM1","baud":115200}"#).unwrap();
        assert_eq!(p.duration_ms, 5000);
        assert_eq!(p.port, Some("COM1".into()));
        assert_eq!(p.baud, Some(115200));
    }

    #[test]
    fn wokwi_flash_defaults() {
        let p: WokwiFlashParams = serde_json::from_str(r#"{"code":"sketch"}"#).unwrap();
        assert_eq!(p.timeout_ms, 5000);
        assert!(p.board.is_none());
    }

    #[test]
    fn wokwi_serial_read_defaults() {
        let p: WokwiSerialReadParams = serde_json::from_str(r#"{"code":"sketch"}"#).unwrap();
        assert_eq!(p.duration_ms, 3000);
        assert!(p.board.is_none());
    }

    #[test]
    fn board_param_required() {
        assert!(serde_json::from_str::<BoardParam>(r#"{}"#).is_err());
        let p: BoardParam =
            serde_json::from_str(r#"{"board":"arduino:avr:uno"}"#).unwrap();
        assert_eq!(p.board, "arduino:avr:uno");
    }

    #[test]
    fn resolve_fqbn_explicit() {
        let result = resolve_fqbn(Some("arduino:avr:uno".into()));
        assert_eq!(result.unwrap(), "arduino:avr:uno");
    }

    #[test]
    fn resolve_fqbn_empty_string_is_error() {
        let result = resolve_fqbn(Some("".into()));
        assert!(result.is_err(), "empty string should be treated as missing");
    }
}

#[tool_handler]
impl ServerHandler for NffServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new("nff", env!("CARGO_PKG_VERSION")))
            .with_instructions(
                "nff MCP server — all tools require HTTP Bearer authentication. \
                Use `nff auth login` to obtain a token, then pass it as \
                Authorization: Bearer <token> on every request.",
            )
    }
}

pub async fn run(bind: &str) -> anyhow::Result<()> {
    use axum::{
        middleware,
        routing::{get, post},
        Router,
    };
    use rmcp::transport::streamable_http_server::{
        session::local::LocalSessionManager, StreamableHttpService, StreamableHttpServerConfig,
    };

    let oauth = Arc::new(OAuthState {
        base: format!("http://{bind}"),
        sessions: Mutex::new(HashMap::new()),
        auth_codes: Mutex::new(HashMap::new()),
    });

    // Shared across all sessions so authenticate()/complete_authentication() agree.
    let pending_auth: Arc<Mutex<Option<TcpListener>>> = Arc::new(Mutex::new(None));
    let service = StreamableHttpService::new(
        move || Ok(NffServer { pending_auth: pending_auth.clone() }),
        Arc::<LocalSessionManager>::default(),
        StreamableHttpServerConfig::default(),
    );

    // Bearer guard scoped to /mcp only — the OAuth/well-known routes must be open.
    let mcp_router = Router::new()
        .nest_service("/mcp", service)
        .layer(middleware::from_fn_with_state(oauth.clone(), bearer_auth));

    let app = Router::new()
        .route("/.well-known/oauth-protected-resource", get(wk_resource))
        .route("/.well-known/oauth-authorization-server", get(wk_authorization_server))
        .route("/oauth/register", post(oauth_register))
        .route("/oauth/authorize", get(oauth_authorize))
        .route("/oauth/callback/{session_id}", get(oauth_callback))
        .route("/oauth/token", post(oauth_token))
        .merge(mcp_router)
        .layer(Extension(oauth));

    let listener = tokio::net::TcpListener::bind(bind).await?;
    eprintln!("nff MCP server listening on http://{bind}/mcp");
    axum::serve(listener, app).await?;
    Ok(())
}
