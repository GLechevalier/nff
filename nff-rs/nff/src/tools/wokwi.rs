use std::path::{Path, PathBuf};
use thiserror::Error;

use crate::tools::{config, toolchain};

#[derive(Error, Debug)]
pub enum WokwiError {
    #[error("Unsupported board for Wokwi simulation: '{0}'. Supported: arduino:avr:uno, arduino:avr:mega, arduino:avr:nano, arduino:avr:leonardo, esp32:esp32:esp32, esp8266:esp8266:generic")]
    UnsupportedBoard(String),
    #[error("wokwi-cli not found. Install from https://github.com/wokwi/wokwi-cli")]
    CliNotFound,
    #[error("Simulation failed: {0}")]
    RunFailed(String),
    #[error("{0}")]
    Io(#[from] std::io::Error),
}

const FQBN_TO_CHIP: &[(&str, &str)] = &[
    ("arduino:avr:uno",         "wokwi-arduino-uno"),
    ("arduino:avr:mega",        "wokwi-arduino-mega"),
    ("arduino:avr:nano",        "wokwi-arduino-nano"),
    ("arduino:avr:leonardo",    "wokwi-arduino-leonardo"),
    ("esp32:esp32:esp32",       "wokwi-esp32-devkit-v1"),
    ("esp8266:esp8266:generic", "wokwi-esp8266"),
];

pub struct WokwiResult {
    pub serial_output: String,
    pub exit_code: i32,
}

pub fn resolve_token() -> Option<String> {
    std::env::var("WOKWI_CLI_TOKEN")
        .ok()
        .filter(|t| !t.is_empty())
        .or_else(|| config::get_wokwi_config().ok().and_then(|c| c.api_token))
}

pub fn generate_diagram(fqbn: &str) -> Result<serde_json::Value, WokwiError> {
    let chip = FQBN_TO_CHIP
        .iter()
        .find(|(f, _)| *f == fqbn)
        .map(|(_, c)| *c)
        .ok_or_else(|| WokwiError::UnsupportedBoard(fqbn.to_string()))?;

    let part_id = fqbn.rsplit(':').next().unwrap_or("board").to_string() + "1";

    Ok(serde_json::json!({
        "version": 1,
        "author": "nff",
        "editor": "wokwi",
        "parts": [{
            "type": chip,
            "id": part_id,
            "top": 0,
            "left": 0,
            "attrs": {},
        }],
        "connections": [],
    }))
}

pub fn write_wokwi_toml(project_dir: &Path, elf_path: &Path) -> Result<PathBuf, WokwiError> {
    let elf_str = elf_path.to_string_lossy().replace('\\', "/");
    let content = format!("[wokwi]\nversion = 1\nelf = \"{elf_str}\"\nfirmware = \"\"\n");
    let toml_path = project_dir.join("wokwi.toml");
    std::fs::write(&toml_path, content)?;
    Ok(toml_path)
}

pub fn run_simulation(project_dir: &Path, timeout_ms: u32) -> Result<WokwiResult, WokwiError> {
    let wokwi_cli = toolchain::find_wokwi_cli().ok_or(WokwiError::CliNotFound)?;

    let mut cmd = std::process::Command::new(&wokwi_cli);
    cmd.args(["run", &project_dir.to_string_lossy(), "--timeout", &timeout_ms.to_string()]);

    if let Some(token) = resolve_token() {
        cmd.env("WOKWI_CLI_TOKEN", token);
    }

    let output = cmd
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::inherit())
        .output()
        .map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                WokwiError::CliNotFound
            } else {
                WokwiError::RunFailed(e.to_string())
            }
        })?;

    Ok(WokwiResult {
        serial_output: String::from_utf8_lossy(&output.stdout).into_owned(),
        exit_code: output.status.code().unwrap_or(1),
    })
}
