//! `nff debug` — live on-chip debugging (OpenOCD + GDB over JTAG/SWD).
//!
//! `check` reports what nff would use (binaries, chip, ELF) without touching hardware.
//! `start` launches a session and drops into a small REPL — one long-lived process, so the
//! OpenOCD + GDB session persists between commands (a CLI that ran each verb as a separate
//! process couldn't keep the target halted between calls). The programmatic surface is the
//! debug_* MCP tools; this command is for manual bench use.

use std::io::{BufRead, Write};

use serde_json::Value;

use crate::cli::{DebugCheckArgs, DebugStartArgs};
use crate::tools::debug;

fn emit(v: &Value) {
    match v {
        Value::String(s) => println!("{s}"),
        other => println!("{}", serde_json::to_string_pretty(other).unwrap_or_default()),
    }
}

pub fn run_check(args: &DebugCheckArgs) -> anyhow::Result<()> {
    let chip = debug::detect_chip(args.board.clone().or_else(debug::autodetect_board));
    let openocd = debug::find_openocd(&chip).unwrap_or_else(|| "NOT FOUND".into());
    let gdb = debug::find_gdb(&chip).unwrap_or_else(|| "NOT FOUND".into());
    let elf = match debug::resolve_elf(None) {
        Ok(p) => p.to_string_lossy().into_owned(),
        Err(e) => format!("(none — {e})"),
    };
    let cfg = match debug::openocd_config(&chip, None) {
        Ok(args) => args.join(" "),
        Err(e) => format!("(needs interface — {e})"),
    };
    println!("chip:           {chip}");
    println!("openocd:        {openocd}");
    println!("gdb:            {gdb}");
    println!("openocd config: {cfg}");
    println!("elf:            {elf}");
    Ok(())
}

const REPL_HELP: &str = "commands:
  info                    session + current frame
  bt                      call stack
  regs                    core registers
  vars [frame]            local variables in a frame (default 0)
  expand <expr>           expand a struct/array/pointer
  mem <addr> [count]      hex dump (count bytes, default 64)
  eval <expr>             evaluate a C/C++ expression
  break <location>        set a breakpoint (file:line or function)
  step [over|into|out]    step the target
  continue                resume
  pause                   halt
  gdb <command>           raw GDB command
  help                    this help
  quit / stop             end the session and exit";

pub fn run_start(args: &DebugStartArgs) -> anyhow::Result<()> {
    let mut session = debug::open_session(
        args.elf.as_deref(),
        args.board.as_deref(),
        args.interface.as_deref(),
    )
    .map_err(|e| anyhow::anyhow!("{e}"))?;

    println!("debug session started — type `help` for commands, `quit` to exit");
    match session.session_info() {
        Ok(v) => emit(&v),
        Err(e) => println!("ERROR: {e}"),
    }

    let stdin = std::io::stdin();
    loop {
        print!("nff-debug> ");
        std::io::stdout().flush().ok();
        let mut line = String::new();
        if stdin.lock().read_line(&mut line)? == 0 {
            break; // EOF (Ctrl-D / closed pipe)
        }
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let (verb, rest) = match line.split_once(' ') {
            Some((v, r)) => (v, r.trim()),
            None => (line, ""),
        };
        let result: Result<Option<Value>, debug::DebugError> = match verb.to_lowercase().as_str() {
            "quit" | "exit" | "stop" | "q" => break,
            "help" => {
                println!("{REPL_HELP}");
                Ok(None)
            }
            "info" => session.session_info().map(Some),
            "bt" => session.call_stack().map(Some),
            "regs" => session.registers().map(Some),
            "vars" => {
                let frame = rest.parse::<i64>().unwrap_or(0);
                session.variables(frame).map(Some)
            }
            "expand" => session.expand_variable(rest).map(Some),
            "mem" => {
                let (addr, cnt) = match rest.split_once(' ') {
                    Some((a, c)) => (a, c.trim()),
                    None => (rest, ""),
                };
                let count = cnt.parse::<i64>().unwrap_or(64);
                session.memory(addr, count).map(Some)
            }
            "eval" => session.evaluate(rest).map(Some),
            "break" => session.set_breakpoint(rest).map(Some),
            "step" => session.step(if rest.is_empty() { "over" } else { rest }).map(Some),
            "continue" => session.cont().map(Some),
            "pause" => session.pause().map(Some),
            "gdb" => session.gdb_command(rest).map(Some),
            other => {
                println!("unknown command {other:?} — type `help`");
                Ok(None)
            }
        };
        match result {
            Ok(Some(v)) => emit(&v),
            Ok(None) => {}
            Err(e) => println!("ERROR: {e}"),
        }
    }

    // Dropping the session stops OpenOCD + GDB.
    drop(session);
    println!("debug session stopped");
    Ok(())
}
