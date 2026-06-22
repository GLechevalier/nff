//! Fetch the nff Arduino library from GitHub and install it for arduino-cli.
//!
//! Faithful port of the Python `nff/tools/arduino_lib.py`. The nff-sdk-c repo
//! uses a nested layout (include/ + src/ + src/port/) with mutually-exclusive
//! #if-guarded port files; the Arduino CLI needs a *flat* library where the
//! ESP32 Arduino port carries a `.cpp` extension. ESP32 only — the other ports
//! are excluded by only globbing the top-level `src/`.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::tools::toolchain;

/// Default branch tarball of the nff-sdk-c repo. Override with NFF_SDK_C_URL.
const NFF_SDK_TARBALL: &str = "https://github.com/nff-io/nff-sdk-c/archive/refs/heads/main.tar.gz";

const SDK_SRC_EXTS: &[&str] = &["c", "h", "cpp"];

#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct ArduinoLibError(pub String);

impl From<std::io::Error> for ArduinoLibError {
    fn from(e: std::io::Error) -> Self {
        ArduinoLibError(e.to_string())
    }
}

fn tarball_url() -> String {
    std::env::var("NFF_SDK_C_URL").unwrap_or_else(|_| NFF_SDK_TARBALL.to_string())
}

/// Where to install the library: `<arduino user dir>/libraries/nff`. Asks
/// arduino-cli for its sketchbook dir; falls back to the platform default.
pub fn resolve_lib_dir() -> PathBuf {
    if let Some(cli) = toolchain::find_arduino_cli() {
        if let Ok(out) = Command::new(&cli)
            .args(["config", "get", "directories.user"])
            .output()
        {
            if out.status.success() {
                let user_dir = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !user_dir.is_empty() {
                    return PathBuf::from(user_dir).join("libraries").join("nff");
                }
            }
        }
    }
    dirs::home_dir()
        .unwrap_or_default()
        .join("Documents")
        .join("Arduino")
        .join("libraries")
        .join("nff")
}

fn copy(src: &Path, dst: &Path) -> Result<(), ArduinoLibError> {
    if let Some(parent) = dst.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::copy(src, dst)?;
    Ok(())
}

fn parse_version(lib_props: &Path) -> String {
    if let Ok(content) = std::fs::read_to_string(lib_props) {
        for line in content.lines() {
            if let Some(v) = line.strip_prefix("version=") {
                return v.trim().to_string();
            }
        }
    }
    "unknown".to_string()
}

/// UTC ISO-8601 timestamp without a date crate (Hinnant civil-from-days).
fn utc_iso_now() -> String {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let (h, mi, s) = ((secs % 86400) / 3600, (secs % 3600) / 60, secs % 60);
    let days = (secs / 86400) as i64;
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    format!("{y:04}-{m:02}-{d:02}T{h:02}:{mi:02}:{s:02}Z")
}

/// Transform a nff-sdk-c checkout into a flat ESP32 Arduino library at `dest`.
pub fn flatten_sdk(repo_root: &Path, dest: &Path) -> Result<(), ArduinoLibError> {
    let inc = repo_root.join("include");
    let src = repo_root.join("src");
    let port_src = src.join("port").join("nff_port_esp32_arduino.c");
    let lib_props = repo_root.join("library.properties");

    let required = [
        inc.join("nff.h"),
        inc.join("nff_port.h"),
        port_src.clone(),
        lib_props.clone(),
    ];
    let missing: Vec<String> = required
        .iter()
        .filter(|p| !p.exists())
        .map(|p| p.display().to_string())
        .collect();
    if !missing.is_empty() {
        return Err(ArduinoLibError(format!(
            "downloaded SDK is missing expected files: {}",
            missing.join(", ")
        )));
    }

    let dest_src = dest.join("src");
    // Wipe src/ so renamed/removed files never linger as stale duplicates.
    if dest_src.exists() {
        std::fs::remove_dir_all(&dest_src)?;
    }
    std::fs::create_dir_all(&dest_src)?;

    // Header: duplicated to the lib root (for <nff.h>) and src/ (recursive layout).
    copy(&inc.join("nff.h"), &dest.join("nff.h"))?;
    copy(&inc.join("nff.h"), &dest_src.join("nff.h"))?;
    copy(&inc.join("nff_port.h"), &dest_src.join("nff_port.h"))?;

    // Platform-agnostic sources + internal headers: top-level src/ only (so the
    // non-Arduino ports under src/port/ are excluded), plus the one ESP32 port.
    for entry in std::fs::read_dir(&src)? {
        let p = entry?.path();
        if p.is_file() {
            if let Some(ext) = p.extension().and_then(|e| e.to_str()) {
                if ext == "c" || ext == "h" {
                    if let Some(name) = p.file_name() {
                        copy(&p, &dest_src.join(name))?;
                    }
                }
            }
        }
    }
    // The single Arduino ESP32 port, renamed .c -> .cpp (it is C++).
    copy(&port_src, &dest_src.join("nff_port_esp32_arduino.cpp"))?;

    copy(&lib_props, &dest.join("library.properties"))?;
    let version = parse_version(&lib_props);
    let meta = format!(
        "synced_from={}\nversion={}\nsynced_at={}\nports=esp32_arduino_only\n",
        tarball_url(),
        version,
        utc_iso_now()
    );
    std::fs::write(dest.join(".nff_sync_meta"), meta)?;
    Ok(())
}

