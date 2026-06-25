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

    Ok(())
}
