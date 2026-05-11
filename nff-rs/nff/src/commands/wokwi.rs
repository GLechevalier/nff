use crate::cli::{WokwiRunArgs, WokwiInitArgs};
use anyhow::Result;
use which::which;

fn python() -> Result<std::path::PathBuf> {
    which("python")
        .or_else(|_| which("python3"))
        .map_err(|_| anyhow::anyhow!("Python not found — install Python 3.10+ to use `nff wokwi`"))
}

pub fn run_init(args: &WokwiInitArgs) -> Result<()> {
    let py = python()?;
    let mut cmd = std::process::Command::new(&py);
    cmd.args(["-m", "nff", "wokwi", "init"]);
    if let Some(board) = &args.board {
        cmd.args(["--board", board]);
    }
    if let Some(token) = &args.token {
        cmd.args(["--token", token]);
    }
    let status = cmd.status()?;
    std::process::exit(status.code().unwrap_or(1));
}

pub fn run_run(args: &WokwiRunArgs) -> Result<()> {
    let py = python()?;
    let mut cmd = std::process::Command::new(&py);
    cmd.args(["-m", "nff", "wokwi", "run"]);
    if args.gui {
        cmd.arg("--gui");
    }
    cmd.args(["--timeout", &args.timeout.to_string()]);
    if let Some(log) = &args.serial_log {
        cmd.args(["--serial-log", log.to_str().unwrap_or("")]);
    }
    let status = cmd.status()?;
    std::process::exit(status.code().unwrap_or(1));
}
