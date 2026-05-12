/// Integration tests for the MCP JSON-RPC server.
/// Spawns `nff mcp`, pipes messages in, captures output.
/// Run with: cargo test --test mcp
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn nff() -> PathBuf {
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

/// Pipe `messages` (one per line) to `nff mcp` stdin, close stdin, return stdout.
fn mcp_exchange(messages: &[&str]) -> String {
    let mut child = Command::new(nff())
        .arg("mcp")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null()) // suppress any startup noise
        .spawn()
        .expect("failed to spawn nff mcp");

    {
        let stdin = child.stdin.as_mut().unwrap();
        for msg in messages {
            stdin.write_all(msg.as_bytes()).unwrap();
            stdin.write_all(b"\n").unwrap();
        }
    } // stdin dropped → EOF → server exits

    let out = child.wait_with_output().unwrap();
    String::from_utf8_lossy(&out.stdout).into_owned()
}

const INIT: &str = r#"{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}"#;
const INITIALIZED: &str = r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#;
const LIST_TOOLS: &str = r#"{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}"#;

// ---------------------------------------------------------------------------
// Handshake
// ---------------------------------------------------------------------------

#[test]
fn initialize_returns_valid_json() {
    let output = mcp_exchange(&[INIT]);
    // There must be at least one parseable JSON object in the output.
    let found = output
        .lines()
        .filter(|l| !l.trim().is_empty())
        .any(|l| serde_json::from_str::<serde_json::Value>(l).is_ok());
    assert!(found, "no valid JSON line found in output:\n{output}");
}

#[test]
fn initialize_response_has_id_1() {
    let output = mcp_exchange(&[INIT]);
    let response = output
        .lines()
        .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
        .find(|v| v["id"] == 1)
        .expect("no response with id=1 found");
    assert!(response["result"].is_object(), "result should be an object: {response}");
}

// ---------------------------------------------------------------------------
// tools/list — must expose exactly the 9 migrated tools
// ---------------------------------------------------------------------------

#[test]
fn tools_list_returns_all_nine_tools() {
    let output = mcp_exchange(&[INIT, INITIALIZED, LIST_TOOLS]);

    let expected = [
        "list_devices",
        "flash",
        "serial_read",
        "serial_write",
        "reset_device",
        "get_device_info",
        "wokwi_flash",
        "wokwi_serial_read",
        "wokwi_get_diagram",
    ];

    for tool in &expected {
        assert!(
            output.contains(tool),
            "tool '{tool}' not found in tools/list response:\n{output}"
        );
    }
}

#[test]
fn tools_list_response_is_valid_json() {
    let output = mcp_exchange(&[INIT, INITIALIZED, LIST_TOOLS]);
    let tool_response = output
        .lines()
        .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
        .find(|v| v["id"] == 2);
    assert!(
        tool_response.is_some(),
        "no tools/list response (id=2) found:\n{output}"
    );
    let resp = tool_response.unwrap();
    let tools = resp["result"]["tools"].as_array();
    assert!(tools.is_some(), "result.tools should be an array: {resp}");
    assert_eq!(tools.unwrap().len(), 9, "expected exactly 9 tools: {resp}");
}

// ---------------------------------------------------------------------------
// tools/call — no-hardware tools that must always work
// ---------------------------------------------------------------------------

#[test]
fn call_list_devices_returns_devices_key() {
    let call = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_devices","arguments":{}}}"#;
    let output = mcp_exchange(&[INIT, INITIALIZED, call]);

    let resp = output
        .lines()
        .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
        .find(|v| v["id"] == 3)
        .expect("no response for list_devices call");

    let content = resp["result"]["content"][0]["text"]
        .as_str()
        .expect("content[0].text should be a string");

    let parsed: serde_json::Value = serde_json::from_str(content)
        .unwrap_or_else(|e| panic!("list_devices result is not valid JSON: {e}\n{content}"));

    assert!(
        parsed["devices"].is_array(),
        "list_devices result should have a 'devices' array: {parsed}"
    );
}

