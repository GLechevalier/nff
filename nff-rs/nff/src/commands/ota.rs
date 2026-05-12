use anyhow::Result;
use which::which;

pub fn run() -> Result<()> {
    let python = which("python")
        .or_else(|_| which("python3"))
        .map_err(|_| anyhow::anyhow!("Python not found — install Python 3.10+"))?;
    let status = std::process::Command::new(&python)
        .args(["-m", "nff", "ota"])
        .status()?;
    std::process::exit(status.code().unwrap_or(1));
}
