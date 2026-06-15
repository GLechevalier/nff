use std::collections::BTreeMap;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use thiserror::Error;
use which::which;

#[derive(Error, Debug)]
pub enum ToolchainError {
    #[error("Executable not found: {0}")]
    NotFound(String),
    #[error("Command timed out: {0}")]
    #[allow(dead_code)]
    Timeout(String),
    #[error("{0}")]
    Invalid(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

#[derive(Debug)]
pub struct RunResult {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
    pub returncode: i32,
}

impl RunResult {
    pub fn output(&self) -> String {
        let mut parts = Vec::new();
        let s = self.stdout.trim();
        let e = self.stderr.trim();
        if !s.is_empty() { parts.push(s); }
        if !e.is_empty() { parts.push(e); }
        parts.join("\n")
    }
}

pub fn find_arduino_cli() -> Option<PathBuf> {
    if let Ok(p) = which("arduino-cli") {
        return Some(p);
    }
    #[cfg(windows)]
    {
        let base = std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| dirs::home_dir().unwrap_or_default().join("AppData").join("Local"));
        let candidate = base.join("Programs").join("arduino-cli").join("arduino-cli.exe");
        if candidate.exists() {
            return Some(candidate);
        }
    }
    #[cfg(not(windows))]
    {
        let candidate = dirs::home_dir()?.join(".local").join("bin").join("arduino-cli");
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

pub fn find_esptool() -> Option<PathBuf> {
    which("esptool.py").or_else(|_| which("esptool")).ok()
}

pub fn find_wokwi_cli() -> Option<PathBuf> {
    if let Ok(p) = which("wokwi-cli") {
        return Some(p);
    }
    #[cfg(windows)]
    {
        let base = std::env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| dirs::home_dir().unwrap_or_default().join("AppData").join("Local"));
        let candidate = base.join("Programs").join("wokwi-cli").join("wokwi-cli.exe");
        if candidate.exists() {
            return Some(candidate);
        }
    }
    #[cfg(not(windows))]
    {
        let candidate = dirs::home_dir()?.join(".local").join("bin").join("wokwi-cli");
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

pub fn arduino_cli_version() -> Option<String> {
    let exe = find_arduino_cli()?;
    let out = Command::new(&exe).arg("version").output().ok()?;
    let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

pub fn wokwi_cli_version() -> Option<String> {
    let exe = find_wokwi_cli()?;
    let out = Command::new(&exe).arg("--version").output().ok()?;
    let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

pub fn esptool_version() -> Option<String> {
    // Try standalone esptool first
    if let Some(exe) = find_esptool() {
        if let Ok(out) = Command::new(&exe).arg("version").output() {
            if out.status.success() {
                let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !s.is_empty() { return Some(s); }
            }
        }
    }
    // Fallback: python -m esptool
    let python = which("python").or_else(|_| which("python3")).ok()?;
    let out = Command::new(&python).args(["-m", "esptool", "version"]).output().ok()?;
    if out.status.success() {
        let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
        if !s.is_empty() { return Some(s); }
    }
    None
}

fn sketch_dir() -> PathBuf {
    std::env::temp_dir().join("nff_sketch")
}

pub fn write_sketch(code: &str, sketch_dir_opt: Option<&Path>) -> Result<PathBuf, ToolchainError> {
    let target = sketch_dir_opt
        .map(Path::to_path_buf)
        .unwrap_or_else(sketch_dir);
    std::fs::create_dir_all(&target)?;
    let name = target.file_name().unwrap_or_default().to_string_lossy();
    let ino = target.join(format!("{name}.ino"));
    std::fs::write(&ino, code)?;
    Ok(target)
}

pub fn elf_path_for(sketch_dir: &Path, fqbn: &str) -> PathBuf {
    let fqbn_dir = fqbn.replace(':', ".");
    let name = sketch_dir.file_name().unwrap_or_default().to_string_lossy();
    sketch_dir.join("build").join(&fqbn_dir).join(format!("{name}.ino.elf"))
}

fn require_arduino_cli() -> Result<PathBuf, ToolchainError> {
    find_arduino_cli().ok_or_else(|| ToolchainError::NotFound(
        "arduino-cli not found. Install from https://arduino.github.io/arduino-cli".into(),
    ))
}

/// Return the path to the compiled ELF, handling arduino-cli's content-hash cache.
///
/// arduino-cli >=1.4 only copies artifacts to `--output-dir` on a cache miss.
/// On cache hits the ELF lives in `%LOCALAPPDATA%/arduino/sketches/<HASH>/`.
/// We find it by re-running `compile --json` (instant cache hit) and reading
/// `builder_result.build_path` from the JSON output.
pub fn locate_compiled_elf(sketch_dir: &Path, fqbn: &str) -> Result<PathBuf, ToolchainError> {
    let expected = elf_path_for(sketch_dir, fqbn);
    if expected.is_file() {
        return Ok(expected);
    }
    let exe = require_arduino_cli()?;
    let name = sketch_dir.file_name().unwrap_or_default().to_string_lossy().into_owned();
    let out = Command::new(&exe)
        .args(["compile", "--fqbn", fqbn, "--json",
               sketch_dir.to_str().unwrap_or("")])
        .output()?;
    let json: serde_json::Value = serde_json::from_slice(&out.stdout).unwrap_or_default();
    let build_path = json["builder_result"]["build_path"]
        .as_str()
        .ok_or_else(|| ToolchainError::NotFound(format!(
            "ELF not at {} and arduino-cli --json gave no build_path",
            expected.display()
        )))?;
    let elf = PathBuf::from(build_path).join(format!("{name}.ino.elf"));
    if elf.is_file() {
        Ok(elf)
    } else {
        Err(ToolchainError::NotFound(format!(
            "ELF not found (tried {} and {})",
            expected.display(), elf.display()
        )))
    }
}

fn run(cmd: &[&str]) -> Result<RunResult, ToolchainError> {
    let output = Command::new(cmd[0])
        .args(&cmd[1..])
        .output()
        .map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                ToolchainError::NotFound(cmd[0].to_string())
            } else {
                ToolchainError::Io(e)
            }
        })?;
    Ok(RunResult {
        success: output.status.success(),
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        returncode: output.status.code().unwrap_or(-1),
    })
}

/// arduino-cli `--build-property` value that bakes the fqbn into the firmware as
/// `NFF_FQBN_TOKEN`. The nff SDK stringifies it into its heartbeat so a device
/// reports exactly what it was built as. Passed as a bare (unquoted) token to
/// avoid cross-shell quoting of the colons in an fqbn; `compiler.cpp.extra_flags`
/// is the conventional empty user-flag slot, so overriding it clobbers nothing.
fn fqbn_build_property(fqbn: &str) -> String {
    format!("compiler.cpp.extra_flags=-DNFF_FQBN_TOKEN={fqbn}")
}

pub fn compile_sketch(sketch_dir: &Path, fqbn: &str) -> Result<RunResult, ToolchainError> {
    let exe = require_arduino_cli()?;
    let output_dir = elf_path_for(sketch_dir, fqbn)
        .parent()
        .unwrap()
        .to_path_buf();
    std::fs::create_dir_all(&output_dir)?;
    let build_prop = fqbn_build_property(fqbn);
    let cmd_strs = [
        exe.to_str().unwrap_or("arduino-cli"),
        "compile",
        "--fqbn", fqbn,
        "--build-property", &build_prop,
        "--output-dir", output_dir.to_str().unwrap_or(""),
        sketch_dir.to_str().unwrap_or(""),
    ];
    run(&cmd_strs)
}

pub fn upload_sketch(sketch_dir: &Path, fqbn: &str, port: &str) -> Result<RunResult, ToolchainError> {
    let exe = require_arduino_cli()?;
    let cmd_strs = [
        exe.to_str().unwrap_or("arduino-cli"),
        "upload",
        "--fqbn", fqbn,
        "--port", port,
        sketch_dir.to_str().unwrap_or(""),
    ];
    run(&cmd_strs)
}

pub struct ProcessStream {
    cmd: Vec<String>,
    pub returncode: Option<i32>,
}

impl ProcessStream {
    pub fn new(cmd: Vec<String>) -> Self {
        ProcessStream { cmd, returncode: None }
    }

    pub fn run(&mut self) -> Result<impl Iterator<Item = String> + '_, ToolchainError> {
        let mut child = Command::new(&self.cmd[0])
            .args(&self.cmd[1..])
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| {
                if e.kind() == std::io::ErrorKind::NotFound {
                    ToolchainError::NotFound(self.cmd[0].clone())
                } else {
                    ToolchainError::Io(e)
                }
            })?;

        let stdout = child.stdout.take().unwrap();
        let lines: Vec<String> = BufReader::new(stdout)
            .lines()
            .map_while(Result::ok)
            .collect();
        let status = child.wait()?;
        self.returncode = status.code();
        Ok(lines.into_iter())
    }
}

pub fn stream_compile(sketch_dir: &Path, fqbn: &str) -> Result<ProcessStream, ToolchainError> {
    let exe = require_arduino_cli()?;
    let output_dir = elf_path_for(sketch_dir, fqbn)
        .parent()
        .unwrap()
        .to_path_buf();
    std::fs::create_dir_all(&output_dir)?;
    Ok(ProcessStream::new(vec![
        exe.to_str().unwrap_or("arduino-cli").to_string(),
        "compile".into(),
        "--fqbn".into(), fqbn.into(),
        "--build-property".into(), fqbn_build_property(fqbn),
        "--output-dir".into(), output_dir.to_str().unwrap_or("").to_string(),
        sketch_dir.to_str().unwrap_or("").to_string(),
    ]))
}

pub fn stream_upload(sketch_dir: &Path, fqbn: &str, port: &str) -> Result<ProcessStream, ToolchainError> {
    let exe = require_arduino_cli()?;
    let input_dir = elf_path_for(sketch_dir, fqbn)
        .parent()
        .unwrap()
        .to_path_buf();
    Ok(ProcessStream::new(vec![
        exe.to_str().unwrap_or("arduino-cli").to_string(),
        "upload".into(),
        "--fqbn".into(), fqbn.into(),
        "--port".into(), port.into(),
        "--input-dir".into(), input_dir.to_str().unwrap_or("").to_string(),
        sketch_dir.to_str().unwrap_or("").to_string(),
    ]))
}

/// Compile + upload from raw code. Retained as a thin shim over `flash_sketch`
/// for API parity with the Python `toolchain.flash`; the MCP tool uses
/// `flash_sketch` directly so it can also take a sketch path.
#[allow(dead_code)]
pub fn flash(code: &str, fqbn: &str, port: &str) -> String {
    let target_dir = match write_sketch(code, None) {
        Ok(d) => d,
        Err(e) => return format!("ERROR: Could not write sketch: {e}"),
    };
    flash_sketch(&target_dir, fqbn, port)
}

/// Compile then upload an already-resolved sketch directory. Used by the `flash`
/// MCP tool so it can accept a sketch path, not just raw code.
pub fn flash_sketch(target_dir: &Path, fqbn: &str, port: &str) -> String {
    let compile_result = match compile_sketch(target_dir, fqbn) {
        Ok(r) => r,
        Err(e) => return format!("ERROR: {e}"),
    };

    if !compile_result.success {
        return format!(
            "ERROR: Compile failed (exit {}):\n{}",
            compile_result.returncode,
            compile_result.output()
        );
    }

    let upload_result = match upload_sketch(target_dir, fqbn, port) {
        Ok(r) => r,
        Err(e) => return format!("ERROR: {e}"),
    };

    if !upload_result.success {
        return format!(
            "ERROR: Upload failed (exit {}):\n{}",
            upload_result.returncode,
            upload_result.output()
        );
    }

    let mut sections = vec!["OK: flash complete".to_string()];
    let co = compile_result.output();
    if !co.is_empty() { sections.push(format!("--- compile ---\n{co}")); }
    let uo = upload_result.output();
    if !uo.is_empty() { sections.push(format!("--- upload ---\n{uo}")); }
    sections.join("\n")
}

// ---------------------------------------------------------------------------
// Port-free structured compile (mirrors Python toolchain.compile_only)
// ---------------------------------------------------------------------------

/// Build directory arduino-cli writes into: `<sketch>/build/<fqbn-with-dots>`.
fn build_dir(sketch_dir: &Path, fqbn: &str) -> PathBuf {
    sketch_dir.join("build").join(fqbn.replace(':', "."))
}

/// kind → filename suffix, in flash-priority order for the `image` pick.
const ARTIFACT_SUFFIXES: &[(&str, &str)] = &[
    ("elf", ".ino.elf"),
    ("merged_bin", ".ino.merged.bin"),
    ("bin", ".ino.bin"),
    ("hex", ".ino.hex"),
    ("partitions_bin", ".ino.partitions.bin"),
    ("bootloader_bin", ".ino.bootloader.bin"),
];

/// Structured result of a compile-only run — never uploads. Mirrors the Python
/// `CompileResult.to_dict()` shape consumed by the `compile` MCP tool.
pub struct CompileResult {
    pub ok: bool,
    pub fqbn: String,
    #[allow(dead_code)]
    pub sketch_dir: PathBuf,
    #[allow(dead_code)]
    pub returncode: i32,
    pub output: String,
    pub artifacts: BTreeMap<String, PathBuf>,
}

impl CompileResult {
    pub fn elf(&self) -> Option<&PathBuf> {
        self.artifacts.get("elf")
    }

