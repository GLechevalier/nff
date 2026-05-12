use crate::cli::InitArgs;
use crate::tools::{boards, config, installer, toolchain};
use anyhow::Result;
use std::io::{self, BufRead, Write};
use which::which;

const SIM_BOARDS: &[(&str, &str)] = &[
    ("arduino:avr:uno",         "Arduino Uno"),
    ("arduino:avr:mega",        "Arduino Mega 2560"),
    ("arduino:avr:nano",        "Arduino Nano"),
    ("arduino:avr:leonardo",    "Arduino Leonardo"),
    ("esp32:esp32:esp32",       "ESP32 DevKit V1"),
    ("esp8266:esp8266:generic", "ESP8266"),
];

pub fn run(args: &InitArgs) -> Result<()> {
    if args.port.is_none() {
        let mode = pick_mode()?;
        if mode == 2 {
            return run_sim_init(args.baud, args.force);
        }
    }

    ensure_arduino_cli();

    // Guard against overwriting existing config
    if config::exists() && !args.force {
        if let Ok(device) = config::get_default_device() {
            if let Some(port) = &device.port {
                if !port.is_empty() {
                    println!(
                        "Config already exists ({} on {}).\n  Pass --force to overwrite.",
                        device.board.as_deref().unwrap_or("?"),
                        port
                    );
                    return Ok(());
                }
            }
        }
    }

    // Device resolution
    if let Some(port) = &args.port {
        println!("  Using specified port {port}…");
        let device = boards::find_device(Some(port));
        if device.is_none() {
            println!("  ⚠  {port} not matched to a known board. Storing as 'Unknown'.");
            config::set_default_device(port, "Unknown", "", args.baud)?;
            write_success(port, "Unknown", None);
            return Ok(());
        }
        let device = device.unwrap();
        config::set_default_device(&device.port, &device.board, &device.fqbn, args.baud)?;
        write_success(&device.port, &device.board, Some(&device));
        return Ok(());
    }

    println!("  Scanning USB ports…");
    let devices = boards::list_devices();

    if devices.is_empty() {
        eprintln!(
            "✗ No recognised boards found.\n  Plug in a board and try again, or use --port PORT to specify one manually."
        );
        std::process::exit(1);
    }

    let device = pick_device(&devices)?;
    config::set_default_device(&device.port, &device.board, &device.fqbn, args.baud)?;
    write_success(&device.port, &device.board, Some(&device));

    Ok(())
}

fn pick_mode() -> Result<u32> {
    println!();
    println!("How would you like to develop?");
    println!("  1. Real board            Connect a physical device via USB");
    println!("  2. Simulated environment  Develop without hardware using Wokwi");
    println!();
    print!("Select mode [1]: ");
    io::stdout().flush()?;

    let line = io::stdin().lock().lines().next()
        .unwrap_or_else(|| Ok(String::new()))?;
    let trimmed = line.trim();
    if trimmed == "2" { Ok(2) } else { Ok(1) }
}

fn pick_sim_board() -> Result<String> {
    println!();
    println!("Select a target board for simulation:");
    for (i, (fqbn, name)) in SIM_BOARDS.iter().enumerate() {
        println!("  {}. {}  {}", i + 1, name, fqbn);
    }
    println!();
    print!("Select board [1]: ");
    io::stdout().flush()?;

    let line = io::stdin().lock().lines().next()
        .unwrap_or_else(|| Ok("1".to_string()))?;
    let idx: usize = line.trim().parse().unwrap_or(1);
    let idx = idx.max(1).min(SIM_BOARDS.len()) - 1;
    Ok(SIM_BOARDS[idx].0.to_string())
}

fn pick_device(devices: &[boards::DetectedDevice]) -> Result<boards::DetectedDevice> {
    if devices.len() == 1 {
        return Ok(devices[0].clone());
    }
    println!("\nMultiple boards detected:");
    for (i, d) in devices.iter().enumerate() {
        println!("  {}. {} on {}", i + 1, d.board, d.port);
    }
    print!("Select board [1]: ");
    io::stdout().flush()?;

    let line = io::stdin().lock().lines().next()
        .unwrap_or_else(|| Ok("1".to_string()))?;
    let idx: usize = line.trim().parse().unwrap_or(1);
    let idx = idx.max(1).min(devices.len()) - 1;
    Ok(devices[idx].clone())
}

