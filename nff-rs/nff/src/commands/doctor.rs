use crate::tools::{boards, config, toolchain};
use anyhow::Result;

struct Check {
    passed: bool,
    detail: String,
    fix: Option<String>,
    optional: bool,
}

impl Check {
    fn ok(detail: impl Into<String>) -> Self {
        Check { passed: true, detail: detail.into(), fix: None, optional: false }
    }
    fn fail(detail: impl Into<String>, fix: impl Into<String>) -> Self {
        Check { passed: false, detail: detail.into(), fix: Some(fix.into()), optional: false }
    }
    fn warn(detail: impl Into<String>, fix: impl Into<String>) -> Self {
        Check { passed: false, detail: detail.into(), fix: Some(fix.into()), optional: true }
    }
}

pub fn run() -> Result<()> {
    let checks = vec![
        check_arduino_cli(),
        check_esptool(),
        check_config(),
        check_device(),
        check_claude_desktop(),
        check_wokwi_cli(),
    ];

    let mut any_failed = false;

    for check in &checks {
        if check.passed {
            println!("  ✓ {}", check.detail);
        } else if check.optional {
            println!("  ⚠  {}", check.detail);
            if let Some(fix) = &check.fix {
                println!("    → {fix}");
            }
        } else {
            println!("  ✗ {}", check.detail);
            if let Some(fix) = &check.fix {
                println!("    → {fix}");
            }
            any_failed = true;
        }
    }

    if any_failed {
        std::process::exit(1);
    }
    Ok(())
}

fn check_arduino_cli() -> Check {
    match toolchain::arduino_cli_version() {
        Some(v) => Check::ok(format!(
            "{}  ({})",
            v,
            toolchain::find_arduino_cli().map(|p| p.display().to_string()).unwrap_or_default()
        )),
        None => Check::fail(
            "arduino-cli not found",
            "Install from https://arduino.github.io/arduino-cli",
        ),
    }
}

fn check_esptool() -> Check {
    match toolchain::esptool_version() {
        Some(v) => {
            let loc = toolchain::find_esptool()
                .map(|p| p.display().to_string())
                .unwrap_or_else(|| "python -m esptool".into());
            Check::ok(format!("{v}  ({loc})"))
        }
        None => Check::fail("esptool not found", "Run: pip install esptool"),
    }
}

fn check_config() -> Check {
    if !config::exists() {
        return Check::fail("Config not found", "Run: nff init");
    }
    match config::load() {
        Ok(_) => Check::ok(format!("Config found at {}", config::config_path().display())),
        Err(e) => Check::fail(
            format!("Config unreadable: {e}"),
            format!("Fix or delete {}", config::config_path().display()),
        ),
    }
}

fn check_device() -> Check {
    let devices = boards::list_devices();
    if devices.is_empty() {
        return Check::warn(
            "No recognised board detected",
            "Plug in a board and run `nff init`  (or use `nff flash --sim` / Wokwi tools without hardware)",
        );
    }
    let d = &devices[0];
    let sim = d.wokwi_chip.as_deref().unwrap_or("no Wokwi support");
    Check::ok(format!("Device detected: {} on {}  [sim: {}]", d.board, d.port, sim))
}

fn check_claude_desktop() -> Check {
    let cfg_path = dirs::home_dir()
        .unwrap_or_default()
        .join(".claude")
        .join("claude_desktop_config.json");

    if !cfg_path.exists() {
        return Check::fail("Claude Desktop config not found", "Run: nff init");
    }
    let raw = match std::fs::read_to_string(&cfg_path) {
        Ok(r) => r,
        Err(e) => return Check::fail(format!("Claude Desktop config unreadable: {e}"), ""),
    };
    let data: serde_json::Value = match serde_json::from_str(&raw) {
        Ok(v) => v,
        Err(e) => return Check::fail(format!("Claude Desktop config invalid JSON: {e}"), "Fix the file manually"),
    };
    if data["mcpServers"]["nff"].is_null() {
        return Check::fail("nff not registered in Claude Desktop config", "Run: nff init");
    }
    Check::ok(format!("Claude Desktop config OK  ({})", cfg_path.display()))
}

fn check_wokwi_cli() -> Check {
    match toolchain::wokwi_cli_version() {
        Some(v) => {
            let loc = toolchain::find_wokwi_cli()
                .map(|p| p.display().to_string())
                .unwrap_or_default();
            Check { passed: true, detail: format!("{v}  ({loc})"), fix: None, optional: true }
        }
        None => Check::warn(
            "wokwi-cli not found  (optional — required for --sim and nff wokwi)",
            "Install from https://github.com/wokwi/wokwi-cli",
        ),
    }
}
