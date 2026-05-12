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
    Timeout(String),
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
    sketch_dir.join("build").join(&fqbn_dir).join(format!("{name}.elf"))
}

fn require_arduino_cli() -> Result<PathBuf, ToolchainError> {
    find_arduino_cli().ok_or_else(|| ToolchainError::NotFound(
        "arduino-cli not found. Install from https://arduino.github.io/arduino-cli".into(),
    ))
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

pub fn compile_sketch(sketch_dir: &Path, fqbn: &str) -> Result<RunResult, ToolchainError> {
    let exe = require_arduino_cli()?;
    let build_path = elf_path_for(sketch_dir, fqbn)
        .parent()
        .unwrap()
        .to_path_buf();
    std::fs::create_dir_all(&build_path)?;
    let cmd_strs = [
        exe.to_str().unwrap_or("arduino-cli"),
        "compile",
        "--fqbn", fqbn,
        "--build-path", build_path.to_str().unwrap_or(""),
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
            .filter_map(|l| l.ok())
            .collect();
        let status = child.wait()?;
        self.returncode = status.code();
        Ok(lines.into_iter())
    }
}

pub fn stream_compile(sketch_dir: &Path, fqbn: &str) -> Result<ProcessStream, ToolchainError> {
    let exe = require_arduino_cli()?;
    let build_path = elf_path_for(sketch_dir, fqbn)
        .parent()
        .unwrap()
        .to_path_buf();
    std::fs::create_dir_all(&build_path)?;
    Ok(ProcessStream::new(vec![
        exe.to_str().unwrap_or("arduino-cli").to_string(),
        "compile".into(),
        "--fqbn".into(), fqbn.into(),
        "--build-path".into(), build_path.to_str().unwrap_or("").to_string(),
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

pub fn flash(code: &str, fqbn: &str, port: &str) -> String {
    let target_dir = match write_sketch(code, None) {
        Ok(d) => d,
        Err(e) => return format!("ERROR: Could not write sketch: {e}"),
    };

    let compile_result = match compile_sketch(&target_dir, fqbn) {
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

    let upload_result = match upload_sketch(&target_dir, fqbn, port) {
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
            PathBuf::from("/tmp/myblink/build/arduino.avr.uno/myblink.elf")
        );
    }

    #[test]
    fn elf_path_for_esp32() {
        let sketch_dir = PathBuf::from("/tmp/mysketch");
        let elf = elf_path_for(&sketch_dir, "esp32:esp32:esp32");
        assert_eq!(
            elf,
            PathBuf::from("/tmp/mysketch/build/esp32.esp32.esp32/mysketch.elf")
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
