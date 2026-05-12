use crate::cli::InstallDepsArgs;
use crate::tools::installer;
use anyhow::Result;

pub fn run(args: &InstallDepsArgs) -> Result<()> {
    println!("arduino-cli");
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
        let python = which::which("python")
            .or_else(|_| which::which("python3"));
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
                eprintln!("  ⚠  Python not found — install wokwi-cli manually: npm install -g @wokwi/cli");
            }
        }
    }

    Ok(())
}
