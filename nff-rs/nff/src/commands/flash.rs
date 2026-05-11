use crate::cli::FlashArgs;
use crate::tools::{config, toolchain, wokwi};
use anyhow::{bail, Result};
use std::io::{self, BufRead};
use std::path::Path;

pub fn run(args: &FlashArgs) -> Result<()> {
    let file = &args.file;

    if !file.exists() {
        bail!("Path does not exist: {}", file.display());
    }

    // Resolve FQBN
    let device_cfg = config::get_default_device().unwrap_or_default();
    let fqbn = args.board.clone()
        .or_else(|| device_cfg.fqbn.clone())
        .unwrap_or_default();

    if fqbn.is_empty() {
        bail!("Missing board FQBN (use --board or run nff init)");
    }

    let port = args.port.clone()
        .or_else(|| device_cfg.port.clone().filter(|p| !p.is_empty()))
        .unwrap_or_default();

    if port.is_empty() && !args.sim {
        bail!("Missing port (use --port or run nff init)");
    }

    let sketch_dir = resolve_sketch(file)?;

    if args.sim {
        println!("  {}  →  {}  [sim]", sketch_dir.file_name().unwrap_or_default().to_string_lossy(), fqbn);
        run_simulation(&sketch_dir, &fqbn, args.sim_timeout)?;
        return Ok(());
    }

    println!("  {}  →  {} on {}", sketch_dir.file_name().unwrap_or_default().to_string_lossy(), fqbn, port);

    // Compile
    let mut compile_stream = toolchain::stream_compile(&sketch_dir, &fqbn)
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    println!("\n  Compiling…");
    for line in compile_stream.run().map_err(|e| anyhow::anyhow!("{e}"))? {
        if !line.trim().is_empty() {
            println!("    {line}");
        }
    }
    if compile_stream.returncode != Some(0) {
        bail!("Compile failed (exit {:?})", compile_stream.returncode);
    }
    println!("  ✓ Compile complete");

    // Manual reset gate
    if args.manual_reset {
        eprintln!("\n  Hold the BOOT button on your board, then press Enter to start uploading…");
        let _ = io::stdin().lock().lines().next();
        println!();
    }

    // Upload
    let mut upload_stream = toolchain::stream_upload(&sketch_dir, &fqbn, &port)
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    println!("\n  Uploading…");
    for line in upload_stream.run().map_err(|e| anyhow::anyhow!("{e}"))? {
        if !line.trim().is_empty() {
            println!("    {line}");
        }
    }
    if upload_stream.returncode != Some(0) {
        bail!("Upload failed (exit {:?})", upload_stream.returncode);
    }
    println!("  ✓ Upload complete");

    Ok(())
}

fn resolve_sketch(path: &Path) -> Result<std::path::PathBuf> {
    if path.is_dir() {
        let inos: Vec<_> = std::fs::read_dir(path)?
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map(|x| x == "ino").unwrap_or(false))
            .collect();
        if inos.is_empty() {
            bail!("No .ino file found in {}", path.display());
        }
        return Ok(path.to_path_buf());
    }

    if path.extension().map(|e| e != "ino").unwrap_or(true) {
        bail!("Expected a .ino file or sketch directory, got: {}", path.file_name().unwrap_or_default().to_string_lossy());
    }

    // If already inside a correctly-named sketch dir, use parent
    if path.parent().and_then(|p| p.file_name()) == path.file_stem().map(|s| s) {
        return Ok(path.parent().unwrap().to_path_buf());
    }

    // Loose .ino — write to temp sketch dir
    println!("  Copying {} → temp sketch dir (multi-file sketches need a directory)", path.file_name().unwrap_or_default().to_string_lossy());
    let code = std::fs::read_to_string(path)?;
    toolchain::write_sketch(&code, None).map_err(|e| anyhow::anyhow!("{e}"))
}

fn run_simulation(sketch_dir: &Path, fqbn: &str, timeout_ms: u32) -> Result<()> {
    println!("  Compiling…");
    let mut compile_stream = toolchain::stream_compile(sketch_dir, fqbn)
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    for line in compile_stream.run().map_err(|e| anyhow::anyhow!("{e}"))? {
        if !line.trim().is_empty() {
            println!("    {line}");
        }
    }
    if compile_stream.returncode != Some(0) {
        bail!("Compile failed (exit {:?})", compile_stream.returncode);
    }
    println!("  ✓ Compile complete");

    let elf_path = toolchain::elf_path_for(sketch_dir, fqbn);

    let diagram = wokwi::generate_diagram(fqbn).map_err(|e| anyhow::anyhow!("{e}"))?;
    std::fs::write(
        sketch_dir.join("diagram.json"),
        serde_json::to_string_pretty(&diagram)?,
    )?;
    wokwi::write_wokwi_toml(sketch_dir, &elf_path).map_err(|e| anyhow::anyhow!("{e}"))?;

    println!("  Simulating…  (timeout: {timeout_ms} ms)");
    let result = wokwi::run_simulation(sketch_dir, timeout_ms).map_err(|e| anyhow::anyhow!("{e}"))?;

    for line in result.serial_output.lines() {
        println!("    {line}");
    }

    if result.exit_code == 0 {
        println!("  ✓ Simulation complete");
    } else {
        bail!("Simulation exited with code {}", result.exit_code);
    }

    Ok(())
}
