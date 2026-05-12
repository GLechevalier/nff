use crate::cli::MonitorArgs;
use crate::tools::serial;
use anyhow::Result;

pub fn run(args: &MonitorArgs) -> Result<()> {
    let port = serial::resolve_port(args.port.as_deref())
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    let baud = serial::resolve_baud(args.baud).unwrap_or(9600);

    eprintln!("nff monitor  —  Ctrl+C to exit");
    eprintln!("  {}  @  {} baud", port, baud);
    eprintln!("{}", "─".repeat(60));

    let lines = serial::stream_lines(Some(&port), Some(baud), args.timeout)
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    for line in lines {
        println!("{line}");
    }
    Ok(())
}
