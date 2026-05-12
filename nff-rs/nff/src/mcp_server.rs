use rmcp::{handler::server::wrapper::Parameters, tool, tool_router, ServiceExt, transport::stdio};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Clone)]
pub struct NffServer;

// ---------------------------------------------------------------------------
// Parameter types
// ---------------------------------------------------------------------------

#[derive(Deserialize, JsonSchema)]
struct FlashParams {
    /// Full Arduino/C++ sketch source code
    code: String,
    /// Board FQBN, e.g. 'arduino:avr:uno'. Defaults to config.
    board: Option<String>,
    /// Serial port, e.g. 'COM3'. Defaults to config.
    port: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct SerialReadParams {
    /// How long to listen in milliseconds
    #[serde(default = "default_3000_u64")]
    duration_ms: u64,
    /// Serial port. Defaults to config.
    port: Option<String>,
    /// Baud rate. Defaults to config (9600).
    baud: Option<u32>,
}
fn default_3000_u64() -> u64 {
    3000
}

#[derive(Deserialize, JsonSchema)]
struct SerialWriteParams {
    /// String to transmit. A newline is appended if absent.
    data: String,
    /// Serial port. Defaults to config.
    port: Option<String>,
    /// Baud rate. Defaults to config (9600).
    baud: Option<u32>,
}

#[derive(Deserialize, JsonSchema)]
struct PortParam {
    /// Serial port. Defaults to config.
    port: Option<String>,
}

#[derive(Deserialize, JsonSchema)]
struct WokwiFlashParams {
    /// Full Arduino/C++ sketch source code
    code: String,
    /// Board FQBN. Defaults to config.
    board: Option<String>,
    /// Simulation wall-clock timeout in milliseconds
    #[serde(default = "default_5000")]
    timeout_ms: u32,
}
fn default_5000() -> u32 {
    5000
}

#[derive(Deserialize, JsonSchema)]
struct WokwiSerialReadParams {
    /// Full Arduino/C++ sketch source code
    code: String,
    /// Board FQBN. Defaults to config.
    board: Option<String>,
    /// Simulation duration in milliseconds
    #[serde(default = "default_3000_u32")]
    duration_ms: u32,
}
fn default_3000_u32() -> u32 {
    3000
}

#[derive(Deserialize, JsonSchema)]
struct BoardParam {
    /// Board FQBN, e.g. 'arduino:avr:uno'
    board: String,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn resolve_fqbn(board: Option<String>) -> Result<String, String> {
    let fqbn = board
        .or_else(|| {
            crate::tools::config::get_default_device()
                .ok()
                .and_then(|d| d.fqbn)
        })
        .unwrap_or_default();
    if fqbn.is_empty() {
        Err("Missing board FQBN (pass board= or run `nff init`)".into())
    } else {
        Ok(fqbn)
    }
}

fn json_sim_error(serial_output: &str, compile_output: &str, exit_code: i32) -> String {
    json!({
        "serial_output": serial_output,
        "compile_output": compile_output,
        "exit_code": exit_code,
        "simulated": true,
    })
    .to_string()
}

// ---------------------------------------------------------------------------
// MCP server
// ---------------------------------------------------------------------------

#[tool_router(server_handler)]
impl NffServer {
    #[tool(description = "List all connected USB/serial devices with board identification")]
    fn list_devices(&self) -> String {
        let devices = crate::tools::boards::list_devices();
        let list: Vec<Value> = devices
            .iter()
            .map(|d| {
                json!({
                    "port": d.port,
                    "board": d.board,
                    "fqbn": d.fqbn,
                    "vendor_id": d.vendor_id,
                    "product_id": d.product_id,
                    "wokwi_chip": d.wokwi_chip,
                })
            })
            .collect();
        json!({ "devices": list }).to_string()
    }

    #[tool(description = "Compile and upload an Arduino/ESP sketch to the connected board. Returns OK: on success or ERROR: on failure.")]
    fn flash(&self, Parameters(p): Parameters<FlashParams>) -> String {
        use crate::tools::{config, toolchain};
        let device = config::get_default_device().unwrap_or_default();
        let fqbn = p.board.or_else(|| device.fqbn.clone()).unwrap_or_default();
        let port = p
            .port
            .or_else(|| device.port.clone().filter(|s| !s.is_empty()))
            .unwrap_or_default();
        if fqbn.is_empty() {
            return "ERROR: Missing board FQBN (pass board= or run `nff init`)".into();
        }
        if port.is_empty() {
            return "ERROR: Missing port (pass port= or run `nff init`)".into();
        }
        toolchain::flash(&p.code, &fqbn, &port)
    }