    /// Best image to flash, preferring a merged binary over a bare bin/hex.
    pub fn image(&self) -> Option<&PathBuf> {
        ["merged_bin", "bin", "hex"]
            .iter()
            .find_map(|k| self.artifacts.get(*k))
    }

    pub fn errors(&self) -> Vec<String> {
        self.output
            .lines()
            .filter(|l| l.contains("error:"))
            .map(|l| l.to_string())
            .collect()
    }

    pub fn to_json(&self) -> serde_json::Value {
        let artifacts: serde_json::Map<String, serde_json::Value> = self
            .artifacts
            .iter()
            .map(|(k, v)| (k.clone(), serde_json::Value::String(v.display().to_string())))
            .collect();
        serde_json::json!({
            "ok": self.ok,
            "fqbn": self.fqbn,
            "elf": self.elf().map(|p| p.display().to_string()),
            "image": self.image().map(|p| p.display().to_string()),
            "artifacts": artifacts,
            "errors": self.errors(),
            "output": self.output,
        })
    }
}

/// First file under `root` whose name ends with `ext` (recursive; rglob fallback).
fn find_by_ext(root: &Path, ext: &str) -> Option<PathBuf> {
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else { continue };
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
            } else if path
                .file_name()
                .and_then(|n| n.to_str())
                .map(|n| n.ends_with(ext))
                .unwrap_or(false)
            {
                return Some(path);
            }
        }
    }
    None
}