/// Download nff-sdk-c, flatten it, and install it into arduino-cli's libraries dir.
pub fn install_nff_library() -> Result<PathBuf, ArduinoLibError> {
    let url = tarball_url();
    let resp = reqwest::blocking::get(&url)
        .and_then(|r| r.error_for_status())
        .map_err(|e| ArduinoLibError(format!("could not download nff SDK: {e}")))?;
    let bytes = resp
        .bytes()
        .map_err(|e| ArduinoLibError(format!("could not read nff SDK: {e}")))?;

    let dest = resolve_lib_dir();
    let tmp = std::env::temp_dir().join(format!("nff_sdk_{}", std::process::id()));
    std::fs::create_dir_all(&tmp)?;

    let gz = flate2::read::GzDecoder::new(std::io::Cursor::new(&bytes[..]));
    let mut archive = tar::Archive::new(gz);
    archive
        .unpack(&tmp)
        .map_err(|e| ArduinoLibError(format!("could not extract nff SDK: {e}")))?;

    // GitHub archive tarballs wrap everything in one top-level dir.
    let top = std::fs::read_dir(&tmp)?
        .flatten()
        .map(|e| e.path())
        .find(|p| p.is_dir())
        .ok_or_else(|| ArduinoLibError("unexpected SDK archive layout".into()))?;

    flatten_sdk(&top, &dest)?;
    std::fs::remove_dir_all(&tmp).ok();
    Ok(dest)
}

/// Parse the installed library's `.nff_sync_meta` into a map (empty if absent).
pub fn read_sync_meta() -> HashMap<String, String> {
    let meta = resolve_lib_dir().join(".nff_sync_meta");
    let mut map = HashMap::new();
    if let Ok(content) = std::fs::read_to_string(&meta) {
        for line in content.lines() {
            if let Some((k, v)) = line.split_once('=') {
                map.insert(k.trim().to_string(), v.trim().to_string());
            }
        }
    }
    map
}

/// A local nff-sdk-c source tree, if the developer has one checked out. Honours
/// NFF_SDK_C_SRC first, then walks up from cwd for a sibling `nff-sdk-c/`.
fn detect_local_sdk_src() -> Option<PathBuf> {
    if let Ok(env) = std::env::var("NFF_SDK_C_SRC") {
        let p = PathBuf::from(&env);
        if p.join("library.properties").exists() {
            return Some(p);
        }
    }
    let cwd = std::env::current_dir().ok()?;
    let mut base: Option<&Path> = Some(cwd.as_path());
    while let Some(b) = base {
        let cand = b.join("nff-sdk-c");
        if cand.join("library.properties").exists() && cand.join("src").is_dir() {
            return Some(cand);
        }
        base = b.parent();
    }
    None
}

/// Return a human warning if a detected local nff-sdk-c source is newer than the
/// installed library, else None. Never panics. Catches the footgun where a dev
/// edits `nff-sdk-c/src` then flashes the *stale* synced library.
pub fn local_sdk_newer_than_synced() -> Option<String> {
    let src = detect_local_sdk_src()?;
    let meta = resolve_lib_dir().join(".nff_sync_meta");
    if !meta.exists() {
        return None;
    }
    src_newer_than(&src, &meta)
}

