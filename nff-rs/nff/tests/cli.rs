/// Integration tests that spawn the `nff` binary and inspect its output.
/// Run with: cargo test --test cli
use std::path::PathBuf;
use std::process::Command;

fn nff() -> PathBuf {
    // cargo puts the main binary next to (or one level above) the test binary.
    let mut path = std::env::current_exe()
        .expect("can't locate test binary")
        .parent()
        .unwrap()
        .to_path_buf();
    if path.ends_with("deps") {
        path.pop();
    }
    if cfg!(windows) { path.join("nff.exe") } else { path.join("nff") }
}

fn run(args: &[&str]) -> std::process::Output {
    Command::new(nff())
        .args(args)
        .output()
        .unwrap_or_else(|e| panic!("failed to run nff {:?}: {e}", args))
}

fn stdout(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn stderr(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stderr).into_owned()
}

// ---------------------------------------------------------------------------
// Basic invocation
// ---------------------------------------------------------------------------

#[test]
fn version_flag_exits_successfully() {
    let out = run(&["--version"]);
    assert!(out.status.success(), "nff --version failed:\n{}", stderr(&out));
}

#[test]
fn version_output_matches_cargo_version() {
    let out = run(&["--version"]);
    let text = stdout(&out);
    assert!(
        text.contains("0.2.16"),
        "version output should contain 0.2.16, got: {text}"
    );
}

#[test]
fn help_flag_exits_successfully() {
    let out = run(&["--help"]);
    assert!(out.status.success(), "nff --help failed:\n{}", stderr(&out));
}

#[test]
fn help_lists_all_top_level_commands() {
    let out = run(&["--help"]);
    let text = stdout(&out);
    for cmd in &["init", "flash", "monitor", "doctor", "clean", "install-deps", "mcp", "wokwi"] {
        assert!(text.contains(cmd), "nff --help missing command '{cmd}':\n{text}");
    }
}

#[test]
fn unknown_command_exits_nonzero() {
    let out = run(&["definitely-not-a-command"]);
    assert!(!out.status.success());
}

// ---------------------------------------------------------------------------
// doctor
// ---------------------------------------------------------------------------

#[test]
fn doctor_runs_without_panic() {
    // doctor may report missing tools but must not crash.
    let out = run(&["doctor"]);
    let combined = format!("{}{}", stdout(&out), stderr(&out));
    // Should print something (tool check results).
    assert!(!combined.trim().is_empty(), "doctor produced no output");
}

// ---------------------------------------------------------------------------
// wokwi subcommand
// ---------------------------------------------------------------------------

#[test]
fn wokwi_help_flag() {
    let out = run(&["wokwi", "--help"]);
    assert!(out.status.success());
    assert!(stdout(&out).contains("init") && stdout(&out).contains("run"));
}

#[test]
fn wokwi_init_unsupported_board_fails() {
    let tmp = std::env::temp_dir().join(format!("nff_cli_test_{}", std::process::id()));
    std::fs::create_dir_all(&tmp).unwrap();
    let out = Command::new(nff())
        .args(["wokwi", "init", "--board", "not:a:board"])
        .current_dir(&tmp)
        .output()
        .unwrap();
    assert!(!out.status.success(), "unsupported board should fail");
    let combined = format!("{}{}", stdout(&out), stderr(&out));
    assert!(
        combined.to_lowercase().contains("unsupported") || combined.to_lowercase().contains("error"),
        "should mention unsupported/error: {combined}"
    );
    std::fs::remove_dir_all(tmp).ok();
}