/// Map artifact kind → absolute path for whatever the compile produced. Looks at
/// the deterministic build dir first, then falls back to a recursive scan so a
/// stray build layout still resolves instead of returning nothing.
pub fn discover_artifacts(sketch_dir: &Path, fqbn: &str) -> BTreeMap<String, PathBuf> {
    let bdir = build_dir(sketch_dir, fqbn);
    let name = sketch_dir.file_name().unwrap_or_default().to_string_lossy().into_owned();
    let mut found: BTreeMap<String, PathBuf> = BTreeMap::new();
    for (kind, suffix) in ARTIFACT_SUFFIXES {
        let candidate = bdir.join(format!("{name}{suffix}"));
        if candidate.is_file() {
            found.insert((*kind).to_string(), candidate);
        }
    }
    if !found.contains_key("elf") {
        if let Some(p) = find_by_ext(sketch_dir, ".elf") {
            found.insert("elf".into(), p);
        }
    }
    if !found.contains_key("merged_bin")
        && !found.contains_key("bin")
        && !found.contains_key("hex")
    {
        for (ext, kind) in [(".merged.bin", "merged_bin"), (".bin", "bin"), (".hex", "hex")] {
            if let Some(p) = find_by_ext(sketch_dir, ext) {
                found.insert(kind.into(), p);
                break;
            }
        }
    }
    found
}

