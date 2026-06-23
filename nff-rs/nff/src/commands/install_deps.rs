use crate::cli::InstallDepsArgs;
use crate::tools::{installer, pio};
use anyhow::Result;

pub fn run(args: &InstallDepsArgs) -> Result<()> {
    // PlatformIO is the default backend — install it first (best-effort: platforms and
    // frameworks self-install on the first build, so a failure here is a warning, not
    // fatal, and arduino-cli below still installs as the opt-in alternative).
    println!("platformio  (default build backend)");
    if pio::install(&|m| println!("  {m}")) {
        if let Some(v) = pio::platformio_version() {
            println!("  ✓ {v}");
        }
    } else {
        eprintln!("  ⚠  PlatformIO install failed — install manually: pip install platformio");
    }
    println!();

    println!("arduino-cli  (optional — NFF_BUILD_BACKEND=arduino)");
    match installer::install(args.force) {
        Ok(exe) => {
            if !installer::verify(&exe) {
                eprintln!("  ✗ arduino-cli verification failed.");
                std::process::exit(1);
            }
        }
        Err(e) => {
            eprintln!("  ✗ {e}");
            std::process::exit(1);
        }
    }

    println!();

    if args.skip_wokwi {
        println!("wokwi-cli skipped (--skip-wokwi)");
    } else {
        println!("wokwi-cli  (optional — for --sim and nff wokwi)");
        // Delegate wokwi-cli install to Python (kept in Python per migration plan)
        let python = which::which("python").or_else(|_| which::which("python3"));
        match python {
            Ok(py) => {
                let status = std::process::Command::new(&py)
                    .args(["-m", "nff", "install-deps", "--skip-wokwi"])
                    .status();
                match status {
                    Ok(s) if !s.success() => {
                        eprintln!("  ⚠  wokwi-cli install exited non-zero — install manually: npm install -g @wokwi/cli");
                    }
                    Err(e) => {
                        eprintln!("  ⚠  Could not run Python to install wokwi-cli: {e}");
                    }
                    _ => {}
                }
            }
            Err(_) => {
                eprintln!(
                    "  ⚠  Python not found — install wokwi-cli manually: npm install -g @wokwi/cli"
                );
            }
        }
    }

    Ok(())
}