#[test]
fn call_wokwi_get_diagram_uno() {
    let call = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"wokwi_get_diagram","arguments":{"board":"arduino:avr:uno"}}}"#;
    let output = mcp_exchange(&[INIT, INITIALIZED, call]);

    let resp = output
        .lines()
        .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
        .find(|v| v["id"] == 3)
        .expect("no response for wokwi_get_diagram call");

    let content = resp["result"]["content"][0]["text"]
        .as_str()
        .expect("content[0].text missing");

    let diagram: serde_json::Value = serde_json::from_str(content)
        .unwrap_or_else(|e| panic!("wokwi_get_diagram result not valid JSON: {e}\n{content}"));

    assert_eq!(diagram["parts"][0]["type"], "wokwi-arduino-uno");
    assert_eq!(diagram["version"], 1);
}

#[test]
fn call_wokwi_get_diagram_all_supported_boards() {
    let boards = [
        ("arduino:avr:uno",         "wokwi-arduino-uno"),
        ("arduino:avr:mega",        "wokwi-arduino-mega"),
        ("arduino:avr:nano",        "wokwi-arduino-nano"),
        ("arduino:avr:leonardo",    "wokwi-arduino-leonardo"),
        ("esp32:esp32:esp32",       "wokwi-esp32-devkit-v1"),
        ("esp8266:esp8266:generic", "wokwi-esp8266"),
    ];

    for (fqbn, expected_chip) in boards {
        let call = format!(
            r#"{{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{{"name":"wokwi_get_diagram","arguments":{{"board":"{fqbn}"}}}}}}"#
        );
        let output = mcp_exchange(&[INIT, INITIALIZED, &call]);
        assert!(
            output.contains(expected_chip),
            "chip '{expected_chip}' not found in diagram for {fqbn}:\n{output}"
        );
    }
}

#[test]
fn call_wokwi_get_diagram_unsupported_board_returns_error() {
    let call = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"wokwi_get_diagram","arguments":{"board":"not:a:board"}}}"#;
    let output = mcp_exchange(&[INIT, INITIALIZED, call]);

    let resp = output
        .lines()
        .filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
        .find(|v| v["id"] == 3)
        .expect("no response");

    let text = resp["result"]["content"][0]["text"].as_str().unwrap_or("");
    assert!(
        text.starts_with("ERROR:"),
        "unsupported board should return ERROR: prefix: {text}"
    );
}

#[test]
fn mcp_stdout_has_no_stray_print_before_handshake() {
    // Any non-JSON bytes before the first JSON object would corrupt the framing.
    let output = mcp_exchange(&[INIT]);
    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() { continue; }
        assert!(
            serde_json::from_str::<serde_json::Value>(trimmed).is_ok(),
            "non-JSON line in MCP output (would corrupt framing): {trimmed:?}"
        );
    }
}

// ---------------------------------------------------------------------------
// Hardware-dependent (skipped by default)
// ---------------------------------------------------------------------------

#[test]
#[ignore = "requires a connected Arduino/ESP32"]
fn call_serial_read_from_real_device() {
    let call = r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"serial_read","arguments":{"duration_ms":500}}}"#;
    let output = mcp_exchange(&[INIT, INITIALIZED, call]);
    assert!(output.contains("id") && output.contains("result"));
}

#[test]
#[ignore = "requires arduino-cli and wokwi-cli"]
fn call_wokwi_flash_blink() {
    let code = r#"void setup(){Serial.begin(9600);} void loop(){Serial.println(\"tick\");delay(500);}"#;
    let call = format!(
        r#"{{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{{"name":"wokwi_flash","arguments":{{"code":"{code}","board":"arduino:avr:uno","timeout_ms":3000}}}}}}"#
    );
    let output = mcp_exchange(&[INIT, INITIALIZED, &call]);
    assert!(output.contains("serial_output"), "should contain serial_output key");
}
