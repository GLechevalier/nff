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
    if cfg!(windows) {
        path.join("nff.exe")
    } else {
        path.join("nff")
    }
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
    assert!(
        out.status.success(),
        "nff --version failed:\n{}",
        stderr(&out)
    );
}

#[test]
fn version_output_matches_cargo_version() {
    let out = run(&["--version"]);
    let text = stdout(&out);
    let expected = env!("CARGO_PKG_VERSION");
    assert!(
        text.contains(expected),
        "version output should contain {expected}, got: {text}"
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
    for cmd in &[
        "init",
        "flash",
        "monitor",
        "doctor",
        "clean",
        "install-deps",
        "mcp",
    ] {
        assert!(
            text.contains(cmd),
            "nff --help missing command '{cmd}':\n{text}"
        );
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

    // Point config resolution at an empty dir so NO config is loaded — must work on
    // Windows too, where dirs::home_dir() ignores HOME/USERPROFILE (so a stray real
    // config could otherwise make this test flash an attached board).
    let cfg_dir = tmp.join("nff_cfg");
    std::fs::create_dir_all(&cfg_dir).unwrap();
    let out = Command::new(nff())
        .args(["flash", sketch_dir.to_str().unwrap()])
        .env("NFF_CONFIG_DIR", &cfg_dir)
        .env("HOME", &tmp)
        .env("USERPROFILE", &tmp)
        .current_dir(&tmp)
        .output()
        .unwrap();

    assert!(!out.status.success());
    std::fs::remove_dir_all(tmp).ok();
}
