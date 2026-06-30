"""nff debug — live on-chip debugging (OpenOCD + GDB over JTAG).

`nff debug check` reports what nff would use (OpenOCD/GDB binaries, chip, ELF) without
touching hardware. `nff debug start` launches a session and drops into a small REPL —
one long-lived process, so the OpenOCD + GDB session persists between commands (a CLI
that ran each verb as a separate process couldn't keep the target halted between calls).

The programmatic surface is the debug_* MCP tools; this command is for manual bench use.
"""

import json

import click

from nff.tools import debug as debug_module


def _emit(result) -> None:
    """Print a debug result: dicts as pretty JSON, strings (OK:/ERROR:) as-is."""
    if isinstance(result, dict):
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(result)


@click.group(invoke_without_command=True)
@click.option("--elf", default=None, help="Path to a built .elf (defaults to the last build)")
@click.option("--board", default=None, help="Board id/FQBN to derive the chip family")
@click.option("--interface", default=None, help="OpenOCD interface cfg for an external JTAG probe")
@click.pass_context
def debug(ctx, elf, board, interface):
    """Live on-chip debugging (OpenOCD + GDB). Runs `start` when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(start, elf=elf, board=board, interface=interface)


@debug.command()
@click.option("--board", default=None, help="Board id/FQBN to derive the chip family")
def check(board):
    """Report the OpenOCD/GDB binaries, chip, and ELF nff would use — no hardware needed."""
    chip = debug_module.detect_chip(board or debug_module.autodetect_board())
    openocd = debug_module.find_openocd(chip)
    gdb = debug_module.find_gdb(chip)
    try:
        elf = str(debug_module.resolve_elf())
    except debug_module.DebugError as exc:
        elf = f"(none — {exc})"
    try:
        cfg_args = " ".join(debug_module.openocd_config(chip))
    except debug_module.DebugError as exc:
        cfg_args = f"(needs interface — {exc})"
    click.echo(f"chip:           {chip}")
    click.echo(f"openocd:        {openocd or 'NOT FOUND'}")
    click.echo(f"gdb:            {gdb or 'NOT FOUND'}")
    click.echo(f"openocd config: {cfg_args}")
    click.echo(f"elf:            {elf}")


_REPL_HELP = """commands:
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
  quit / stop             end the session and exit"""


@debug.command()
@click.option("--elf", default=None, help="Path to a built .elf (defaults to the last build)")
@click.option("--board", default=None, help="Board id/FQBN to derive the chip family")
@click.option("--interface", default=None, help="OpenOCD interface cfg for an external JTAG probe")
def start(elf, board, interface):
    """Start a debug session and enter an interactive prompt."""
    try:
        info = debug_module.start_session(elf, board, interface)
    except debug_module.DebugError as exc:
        raise click.ClickException(str(exc))
    click.echo("debug session started — type `help` for commands, `quit` to exit")
    _emit(info)
    try:
        _repl()
    finally:
        debug_module.stop_session()
        click.echo("debug session stopped")


def _repl() -> None:
    session = debug_module.require_session()
    while True:
        try:
            line = click.prompt("nff-debug", prompt_suffix="> ", default="", show_default=False)
        except (EOFError, click.Abort):
            return
        line = line.strip()
        if not line:
            continue
        verb, _, rest = line.partition(" ")
        rest = rest.strip()
        verb = verb.lower()
        try:
            if verb in ("quit", "exit", "stop", "q"):
                return
            elif verb == "help":
                click.echo(_REPL_HELP)
            elif verb == "info":
                _emit(session.session_info())
            elif verb == "bt":
                _emit(session.call_stack())
            elif verb == "regs":
                _emit(session.registers())
            elif verb == "vars":
                _emit(session.variables(int(rest) if rest else 0))
            elif verb == "expand":
                _emit(session.expand_variable(rest))
            elif verb == "mem":
                addr, _, cnt = rest.partition(" ")
                _emit(session.memory(addr, int(cnt) if cnt.strip() else 64))
            elif verb == "eval":
                _emit(session.evaluate(rest))
            elif verb == "break":
                _emit(session.set_breakpoint(rest))
            elif verb == "step":
                _emit(session.step(rest or "over"))
            elif verb == "continue":
                _emit(session.cont())
            elif verb == "pause":
                _emit(session.pause())
            elif verb == "gdb":
                _emit(session.gdb_command(rest))
            else:
                click.echo(f"unknown command {verb!r} — type `help`")
        except debug_module.DebugError as exc:
            click.echo(f"ERROR: {exc}")