    #[tool(description = "Capture serial output from the device for a given duration. Returns captured text or ERROR:.")]
    fn serial_read(&self, Parameters(p): Parameters<SerialReadParams>) -> String {
        crate::tools::serial::serial_read(p.duration_ms, p.port.as_deref(), p.baud)
    }

    #[tool(description = "Send a string to the device over serial. Returns OK: wrote N bytes or ERROR:.")]
    fn serial_write(&self, Parameters(p): Parameters<SerialWriteParams>) -> String {
        crate::tools::serial::serial_write(&p.data, p.port.as_deref(), p.baud)
    }

    #[tool(description = "Toggle DTR to hardware-reset the board. Returns OK: or ERROR:.")]
    fn reset_device(&self, Parameters(p): Parameters<PortParam>) -> String {
        crate::tools::serial::reset_device(p.port.as_deref())
    }

    #[tool(description = "Return detailed information about the connected device as JSON")]
    fn get_device_info(&self, Parameters(p): Parameters<PortParam>) -> String {
        use crate::tools::{boards, config, serial};
        let port = match serial::resolve_port(p.port.as_deref()) {
            Ok(p) => p,
            Err(e) => return json!({"error": e.to_string()}).to_string(),
        };
        let device = boards::find_device(Some(&port));
        let baud = config::get_default_device().map(|d| d.baud).unwrap_or(9600);
        if let Some(d) = device {
            json!({
                "port": d.port,
                "board": d.board,
                "fqbn": d.fqbn,
                "baud": baud,
                "vendor_id": d.vendor_id,
                "product_id": d.product_id,
                "wokwi_chip": d.wokwi_chip,
            })
            .to_string()
        } else {
            let cfg = config::get_default_device().unwrap_or_default();
            json!({
                "port": port,
                "board": cfg.board.unwrap_or_else(|| "Unknown".into()),
                "fqbn": cfg.fqbn.unwrap_or_default(),
                "baud": baud,
                "vendor_id": "",
                "product_id": "",
                "wokwi_chip": null,
            })
            .to_string()
        }
    }

    #[tool(description = "Compile a sketch and run it in the Wokwi simulator. No hardware needed. Returns JSON with serial_output, compile_output, exit_code, simulated.")]
    fn wokwi_flash(&self, Parameters(p): Parameters<WokwiFlashParams>) -> String {
        use crate::tools::{toolchain, wokwi};
        let fqbn = match resolve_fqbn(p.board) {
            Ok(f) => f,
            Err(e) => return json_sim_error("", &e, 1),
        };
        let sketch_dir = match toolchain::write_sketch(&p.code, None) {
            Ok(d) => d,
            Err(e) => return json_sim_error("", &e.to_string(), 1),
        };
        let compile_result = match toolchain::compile_sketch(&sketch_dir, &fqbn) {
            Ok(r) => r,
            Err(e) => return json_sim_error("", &format!("compile error: {e}"), 1),
        };
        let compile_output = compile_result.output();
        if !compile_result.success {
            return json_sim_error("", &compile_output, compile_result.returncode);
        }
        let elf_path = toolchain::elf_path_for(&sketch_dir, &fqbn);
        let diagram = match wokwi::generate_diagram(&fqbn) {
            Ok(d) => d,
            Err(e) => {
                return json_sim_error("", &format!("{compile_output}\nwokwi setup error: {e}"), 1)
            }
        };
        if let Err(e) = std::fs::write(
            sketch_dir.join("diagram.json"),
            serde_json::to_string_pretty(&diagram).unwrap_or_default(),
        ) {
            return json_sim_error(
                "",
                &format!("{compile_output}\ndiagram.json write error: {e}"),
                1,
            );
        }
        if let Err(e) = wokwi::write_wokwi_toml(&sketch_dir, &elf_path) {
            return json_sim_error("", &format!("{compile_output}\nwokwi.toml error: {e}"), 1);
        }
        match wokwi::run_simulation(&sketch_dir, p.timeout_ms) {
            Ok(r) => json!({
                "serial_output": r.serial_output,
                "compile_output": compile_output,
                "exit_code": r.exit_code,
                "simulated": true,
            })
            .to_string(),
            Err(e) => json_sim_error(&format!("wokwi error: {e}"), &compile_output, 1),
        }
    }