fn ensure_arduino_cli() {
    if toolchain::find_arduino_cli().is_some() {
        return;
    }
    println!("  ⚠  arduino-cli not found — installing automatically…");
    match installer::install(false) {
        Ok(exe) => {
            if installer::verify(&exe) {
                println!("  ✓ arduino-cli installed.");
            } else {
                println!("  ⚠  arduino-cli installed but could not be verified. Restart your terminal if commands fail.");
            }
        }
        Err(e) => {
            println!("  ⚠  Could not auto-install arduino-cli: {e}\n  Install manually: https://arduino.github.io/arduino-cli");
        }
    }
}

fn run_sim_init(baud: u32, force: bool) -> Result<()> {
    let fqbn = pick_sim_board()?;
    ensure_arduino_cli();

    let cwd = std::env::current_dir()?;
    let toml_path = cwd.join("wokwi.toml");
    let diagram_path = cwd.join("diagram.json");

    let paths = [&toml_path, &diagram_path];
    let existing: Vec<_> = paths.iter()
        .filter(|p| p.exists())
        .collect();

    if !existing.is_empty() && !force {
        for p in &existing {
            println!("  ⚠  {} already exists.", p.file_name().unwrap_or_default().to_string_lossy());
        }
        println!("    Pass --force to overwrite.");
        std::process::exit(1);
    }

    // Find board name from SIM_BOARDS
    let board_name = SIM_BOARDS.iter()
        .find(|&&(f, _)| f == fqbn)
        .map(|&(_, n)| n)
        .unwrap_or("Unknown");

    config::set_default_device("", board_name, &fqbn, baud)?;
    println!("  ✓ Config written to {}", config::config_path().display());

    // Write wokwi.toml
    let elf_abs = toolchain::elf_path_for(&cwd, &fqbn);
    let elf_rel = elf_abs.strip_prefix(&cwd).unwrap_or(&elf_abs);
    std::fs::write(
        &toml_path,
        format!(
            "[wokwi]\nversion = 1\nelf = \"{}\"\nfirmware = \"\"\n",
            elf_rel.to_str().unwrap_or("").replace('\\', "/")
        ),
    )?;
    println!("  ✓ wokwi.toml written");

    register_mcp_claude_code();

    println!();
    println!("  Next steps:");
    println!("    1. Write your sketch  <name>.ino");
    println!("    2. Compile + sim      nff flash --sim <name>.ino --board {fqbn}");
    println!("    3. Visual sim         nff wokwi run --gui");
    println!("    4. Add components to diagram.json using the Wokwi VS Code extension");

    Ok(())
}

fn write_success(_port: &str, _board: &str, device: Option<&boards::DetectedDevice>) {
    if let Some(d) = device {
        let sim = d.wokwi_chip.as_deref().unwrap_or("no Wokwi support");
        println!(
            "  ✓ Found: {} on {} (vendor: {}, product: {})  [sim: {}]",
            d.board, d.port, d.vendor_id, d.product_id, sim
        );
    }
    println!("  ✓ Config written to {}", config::config_path().display());
    register_mcp_claude_code();
}

fn register_mcp_claude_code() {
    let claude = match which("claude") {
        Ok(p) => p,
        Err(_) => {
            println!("  `claude` CLI not found — skipping Claude Code registration.");
            println!("  To register manually: claude mcp add nff nff mcp");
            return;
        }
    };

    let nff_exe = std::env::current_exe()
        .map(|p| p.to_str().unwrap_or("nff").to_string())
        .unwrap_or_else(|_| "nff".to_string());

    let result = std::process::Command::new(&claude)
        .args(["mcp", "add", "--scope", "user", "nff", &nff_exe, "mcp"])
        .output();

    match result {
        Ok(out) if out.status.success() => {
            println!("  ✓ Registered with Claude Code CLI (claude mcp add nff nff mcp)");
        }
        _ => {
            println!("  Could not register with Claude Code CLI. Run manually: claude mcp add nff nff mcp");
        }
    }
}