/// Normalize raw code, a `.ino` file, or a sketch folder into a sketch directory
/// arduino-cli will accept (folder name must match the `.ino` stem).
pub fn resolve_sketch_dir(
    code: Option<&str>,
    source: Option<&Path>,
) -> Result<PathBuf, ToolchainError> {
    if let Some(src) = source {
        if src.is_dir() {
            return Ok(src.to_path_buf());
        }
        if src.is_file() && src.extension().and_then(|e| e.to_str()) == Some("ino") {
            let stem = src.file_stem().and_then(|s| s.to_str()).unwrap_or_default();
            let parent_name = src
                .parent()
                .and_then(|p| p.file_name())
                .and_then(|n| n.to_str())
                .unwrap_or_default();
            if parent_name == stem {
                return Ok(src.parent().unwrap().to_path_buf());
            }
            // Loose .ino: copy into a properly-named sketch folder under temp.
            let dest = std::env::temp_dir().join(format!("nff_sketch_{stem}"));
            std::fs::create_dir_all(&dest)?;
            let contents = std::fs::read_to_string(src)?;
            std::fs::write(dest.join(format!("{stem}.ino")), contents)?;
            return Ok(dest);
        }
        return Err(ToolchainError::Invalid(format!(
            "Not a sketch file or directory: {}",
            src.display()
        )));
    }
    if let Some(code) = code {
        return write_sketch(code, None);
    }
    Err(ToolchainError::Invalid(
        "provide either code or a .ino file / sketch folder".into(),
    ))
}

