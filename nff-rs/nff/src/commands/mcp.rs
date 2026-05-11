use anyhow::{Context, Result};
use which::which;

pub fn run() -> Result<()> {
    let python = which("python")
        .or_else(|_| which("python3"))
        .context("Python not found — install Python 3.10+ to use `nff mcp`")?;
    let status = std::process::Command::new(python)
        .args(["-m", "nff", "mcp"])
        .status()?;
    std::process::exit(status.code().unwrap_or(1));
}
