use anyhow::{bail, Context, Result};
use std::env::consts::{ARCH, OS};
use std::path::PathBuf;
use std::process::Command;

const BASE: &str = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest";

fn asset_url() -> (&'static str, &'static str) {
    match (OS, ARCH) {
        ("windows", "x86_64") => ("_Windows_64bit.zip", "zip"),
        ("windows", _)        => ("_Windows_32bit.zip", "zip"),
        ("macos", "aarch64")  => ("_macOS_ARM64.tar.gz", "tar.gz"),
        ("macos", _)          => ("_macOS_64bit.tar.gz", "tar.gz"),
        ("linux", "x86_64")   => ("_Linux_64bit.tar.gz", "tar.gz"),
        ("linux", "aarch64")  => ("_Linux_ARM64.tar.gz", "tar.gz"),
        ("linux", "arm")      => ("_Linux_ARMv7.tar.gz", "tar.gz"),
        _                     => ("_Linux_64bit.tar.gz", "tar.gz"),
    }
}

fn install_dir() -> PathBuf {
    #[cfg(windows)]
    {
        let base = std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| dirs::home_dir().unwrap_or_default().join("AppData").join("Local"));
        base.join("Programs").join("arduino-cli")
    }
    #[cfg(not(windows))]
    {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".local")
            .join("bin")
    }
}

fn exe_name() -> &'static str {
    if cfg!(windows) { "arduino-cli.exe" } else { "arduino-cli" }
}

pub fn install(force: bool) -> Result<PathBuf> {
    let (suffix, ext) = asset_url();
    let url = format!("{BASE}{suffix}");
    let dir = install_dir();
    let exe_path = dir.join(exe_name());

    if exe_path.exists() && !force {
        println!("  arduino-cli already installed at {}", exe_path.display());
        return Ok(exe_path);
    }

    println!("  Platform  : {OS} {ARCH}");
    println!("  Download  : {url}");
    println!("  Install   : {}", dir.display());
    println!();

    std::fs::create_dir_all(&dir).context("creating install directory")?;

    // Download to temp file
    let tmp_dir = std::env::temp_dir();
    let archive_name = if ext == "zip" { "arduino-cli-dl.zip" } else { "arduino-cli-dl.tar.gz" };
    let archive_path = tmp_dir.join(archive_name);

    println!("  Downloading…");
    let response = reqwest::blocking::get(&url)
        .context("download failed")?;
    let bytes = response.bytes().context("reading response bytes")?;
    std::fs::write(&archive_path, &bytes).context("writing archive")?;

    println!("  Extracting… ");
    let dest = extract_binary(&archive_path, ext, &dir)?;
    println!("done");

    ensure_on_path(&dir);
    Ok(dest)
}

fn extract_binary(archive: &std::path::Path, ext: &str, dest_dir: &std::path::Path) -> Result<PathBuf> {
    let exe = exe_name();
    let dest = dest_dir.join(exe);

    if ext == "zip" {
        let file = std::fs::File::open(archive)?;
        let mut zip = zip::ZipArchive::new(file)?;
        let entry_idx = (0..zip.len())
            .find(|&i| zip.by_index(i).map(|e| e.name().ends_with(exe)).unwrap_or(false))
            .context("arduino-cli binary not found in zip")?;
        let mut entry = zip.by_index(entry_idx)?;
        let mut out = std::fs::File::create(&dest)?;
        std::io::copy(&mut entry, &mut out)?;
    } else {
        let file = std::fs::File::open(archive)?;
        let gz = flate2::read::GzDecoder::new(file);
        let mut tar = tar::Archive::new(gz);
        let mut found = false;
        for entry in tar.entries()? {
            let mut entry = entry?;
            let path = entry.path()?.to_path_buf();
            if path.file_name().map(|n| n == "arduino-cli").unwrap_or(false) {
                entry.unpack(&dest)?;
                found = true;
                break;
            }
        }
        if !found {
            bail!("arduino-cli binary not found in tar archive");
        }
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(&dest)?.permissions();
        perms.set_mode(perms.mode() | 0o111);
        std::fs::set_permissions(&dest, perms)?;
    }

    Ok(dest)
}

fn ensure_on_path(dir: &std::path::Path) {
    let dir_str = dir.to_str().unwrap_or("");

    #[cfg(windows)]
    {
        use winreg::enums::*;
        use winreg::RegKey;
        let hkcu = RegKey::predef(HKEY_CURRENT_USER);
        if let Ok(env) = hkcu.open_subkey_with_flags("Environment", KEY_READ | KEY_WRITE) {
            let current: String = env.get_value("PATH").unwrap_or_default();
            if !current.to_lowercase().contains(&dir_str.to_lowercase()) {
                let new_path = if current.is_empty() {
                    dir_str.to_string()
                } else {
                    format!("{current};{dir_str}")
                };
                let _ = env.set_value("PATH", &new_path);
                println!("  Added {dir_str} to user PATH");
            } else {
                println!("  {dir_str} already in user PATH");
            }
        }
        let current_path = std::env::var("PATH").unwrap_or_default();
        unsafe {
            std::env::set_var("PATH", format!("{current_path};{dir_str}"));
        }
    }

    #[cfg(not(windows))]
    {
        let export_line = format!("\nexport PATH=\"$PATH:{dir_str}\"");
        let candidates = [
            dirs::home_dir().unwrap_or_default().join(".bashrc"),
            dirs::home_dir().unwrap_or_default().join(".zshrc"),
            dirs::home_dir().unwrap_or_default().join(".profile"),
        ];
        for cfg in &candidates {
            if cfg.exists() {
                if let Ok(content) = std::fs::read_to_string(cfg) {
                    if !content.contains(dir_str) {
                        let _ = std::fs::write(cfg, format!("{content}{export_line}"));
                        println!("  Added PATH entry to {}", cfg.display());
                        println!("  Run: source ~/.bashrc  (or restart your terminal)");
                    } else {
                        println!("  {dir_str} already in {}", cfg.display());
                    }
                }
                let current = std::env::var("PATH").unwrap_or_default();
                unsafe { std::env::set_var("PATH", format!("{current}:{dir_str}")); }
                return;
            }
        }
        let profile = dirs::home_dir().unwrap_or_default().join(".profile");
        let _ = std::fs::write(&profile, export_line.trim_start_matches('\n'));
        println!("  Created {} with PATH export", profile.display());
        let current = std::env::var("PATH").unwrap_or_default();
        unsafe { std::env::set_var("PATH", format!("{current}:{dir_str}")); }
    }
}

pub fn verify(exe: &std::path::Path) -> bool {
    Command::new(exe)
        .arg("version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}
