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
    Mcp,
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
