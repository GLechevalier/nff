use crate::tools::config;
use std::io::{BufRead, BufReader, Write};
use std::time::{Duration, Instant};
use thiserror::Error;

#[derive(Error, Debug)]
pub enum SerialError {
    #[error("No port specified and no default port in config. Run `nff init` or pass --port explicitly.")]
    NoPort,
    #[error("No port specified and config is unreadable: {0}")]
    ConfigUnreadable(String),
    #[error("Could not open {port}: {source}")]
    Open {
        port: String,
        #[source]
        source: serialport::Error,
    },
    #[error("Read error on {port}: {source}")]
    Read {
        port: String,
        source: serialport::Error,
    },
}

pub fn resolve_port(opt: Option<&str>) -> Result<String, SerialError> {
    if let Some(p) = opt {
        return Ok(p.to_string());
    }
    let cfg = config::get_default_device()
        .map_err(|e| SerialError::ConfigUnreadable(e.to_string()))?;
    cfg.port
        .filter(|p| !p.is_empty())
        .ok_or(SerialError::NoPort)
}

pub fn resolve_baud(opt: Option<u32>) -> Result<u32, SerialError> {
    if let Some(b) = opt {
        return Ok(b);
    }
    Ok(config::get_default_device()
        .map(|c| c.baud)
        .unwrap_or(9600))
}

fn open_port(port: &str, baud: u32) -> Result<Box<dyn serialport::SerialPort>, SerialError> {
    serialport::new(port, baud)
        .timeout(Duration::from_millis(100))
        .open()
        .map_err(|e| SerialError::Open { port: port.to_string(), source: e })
}

pub fn serial_read(duration_ms: u64, port: Option<&str>, baud: Option<u32>) -> String {
    let port_str = match resolve_port(port) {
        Ok(p) => p,
        Err(e) => return format!("ERROR: {e}"),
    };
    let baud_val = resolve_baud(baud).unwrap_or(9600);

    let mut sp = match open_port(&port_str, baud_val) {
        Ok(p) => p,
        Err(e) => return format!("ERROR: {e}"),
    };

    let deadline = Instant::now() + Duration::from_millis(duration_ms);
    let mut buf = Vec::new();

    while Instant::now() < deadline {
        let mut chunk = [0u8; 256];
        match sp.read(&mut chunk) {
            Ok(0) => {}
            Ok(n) => buf.extend_from_slice(&chunk[..n]),
            Err(ref e) if e.kind() == std::io::ErrorKind::TimedOut => {}
            Err(e) => return format!("ERROR: {e}"),
        }
    }
    String::from_utf8_lossy(&buf).into_owned()
}

pub fn serial_write(data: &str, port: Option<&str>, baud: Option<u32>) -> String {
    let data = if data.ends_with('\n') {
        data.to_string()
    } else {
        format!("{data}\n")
    };

    let port_str = match resolve_port(port) {
        Ok(p) => p,
        Err(e) => return format!("ERROR: {e}"),
    };
    let baud_val = resolve_baud(baud).unwrap_or(9600);

    let mut sp = match open_port(&port_str, baud_val) {
        Ok(p) => p,
        Err(e) => return format!("ERROR: {e}"),
    };

    let bytes = data.as_bytes();
    match sp.write_all(bytes) {
        Ok(_) => format!("OK: wrote {} byte(s) to {}", bytes.len(), port_str),
        Err(e) => format!("ERROR: {e}"),
    }
}

pub fn reset_device(port: Option<&str>) -> String {
    let port_str = match resolve_port(port) {
        Ok(p) => p,
        Err(e) => return format!("ERROR: {e}"),
    };

    let mut sp = match serialport::new(&port_str, 9600)
        .timeout(Duration::from_millis(1000))
        .open()
    {
        Ok(p) => p,
        Err(e) => return format!("ERROR: Could not reset {port_str}: {e}"),
    };

    if let Err(e) = sp.write_data_terminal_ready(false) {
        return format!("ERROR: Could not reset {port_str}: {e}");
    }
    std::thread::sleep(Duration::from_millis(50));
    if let Err(e) = sp.write_data_terminal_ready(true) {
        return format!("ERROR: Could not reset {port_str}: {e}");
    }
    std::thread::sleep(Duration::from_millis(50));

    format!("OK: reset {port_str} via DTR toggle")
}

pub fn stream_lines(
    port: Option<&str>,
    baud: Option<u32>,
    timeout_s: Option<f64>,
) -> Result<impl Iterator<Item = String>, SerialError> {
    let port_str = resolve_port(port)?;
    let baud_val = resolve_baud(baud)?;

    let sp = open_port(&port_str, baud_val)?;
    let deadline = timeout_s.map(|s| Instant::now() + Duration::from_secs_f64(s));

    let reader = BufReader::new(sp);
    let iter = reader.lines().map_while(move |line| {
        if let Some(d) = deadline {
            if Instant::now() >= d {
                return None;
            }
        }
        match line {
            Ok(l) => Some(l),
            Err(_) => None,
        }
    });

    Ok(iter)
}
