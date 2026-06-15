use clap::{Args, Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "nff", version, about = "nff — Claude Code IoT Bridge\n\nConnects Claude Code to physical hardware devices via USB.\nRun `nff init` to get started.")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    Init(InitArgs),
    Compile(CompileArgs),
    Flash(FlashArgs),
    Monitor(MonitorArgs),
    Wokwi(WokwiCommand),
    Doctor,
    Clean,
    Test,
    Connect,
    Ota,
    #[command(name = "install-deps")]
    InstallDeps(InstallDepsArgs),
    Mcp(McpArgs),
    Auth(AuthCommand),
    Repair(RepairArgs),
    Provision(ProvisionCommand),
}

#[derive(Args)]
pub struct InitArgs {
    #[arg(long, value_name = "PORT", help = "Serial port to use; skips auto-detection.")]
    pub port: Option<String>,
    #[arg(long, default_value = "9600", help = "Baud rate stored in config.")]
    pub baud: u32,
    #[arg(long, help = "Overwrite an existing config without prompting.")]
    pub force: bool,
}

#[derive(Args)]
pub struct CompileArgs {
    #[arg(value_name = "FILE", help = "Path to .ino file or sketch directory. No board connection needed.")]
    pub file: PathBuf,
    #[arg(long, value_name = "FQBN", help = "Board FQBN, e.g. arduino:avr:uno. Falls back to config.")]
    pub board: Option<String>,
    #[arg(long, help = "Emit the raw JSON result instead of a human summary.")]
    pub json: bool,
}

#[derive(Args)]
pub struct FlashArgs {
    #[arg(value_name = "FILE", help = "Path to .ino file or sketch directory.")]
    pub file: PathBuf,
    #[arg(long, value_name = "FQBN", help = "Board FQBN, e.g. arduino:avr:uno. Falls back to config.")]
    pub board: Option<String>,
    #[arg(long, value_name = "PORT", help = "Serial port, e.g. COM3. Falls back to config. Not needed with --sim.")]
    pub port: Option<String>,
    #[arg(long, help = "Baud rate (stored in config, not used by arduino-cli).")]
    pub baud: Option<u32>,
    #[arg(long, help = "Pause before upload — use when auto-reset is broken.")]
    pub manual_reset: bool,
    #[arg(long, help = "Simulate with Wokwi instead of uploading to real hardware.")]
    pub sim: bool,
    #[arg(long, default_value = "5000", value_name = "MS", help = "Wokwi simulation timeout in milliseconds. Only used with --sim.")]
    pub sim_timeout: u32,
}

#[derive(Args)]
pub struct MonitorArgs {
    #[arg(long, value_name = "PORT", help = "Serial port, e.g. COM3 or /dev/ttyUSB0. Falls back to config.")]
    pub port: Option<String>,
    #[arg(long, help = "Baud rate. Falls back to config default (9600).")]
    pub baud: Option<u32>,
    #[arg(long, value_name = "SECONDS", help = "Stop after this many seconds instead of running indefinitely.")]
    pub timeout: Option<f64>,
}

#[derive(Args)]
pub struct InstallDepsArgs {
    #[arg(long, help = "Reinstall even if already present.")]
    pub force: bool,
    #[arg(long, help = "Skip wokwi-cli installation.")]
    pub skip_wokwi: bool,
}

#[derive(Args)]
pub struct WokwiCommand {
    #[command(subcommand)]
    pub sub: WokwiSubcommands,
}

#[derive(Subcommand)]
pub enum WokwiSubcommands {
    Init(WokwiInitArgs),
    Run(WokwiRunArgs),
}

#[derive(Args)]
pub struct WokwiInitArgs {
    #[arg(long, value_name = "FQBN", help = "Board FQBN override.")]
    pub board: Option<String>,
    #[arg(long, value_name = "TOKEN", help = "Wokwi CI API token.")]
    pub token: Option<String>,
}

#[derive(Args)]
pub struct WokwiRunArgs {
    #[arg(long, help = "Open animated circuit in VS Code.")]
    pub gui: bool,
    #[arg(long, default_value = "5000", value_name = "MS", help = "Simulation wall-clock timeout in milliseconds.")]
    pub timeout: u32,
    #[arg(long, value_name = "FILE", help = "Write captured serial output to this file.")]
    pub serial_log: Option<PathBuf>,
}

