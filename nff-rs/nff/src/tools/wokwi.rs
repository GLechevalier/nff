use std::path::{Path, PathBuf};
use thiserror::Error;

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn tmp_dir(suffix: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!("nff_wokwi_test_{suffix}_{}", std::process::id()));
        fs::create_dir_all(&p).unwrap();
        p
    }

    // --- generate_diagram ---

    #[test]
    fn all_supported_boards_generate_diagrams() {
        let cases = [
            ("arduino:avr:uno",         "wokwi-arduino-uno",       "uno1"),
            ("arduino:avr:mega",        "wokwi-arduino-mega",      "mega1"),
            ("arduino:avr:nano",        "wokwi-arduino-nano",      "nano1"),
            ("arduino:avr:leonardo",    "wokwi-arduino-leonardo",  "leonardo1"),
            ("esp32:esp32:esp32",       "wokwi-esp32-devkit-v1",   "esp321"),
            ("esp8266:esp8266:generic", "wokwi-esp8266",           "generic1"),
        ];
        for (fqbn, chip, part_id) in cases {
            let d = generate_diagram(fqbn)
                .unwrap_or_else(|e| panic!("generate_diagram({fqbn}) failed: {e}"));
            assert_eq!(d["version"], 1);
            assert_eq!(d["author"], "nff");
            assert_eq!(d["parts"][0]["type"], chip,   "wrong chip for {fqbn}");
            assert_eq!(d["parts"][0]["id"],   part_id, "wrong part_id for {fqbn}");
            assert_eq!(d["parts"][0]["top"],  0);
            assert_eq!(d["parts"][0]["left"], 0);
            assert!(d["connections"].as_array().unwrap().is_empty());
        }
    }

    #[test]
    fn unsupported_board_returns_error() {
        let err = generate_diagram("bad:board:fqbn").unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("Unsupported"), "error should mention 'Unsupported': {msg}");
        assert!(msg.contains("bad:board:fqbn"), "error should name the bad FQBN: {msg}");
    }

    #[test]
    fn fqbn_to_chip_covers_all_boards_in_board_map() {
        // Every FQBN that appears in boards::BOARD_MAP with a wokwi_chip should
        // also be resolvable via generate_diagram.
        use crate::tools::boards::BOARD_MAP;
        for &(_, _, _, fqbn, wokwi_chip) in BOARD_MAP {
            if let Some(chip) = wokwi_chip {
                let result = generate_diagram(fqbn);
                assert!(
                    result.is_ok(),
                    "BOARD_MAP has wokwi chip '{chip}' for {fqbn} but generate_diagram failed"
                );
                assert_eq!(result.unwrap()["parts"][0]["type"], chip);
            }
        }
    }

    // --- write_wokwi_toml ---

    #[test]
    fn write_wokwi_toml_creates_file() {
        let dir = tmp_dir("toml");
        let elf = PathBuf::from("/tmp/sketch/build/arduino.avr.uno/sketch.elf");
        let toml_path = write_wokwi_toml(&dir, &elf).unwrap();
        assert!(toml_path.exists());
        assert_eq!(toml_path.file_name().unwrap(), "wokwi.toml");
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn write_wokwi_toml_content_is_valid() {
        let dir = tmp_dir("toml_content");
        // ELF inside the project dir → written as a relative path
        let elf = dir.join("build").join("arduino.avr.uno").join("sketch.ino.elf");
        write_wokwi_toml(&dir, &elf).unwrap();
        let content = fs::read_to_string(dir.join("wokwi.toml")).unwrap();
        assert!(content.contains("[wokwi]"),     "missing [wokwi] header");
        assert!(content.contains("version = 1"), "missing version");
        assert!(content.contains("build/arduino.avr.uno/sketch.ino.elf"), "expected relative elf path");
        assert!(content.contains("firmware = \"\""), "missing firmware key");
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn write_wokwi_toml_absolute_fallback() {
        // ELF outside project dir → absolute path written as-is (with forward slashes)
        let dir = tmp_dir("toml_abs");
        let elf = PathBuf::from("/unrelated/path/sketch.elf");
        write_wokwi_toml(&dir, &elf).unwrap();
        let content = fs::read_to_string(dir.join("wokwi.toml")).unwrap();
        assert!(content.contains("/unrelated/path/sketch.elf"), "expected absolute elf path");
        fs::remove_dir_all(dir).ok();
    }

    // --- resolve_token ---

    #[test]
    fn resolve_token_reads_env_var() {
        std::env::set_var("WOKWI_CLI_TOKEN", "tok_test_abc");
        let token = resolve_token();
        std::env::remove_var("WOKWI_CLI_TOKEN");
        assert_eq!(token, Some("tok_test_abc".to_string()));
    }

    #[test]
    fn resolve_token_empty_env_is_skipped() {
        std::env::set_var("WOKWI_CLI_TOKEN", "");
        let token = resolve_token();
        std::env::remove_var("WOKWI_CLI_TOKEN");
        assert_ne!(token, Some("".to_string()), "empty env var should not be returned");
    }
}

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
    // wokwi-cli resolves the elf path relative to the project dir — strip the prefix.
    let rel = elf_path.strip_prefix(project_dir).unwrap_or(elf_path);
    let elf_str = rel.to_string_lossy().replace('\\', "/");
    let content = format!("[wokwi]\nversion = 1\nelf = \"{elf_str}\"\nfirmware = \"\"\n");
    let toml_path = project_dir.join("wokwi.toml");
    std::fs::write(&toml_path, content)?;
    Ok(toml_path)
}

/// Run the Wokwi simulator on `project_dir`.
///
/// `elf` overrides the ELF path from `wokwi.toml` via `--elf`.  Pass `None`
/// to let wokwi-cli read the path from `wokwi.toml` (used by `nff wokwi run`).
/// Pass `Some` after a fresh compile to handle arduino-cli cache-hit scenarios
/// where `--output-dir` is not populated.
pub fn run_simulation(project_dir: &Path, timeout_ms: u32, elf: Option<&Path>) -> Result<WokwiResult, WokwiError> {
    let wokwi_cli = toolchain::find_wokwi_cli().ok_or(WokwiError::CliNotFound)?;

    let mut cmd = std::process::Command::new(&wokwi_cli);
    cmd.arg("--timeout").arg(timeout_ms.to_string());
    if let Some(e) = elf {
        cmd.arg("--elf").arg(e);
    }
    cmd.arg(project_dir);

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
