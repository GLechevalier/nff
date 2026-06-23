use anyhow::Result;

/// `nff clean` — remove nff build artifacts. `nff_sketch` is the arduino-cli backend's
/// temp dir; `nff_pio` is the PlatformIO backend's (each scaffold's heavy `.pio/build`
/// output lives nested inside, so one removal clears it). BYO pio projects keep their
/// own `.pio` — not nff's to delete.
pub fn run() -> Result<()> {
    let tmp = std::env::temp_dir();
    let mut removed = Vec::new();
    for name in ["nff_sketch", "nff_pio"] {
        let dir = tmp.join(name);
        if dir.exists() {
            std::fs::remove_dir_all(&dir).ok();
            removed.push(dir.display().to_string());
        }
    }
    if removed.is_empty() {
        println!("Nothing to clean.");
    } else {
        for p in removed {
            println!("Removed {p}");
        }
    }
    Ok(())
}
