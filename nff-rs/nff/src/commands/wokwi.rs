use crate::cli::{WokwiInitArgs, WokwiRunArgs};
use crate::tools::{config, toolchain, wokwi};
use anyhow::{bail, Context, Result};

pub fn run_init(args: &WokwiInitArgs) -> Result<()> {
    let fqbn = args
        .board
        .clone()
        .or_else(|| config::get_default_device().ok().and_then(|d| d.fqbn))
        .context("Board FQBN required. Pass --board FQBN or run `nff init` first.")?;

    let cwd = std::env::current_dir()?;

    let diagram = wokwi::generate_diagram(&fqbn)
        .with_context(|| format!("{fqbn} is not supported by Wokwi"))?;

    std::fs::write(
        cwd.join("diagram.json"),
        serde_json::to_string_pretty(&diagram)?,
    )?;
    let chip = diagram["parts"][0]["type"].as_str().unwrap_or("");
    println!("  ✓ diagram.json written  ({chip})");

    let elf_path = toolchain::elf_path_for(&cwd, &fqbn);
    wokwi::write_wokwi_toml(&cwd, &elf_path)
        .context("Failed to write wokwi.toml")?;
    println!("  ✓ wokwi.toml written  (elf: {})", elf_path.display());

    if let Some(token) = &args.token {
        config::set_wokwi_token(Some(token)).context("Failed to save Wokwi token")?;
        println!("  ✓ Wokwi API token saved to config.");
    } else if wokwi::resolve_token().is_none() {
        println!("  ⚠  No Wokwi API token found.");
        println!("    Get one at https://wokwi.com/dashboard/ci then run:");
        println!("    nff wokwi init --token YOUR_TOKEN");
    } else {
        println!("  Wokwi API token already configured.");
    }

    println!();
    println!("  Next steps:");
    println!("    1. Write your sketch in  sketches/<name>/<name>.ino");
    println!("    2. Compile + sim:        nff flash --sim sketches/<name> --board {fqbn}");
    println!("    3. Visual simulation:    nff wokwi run --gui");

    Ok(())
}

pub fn run_run(args: &WokwiRunArgs) -> Result<()> {
    let cwd = std::env::current_dir()?;
    let toml_path = cwd.join("wokwi.toml");

    if !toml_path.exists() {
        bail!(
            "wokwi.toml not found in {}\n    Run `nff wokwi init` to scaffold the project first.",
            cwd.display()
        );
    }

    if args.gui {
        let diagram = cwd.join("diagram.json");
        if !diagram.exists() {
            bail!("diagram.json not found. Run `nff wokwi init` first.");
        }
        std::process::Command::new("code")
            .args(["--reuse-window", &diagram.to_string_lossy()])
            .spawn()
            .context("'code' not found in PATH. In VS Code: Ctrl+Shift+P → 'Shell Command: Install code command in PATH'")?;
        println!("  ✓ Opened diagram.json in VS Code.");
        println!("  Use the Wokwi VS Code extension to start the simulation.");
        return Ok(());
    }

    if toolchain::find_wokwi_cli().is_none() {
        bail!("wokwi-cli not found.\n    Install from https://github.com/wokwi/wokwi-cli");
    }

    println!("  nff wokwi run  —  timeout: {} ms  —  Ctrl+C to abort", args.timeout);
    println!("{}", "─".repeat(60));

    let result = wokwi::run_simulation(&cwd, args.timeout, None).context("Simulation failed")?;

    for line in result.serial_output.lines() {
        println!("{line}");
    }

    if let Some(log_path) = &args.serial_log {
        std::fs::write(log_path, &result.serial_output)
            .with_context(|| format!("Failed to write serial log to {}", log_path.display()))?;
        println!("  ✓ Serial log written to {}", log_path.display());
    }

    println!("{}", "─".repeat(60));

    if result.exit_code == 0 {
        println!("  ✓ Simulation complete.");
    } else {
        eprintln!("  ✗ wokwi-cli exited with code {}.", result.exit_code);
        std::process::exit(result.exit_code);
    }

    Ok(())
}