/// Compile into the deterministic `--build-path` so artifacts are always present
/// (unlike `--output-dir`, which arduino-cli only populates on a cache miss).
fn compile_to_build_path(sketch_dir: &Path, fqbn: &str) -> Result<RunResult, ToolchainError> {
    let exe = require_arduino_cli()?;
    let bdir = build_dir(sketch_dir, fqbn);
    std::fs::create_dir_all(&bdir)?;
    let build_prop = fqbn_build_property(fqbn);
    let cmd_strs = [
        exe.to_str().unwrap_or("arduino-cli"),
        "compile",
        "--fqbn", fqbn,
        "--build-property", &build_prop,
        "--build-path", bdir.to_str().unwrap_or(""),
        sketch_dir.to_str().unwrap_or(""),
    ];
    run(&cmd_strs)
}

/// Compile a sketch and report exactly what came out — never uploads. Accepts a
/// `.ino` file, a sketch folder (`source`) or raw `code`. Only arduino-cli /
/// sketch-resolution problems raise; callers branch on `.ok`.
pub fn compile_only(
    fqbn: &str,
    code: Option<&str>,
    source: Option<&Path>,
) -> Result<CompileResult, ToolchainError> {
    if fqbn.is_empty() {
        return Err(ToolchainError::Invalid(
            "Missing board FQBN — pass board=/--board or run `nff init`".into(),
        ));
    }
    if find_arduino_cli().is_none() {
        return Err(ToolchainError::NotFound(
            "arduino-cli not found — run `nff install-deps`".into(),
        ));
    }
    let sd = resolve_sketch_dir(code, source)?;
    let result = compile_to_build_path(&sd, fqbn)?;
    let artifacts = if result.success {
        discover_artifacts(&sd, fqbn)
    } else {
        BTreeMap::new()
    };
    Ok(CompileResult {
        ok: result.success,
        fqbn: fqbn.to_string(),
        sketch_dir: sd,
        returncode: result.returncode,
        output: result.output(),
        artifacts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn write_sketch_creates_ino_file() {
        let dir = std::env::temp_dir()
            .join(format!("nff_tc_test_{}", std::process::id()));
        let sketch_dir = write_sketch("void setup(){} void loop(){}", Some(&dir)).unwrap();
        assert_eq!(sketch_dir, dir);
        let ino_name = format!("{}.ino", dir.file_name().unwrap().to_string_lossy());
        let ino = dir.join(&ino_name);
        assert!(ino.exists(), ".ino file not created at {}", ino.display());
        let content = std::fs::read_to_string(&ino).unwrap();
        assert!(content.contains("void setup()"));
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn write_sketch_overwrites_existing_file() {
        let dir = std::env::temp_dir()
            .join(format!("nff_tc_overwrite_{}", std::process::id()));
        write_sketch("void setup(){} void loop(){}", Some(&dir)).unwrap();
        write_sketch("// second write", Some(&dir)).unwrap();
        let ino = dir.join(format!("{}.ino", dir.file_name().unwrap().to_string_lossy()));
        let content = std::fs::read_to_string(&ino).unwrap();
        assert!(content.contains("second write"), "second write should overwrite first");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn elf_path_for_uno() {
        let sketch_dir = PathBuf::from("/tmp/myblink");
        let elf = elf_path_for(&sketch_dir, "arduino:avr:uno");
        assert_eq!(
            elf,
            PathBuf::from("/tmp/myblink/build/arduino.avr.uno/myblink.ino.elf")
        );
    }

    #[test]
    fn elf_path_for_esp32() {
        let sketch_dir = PathBuf::from("/tmp/mysketch");
        let elf = elf_path_for(&sketch_dir, "esp32:esp32:esp32");
        assert_eq!(
            elf,
            PathBuf::from("/tmp/mysketch/build/esp32.esp32.esp32/mysketch.ino.elf")
        );
    }

    #[test]
    fn find_arduino_cli_does_not_panic() {
        let _ = find_arduino_cli();
    }

    #[test]
    fn find_wokwi_cli_does_not_panic() {
        let _ = find_wokwi_cli();
    }

    #[test]
    fn resolve_sketch_dir_passes_through_folder() {
        let dir = std::env::temp_dir().join(format!("nff_rsd_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let resolved = resolve_sketch_dir(None, Some(&dir)).unwrap();
        assert_eq!(resolved, dir);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn resolve_sketch_dir_writes_code() {
        let resolved = resolve_sketch_dir(Some("void setup(){} void loop(){}"), None).unwrap();
        let ino = resolved.join(format!(
            "{}.ino",
            resolved.file_name().unwrap().to_string_lossy()
        ));
        assert!(ino.exists());
    }

    #[test]
    fn resolve_sketch_dir_requires_input() {
        assert!(resolve_sketch_dir(None, None).is_err());
    }

    #[test]
    fn compile_result_image_prefers_merged_bin() {
        let mut artifacts = BTreeMap::new();
        artifacts.insert("bin".to_string(), PathBuf::from("/x/a.ino.bin"));
        artifacts.insert("merged_bin".to_string(), PathBuf::from("/x/a.ino.merged.bin"));
        let r = CompileResult {
            ok: true,
            fqbn: "esp32:esp32:esp32".into(),
            sketch_dir: PathBuf::from("/x"),
            returncode: 0,
            output: String::new(),
            artifacts,
        };
        assert_eq!(r.image().unwrap(), &PathBuf::from("/x/a.ino.merged.bin"));
    }

    #[test]
    fn compile_result_errors_filters_error_lines() {
        let r = CompileResult {
            ok: false,
            fqbn: "arduino:avr:uno".into(),
            sketch_dir: PathBuf::from("/x"),
            returncode: 1,
            output: "blink.ino:3:1: error: expected ';'\nnote: something".into(),
            artifacts: BTreeMap::new(),
        };
        let errs = r.errors();
        assert_eq!(errs.len(), 1);
        assert!(errs[0].contains("error:"));
    }

    #[test]
    #[ignore = "requires arduino-cli on PATH"]
    fn compile_sketch_blink() {
        let dir = std::env::temp_dir().join("nff_compile_blink");
        let code = r#"
void setup() { pinMode(LED_BUILTIN, OUTPUT); }
void loop() { digitalWrite(LED_BUILTIN, HIGH); delay(1000); digitalWrite(LED_BUILTIN, LOW); delay(1000); }
"#;
        let sketch_dir = write_sketch(code, Some(&dir)).unwrap();
        let result = compile_sketch(&sketch_dir, "arduino:avr:uno").unwrap();
        assert!(result.success, "compile failed:\n{}", result.output());
        std::fs::remove_dir_all(&dir).ok();
    }
}

#[allow(dead_code)]
pub fn esptool_flash(port: &str, bin_path: &Path, baud: u32, address: &str) -> String {
    let (exe, mut cmd) = if let Some(e) = find_esptool() {
        (e.to_str().unwrap_or("esptool").to_string(), vec![])
    } else {
        let python = which("python")
            .or_else(|_| which("python3"))
            .map(|p| p.to_str().unwrap_or("python").to_string())
            .unwrap_or_else(|_| "python".to_string());
        (python, vec!["-m".to_string(), "esptool".to_string()])
    };

    cmd.extend([
        "--port".to_string(), port.to_string(),
        "--baud".to_string(), baud.to_string(),
        "write_flash".to_string(),
        address.to_string(),
        bin_path.to_str().unwrap_or("").to_string(),
    ]);

    let all: Vec<&str> = std::iter::once(exe.as_str())
        .chain(cmd.iter().map(|s| s.as_str()))
        .collect();

    match run(&all) {
        Ok(r) if r.success => format!("OK: esptool flash complete\n{}", r.output()).trim().to_string(),
        Ok(r) => format!("ERROR: esptool failed (exit {}):\n{}", r.returncode, r.output()),
        Err(e) => format!("ERROR: {e}"),
    }
}