    #[tool(description = "Compile and simulate a sketch, returning only the serial output string")]
    fn wokwi_serial_read(&self, Parameters(p): Parameters<WokwiSerialReadParams>) -> String {
        use crate::tools::{toolchain, wokwi};
        let fqbn = match resolve_fqbn(p.board) {
            Ok(f) => f,
            Err(e) => return format!("ERROR: {e}"),
        };
        let sketch_dir = match toolchain::write_sketch(&p.code, None) {
            Ok(d) => d,
            Err(e) => return format!("ERROR: {e}"),
        };
        let compile_result = match toolchain::compile_sketch(&sketch_dir, &fqbn) {
            Ok(r) => r,
            Err(e) => return format!("ERROR: compile failed: {e}"),
        };
        if !compile_result.success {
            return format!("ERROR: compile failed:\n{}", compile_result.output());
        }
        let elf_path = toolchain::elf_path_for(&sketch_dir, &fqbn);
        let diagram = match wokwi::generate_diagram(&fqbn) {
            Ok(d) => d,
            Err(e) => return format!("ERROR: {e}"),
        };
        if let Err(e) = std::fs::write(
            sketch_dir.join("diagram.json"),
            serde_json::to_string_pretty(&diagram).unwrap_or_default(),
        ) {
            return format!("ERROR: {e}");
        }
        if let Err(e) = wokwi::write_wokwi_toml(&sketch_dir, &elf_path) {
            return format!("ERROR: {e}");
        }
        match wokwi::run_simulation(&sketch_dir, p.duration_ms) {
            Ok(r) => r.serial_output,
            Err(e) => format!("ERROR: {e}"),
        }
    }

    #[tool(description = "Return a minimal diagram.json for the given board FQBN as a pretty-printed JSON string")]
    fn wokwi_get_diagram(&self, Parameters(p): Parameters<BoardParam>) -> String {
        match crate::tools::wokwi::generate_diagram(&p.board) {
            Ok(d) => serde_json::to_string_pretty(&d).unwrap_or_else(|e| format!("ERROR: {e}")),
            Err(e) => format!("ERROR: {e}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flash_params_full() {
        let p: FlashParams = serde_json::from_str(
            r#"{"code":"void setup(){}","board":"arduino:avr:uno","port":"COM3"}"#,
        )
        .unwrap();
        assert_eq!(p.code, "void setup(){}");
        assert_eq!(p.board, Some("arduino:avr:uno".into()));
        assert_eq!(p.port, Some("COM3".into()));
    }

    #[test]
    fn flash_params_optional_fields_absent() {
        let p: FlashParams = serde_json::from_str(r#"{"code":"void setup(){}"}"#).unwrap();
        assert!(p.board.is_none());
        assert!(p.port.is_none());
    }

    #[test]
    fn serial_read_defaults() {
        let p: SerialReadParams = serde_json::from_str(r#"{}"#).unwrap();
        assert_eq!(p.duration_ms, 3000);
        assert!(p.port.is_none());
        assert!(p.baud.is_none());
    }

    #[test]
    fn serial_read_explicit() {
        let p: SerialReadParams =
            serde_json::from_str(r#"{"duration_ms":5000,"port":"COM1","baud":115200}"#).unwrap();
        assert_eq!(p.duration_ms, 5000);
        assert_eq!(p.port, Some("COM1".into()));
        assert_eq!(p.baud, Some(115200));
    }

    #[test]
    fn wokwi_flash_defaults() {
        let p: WokwiFlashParams = serde_json::from_str(r#"{"code":"sketch"}"#).unwrap();
        assert_eq!(p.timeout_ms, 5000);
        assert!(p.board.is_none());
    }

    #[test]
    fn wokwi_serial_read_defaults() {
        let p: WokwiSerialReadParams = serde_json::from_str(r#"{"code":"sketch"}"#).unwrap();
        assert_eq!(p.duration_ms, 3000);
        assert!(p.board.is_none());
    }

    #[test]
    fn board_param_required() {
        assert!(serde_json::from_str::<BoardParam>(r#"{}"#).is_err());
        let p: BoardParam =
            serde_json::from_str(r#"{"board":"arduino:avr:uno"}"#).unwrap();
        assert_eq!(p.board, "arduino:avr:uno");
    }

    #[test]
    fn resolve_fqbn_explicit() {
        let result = resolve_fqbn(Some("arduino:avr:uno".into()));
        assert_eq!(result.unwrap(), "arduino:avr:uno");
    }

    #[test]
    fn resolve_fqbn_empty_string_is_error() {
        let result = resolve_fqbn(Some("".into()));
        assert!(result.is_err(), "empty string should be treated as missing");
    }
}

pub async fn run() -> anyhow::Result<()> {
    let service = NffServer.serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}