#[test]
fn wokwi_init_creates_diagram_and_toml() {
    let tmp = std::env::temp_dir().join(format!("nff_wokwi_init_{}", std::process::id()));
    std::fs::create_dir_all(&tmp).unwrap();

    let out = Command::new(nff())
        .args(["wokwi", "init", "--board", "arduino:avr:uno"])
        .current_dir(&tmp)
        .output()
        .unwrap();

    // Accept both success and "token missing" warning — both still write the files.
    let diagram = tmp.join("diagram.json");
    let toml    = tmp.join("wokwi.toml");

    assert!(diagram.exists(), "diagram.json not created (exit={:?}):\n{}", out.status.code(), stderr(&out));
    assert!(toml.exists(),    "wokwi.toml not created (exit={:?}):\n{}", out.status.code(), stderr(&out));

    // diagram.json must contain the wokwi-arduino-uno chip
    let diagram_content = std::fs::read_to_string(&diagram).unwrap();
    let v: serde_json::Value = serde_json::from_str(&diagram_content).unwrap();
    assert_eq!(v["parts"][0]["type"], "wokwi-arduino-uno");

    // wokwi.toml must reference the right FQBN directory
    let toml_content = std::fs::read_to_string(&toml).unwrap();
    assert!(toml_content.contains("[wokwi]"));
    assert!(toml_content.contains("arduino.avr.uno"));

    std::fs::remove_dir_all(tmp).ok();
}

#[test]
fn wokwi_run_without_toml_fails_with_clear_message() {
    let tmp = std::env::temp_dir().join(format!("nff_wokwi_run_{}", std::process::id()));
    std::fs::create_dir_all(&tmp).unwrap();

    let out = Command::new(nff())
        .args(["wokwi", "run"])
        .current_dir(&tmp)
        .output()
        .unwrap();

    assert!(!out.status.success());
    let combined = format!("{}{}", stdout(&out), stderr(&out));
    assert!(
        combined.contains("wokwi.toml"),
        "error should mention wokwi.toml: {combined}"
    );
    std::fs::remove_dir_all(tmp).ok();
}

// ---------------------------------------------------------------------------
// flash edge cases (no hardware / no arduino-cli)
// ---------------------------------------------------------------------------

#[test]
fn flash_missing_file_exits_nonzero() {
    let out = run(&["flash", "/tmp/nonexistent_sketch_xyz.ino"]);
    assert!(!out.status.success());
}

#[test]
fn flash_missing_board_exits_nonzero() {
    // Run from a temp dir with no config so FQBN is always missing.
    let tmp = std::env::temp_dir().join(format!("nff_flash_{}", std::process::id()));
    std::fs::create_dir_all(&tmp).unwrap();

    // Create a dummy .ino file so the path check passes
    let sketch_dir = tmp.join("blink");
    std::fs::create_dir_all(&sketch_dir).unwrap();
    std::fs::write(sketch_dir.join("blink.ino"), "void setup(){} void loop(){}").unwrap();

    // Use a fake HOME so no config is loaded
    let out = Command::new(nff())
        .args(["flash", sketch_dir.to_str().unwrap()])
        .env("HOME", &tmp)
        .env("USERPROFILE", &tmp)
        .current_dir(&tmp)
        .output()
        .unwrap();

    assert!(!out.status.success());
    std::fs::remove_dir_all(tmp).ok();
}

// ---------------------------------------------------------------------------
// Simulation (requires arduino-cli + wokwi-cli)
// ---------------------------------------------------------------------------

#[test]
#[ignore = "requires arduino-cli and wokwi-cli on PATH"]
fn flash_sim_blink_sketch() {
    let tmp = std::env::temp_dir().join(format!("nff_sim_{}", std::process::id()));
    let sketch = tmp.join("blink");
    std::fs::create_dir_all(&sketch).unwrap();
    std::fs::write(
        sketch.join("blink.ino"),
        r#"
void setup() {
    Serial.begin(9600);
    pinMode(LED_BUILTIN, OUTPUT);
}
void loop() {
    Serial.println("tick");
    digitalWrite(LED_BUILTIN, HIGH); delay(500);
    digitalWrite(LED_BUILTIN, LOW);  delay(500);
}
"#,
    )
    .unwrap();

    let out = Command::new(nff())
        .args(["flash", "--sim", sketch.to_str().unwrap(), "--board", "arduino:avr:uno", "--sim-timeout", "3000"])
        .output()
        .unwrap();

    assert!(out.status.success(), "sim failed:\n{}", stderr(&out));
    std::fs::remove_dir_all(tmp).ok();
}