// ── mcp ─────────────────────────────────────────────────────────────────────

#[derive(Args)]
pub struct McpArgs {
    #[arg(long, default_value = "127.0.0.1", value_name = "ADDR", help = "Address to bind the HTTP server to.")]
    pub host: String,
    #[arg(long, default_value = "3010", value_name = "PORT", help = "Port to listen on.")]
    pub port: u16,
}

// ── auth ────────────────────────────────────────────────────────────────────

#[derive(Args)]
pub struct AuthCommand {
    #[command(subcommand)]
    pub sub: AuthSubcommands,
}

#[derive(Subcommand)]
pub enum AuthSubcommands {
    #[command(about = "Sign in to the nff diagnosis service.")]
    Login(AuthLoginArgs),
    #[command(about = "Sign out and clear saved credentials.")]
    Logout(AuthLogoutArgs),
    #[command(about = "Show current authentication status.")]
    Status,
}

#[derive(Args)]
pub struct AuthLoginArgs {
    #[arg(long, value_name = "EMAIL", help = "Email address (headless/CI login; omit to use browser).")]
    pub email: Option<String>,
    #[arg(long, value_name = "PASSWORD", help = "Password (headless/CI login; omit to use browser).")]
    pub password: Option<String>,
    #[arg(long, value_name = "URL", help = "Diagnosis server URL. Defaults to config value (https://nanoforgeflow.com).")]
    pub server: Option<String>,
}

#[derive(Args)]
pub struct AuthLogoutArgs {
    #[arg(long, value_name = "URL", help = "Diagnosis server URL. Defaults to config value.")]
    pub server: Option<String>,
}

// ── repair ──────────────────────────────────────────────────────────────────

// ── provision ─────────────────────────────────────────────────────────────

#[derive(Args)]
pub struct ProvisionCommand {
    #[command(subcommand)]
    pub sub: ProvisionSubcommands,
}

#[derive(Subcommand)]
pub enum ProvisionSubcommands {
    #[command(about = "Create one shared batch bootstrap credential and write credentials.h.")]
    Batch(BatchArgs),
}

#[derive(Args)]
pub struct BatchArgs {
    #[arg(long = "project", value_name = "UUID", help = "Target project id (uuid).")]
    pub project: String,
    #[arg(long, value_name = "N", help = "Expected batch size; the server rejects enrollments beyond this as a cloned-credential anomaly. Omit for no hard quota.")]
    pub count: Option<u32>,
    #[arg(long, value_name = "FILE", default_value = "credentials.h", help = "Where to write the shared bootstrap credentials.h.")]
    pub out: PathBuf,
    #[arg(long = "fleet-url", value_name = "URL", help = "nff-fleet base URL (or env NFF_FLEET_URL).")]
    pub fleet_url: Option<String>,
    #[arg(long, value_name = "SECRET", help = "X-Fleet-Secret (or env NFF_FLEET_SECRET).")]
    pub secret: Option<String>,
}

#[derive(Args)]
pub struct RepairArgs {
    #[arg(long, value_name = "TEXT", help = "Raw serial/crash output to diagnose. Reads from device if omitted.")]
    pub serial: Option<String>,
    #[arg(long, value_name = "MS", help = "How long to capture serial output from the device (default: 5000 ms).")]
    pub capture_ms: Option<u32>,
    #[arg(long, value_name = "PORT", help = "Serial port to read from. Falls back to config.")]
    pub port: Option<String>,
    #[arg(long, help = "Baud rate for serial capture. Falls back to config.")]
    pub baud: Option<u32>,
    #[arg(long, value_name = "ID", help = "Firmware build ID (hex hash of ELF). Enables symbol resolution when provided.")]
    pub build_id: Option<String>,
    #[arg(long, value_name = "FQBN", help = "Board FQBN hint for the diagnosis server.")]
    pub board: Option<String>,
    #[arg(long, value_name = "URL", help = "Diagnosis server URL. Defaults to config value.")]
    pub server: Option<String>,
}