/// Pure comparison (testable): warn if the newest `.c/.h/.cpp` under `src` is
/// newer than the `meta` marker's mtime.
fn src_newer_than(src: &Path, meta: &Path) -> Option<String> {
    let synced_mtime = meta.metadata().ok()?.modified().ok()?;

    let mut newest: Option<SystemTime> = None;
    let mut stack = vec![src.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for e in entries.flatten() {
            let p = e.path();
            if p.is_dir() {
                stack.push(p);
            } else if p
                .extension()
                .and_then(|x| x.to_str())
                .map(|x| SDK_SRC_EXTS.contains(&x))
                .unwrap_or(false)
            {
                if let Ok(m) = p.metadata().and_then(|md| md.modified()) {
                    if newest.is_none_or(|n| m > n) {
                        newest = Some(m);
                    }
                }
            }
        }
    }

    match newest {
        Some(n) if n > synced_mtime => Some(format!(
            "local nff-sdk-c at {} has edits newer than the synced Arduino \
             library — run `python {}` before flashing",
            src.display(),
            src.join("tools").join("sync_arduino_lib.py").display()
        )),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sdk_tree(root: &Path) -> PathBuf {
        std::fs::create_dir_all(root.join("include")).unwrap();
        std::fs::create_dir_all(root.join("src").join("port")).unwrap();
        std::fs::write(root.join("include").join("nff.h"), "// nff.h\n").unwrap();
        std::fs::write(root.join("include").join("nff_port.h"), "// port\n").unwrap();
        std::fs::write(root.join("src").join("nff_core.c"), "// core\n").unwrap();
        std::fs::write(root.join("src").join("nff_internal.h"), "// int\n").unwrap();
        std::fs::write(
            root.join("src")
                .join("port")
                .join("nff_port_esp32_arduino.c"),
            "// esp32\n",
        )
        .unwrap();
        std::fs::write(root.join("library.properties"), "name=nff\nversion=1.2.3\n").unwrap();
        root.to_path_buf()
    }

    #[test]
    fn flatten_sdk_writes_flat_library_and_meta() {
        let base = std::env::temp_dir().join(format!("nff_al_{}", std::process::id()));
        let repo = make_sdk_tree(&base.join("repo"));
        let dest = base.join("lib");
        flatten_sdk(&repo, &dest).unwrap();

        assert!(dest.join("nff.h").exists());
        assert!(dest.join("src").join("nff.h").exists());
        assert!(dest.join("src").join("nff_core.c").exists());
        assert!(dest.join("src").join("nff_port_esp32_arduino.cpp").exists());
        assert!(!dest.join("src").join("nff_port_esp32_arduino.c").exists());

        let meta = std::fs::read_to_string(dest.join(".nff_sync_meta")).unwrap();
        assert!(meta.contains("version=1.2.3"), "meta: {meta}");
        assert!(meta.contains("synced_at="), "meta: {meta}");
        std::fs::remove_dir_all(&base).ok();
    }

    #[test]
    fn src_newer_than_warns_when_src_is_newer() {
        let base = std::env::temp_dir().join(format!("nff_al_newer_{}", std::process::id()));
        let meta = base.join(".nff_sync_meta");
        let src = base.join("nff-sdk-c");
        std::fs::create_dir_all(src.join("src")).unwrap();
        std::fs::write(&meta, "version=1\n").unwrap();
        // Make the marker old, then write a source file (mtime = now, newer).
        let old = SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(1000);
        std::fs::OpenOptions::new()
            .write(true)
            .open(&meta)
            .unwrap()
            .set_modified(old)
            .unwrap();
        std::fs::write(src.join("src").join("nff_core.c"), "// edited\n").unwrap();

        let warn = src_newer_than(&src, &meta);
        assert!(warn.is_some(), "expected a staleness warning");
        assert!(warn.unwrap().contains("newer"));
        std::fs::remove_dir_all(&base).ok();
    }

    #[test]
    fn src_newer_than_clean_when_synced_after_edit() {
        let base = std::env::temp_dir().join(format!("nff_al_clean_{}", std::process::id()));
        let meta = base.join(".nff_sync_meta");
        let src = base.join("nff-sdk-c");
        std::fs::create_dir_all(src.join("src")).unwrap();
        // Make the source old, then write a fresh marker (synced after the edit).
        std::fs::write(src.join("src").join("nff_core.c"), "// edited\n").unwrap();
        let old = SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(1000);
        std::fs::OpenOptions::new()
            .write(true)
            .open(src.join("src").join("nff_core.c"))
            .unwrap()
            .set_modified(old)
            .unwrap();
        std::fs::write(&meta, "version=1\n").unwrap();

        assert!(src_newer_than(&src, &meta).is_none());
        std::fs::remove_dir_all(&base).ok();
    }
}
