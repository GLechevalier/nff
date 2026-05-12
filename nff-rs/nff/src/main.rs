mod cli;
mod commands;
mod mcp_server;
mod tools;

use clap::Parser;
use cli::{Cli, Commands, WokwiSubcommands};

fn main() {
    let cli = Cli::parse();

    let result = match cli.command {
        Commands::Init(args)        => commands::init::run(&args),
        Commands::Flash(args)       => commands::flash::run(&args),
        Commands::Monitor(args)     => commands::monitor::run(&args),
        Commands::Doctor            => commands::doctor::run(),
        Commands::Clean             => commands::clean::run(),
        Commands::Test              => delegate_python(&["test"]),
        Commands::Connect           => commands::connect::run(),
        Commands::Ota               => commands::ota::run(),
        Commands::InstallDeps(args) => commands::install_deps::run(&args),
        Commands::Mcp               => tokio::runtime::Runtime::new()
            .expect("failed to create tokio runtime")
            .block_on(commands::mcp::run()),
        Commands::Wokwi(w) => match w.sub {
            WokwiSubcommands::Init(a) => commands::wokwi::run_init(&a),
            WokwiSubcommands::Run(a)  => commands::wokwi::run_run(&a),
        },
    };

    if let Err(e) = result {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}

fn delegate_python(args: &[&str]) -> anyhow::Result<()> {
    let python = which::which("python")
        .or_else(|_| which::which("python3"))
        .map_err(|_| anyhow::anyhow!("Python not found — install Python 3.10+"))?;
    let mut cmd_args = vec!["-m", "nff"];
    cmd_args.extend_from_slice(args);
    let status = std::process::Command::new(&python)
        .args(&cmd_args)
        .status()?;
    std::process::exit(status.code().unwrap_or(1));
}
