mod cli;
mod commands;
mod mcp_server;
mod tools;

use clap::Parser;
use cli::{AuthSubcommands, Cli, Commands, PiSubcommands, ProvisionSubcommands, WokwiSubcommands};

fn main() {
    let cli = Cli::parse();

    let result = match cli.command {
        Commands::Init(args) => commands::init::run(&args),
        Commands::Compile(args) => commands::compile::run(&args),
        Commands::Flash(args) => commands::flash::run(&args),
        Commands::Monitor(args) => commands::monitor::run(&args),
        Commands::Doctor => commands::doctor::run(),
        Commands::Clean => commands::clean::run(),
        Commands::Test => {
            // The test suite is a development-only command; the shipped binary carries
            // no Python runtime to delegate to.
            eprintln!("`nff test` is a development-only command and isn't available in this binary.");
            std::process::exit(2);
        }
        Commands::Connect => commands::connect::run(),
        Commands::Ota => commands::ota::run(),
        Commands::InstallDeps(args) => commands::install_deps::run(&args),
        Commands::Mcp(args) => tokio::runtime::Runtime::new()
            .expect("failed to create tokio runtime")
            .block_on(commands::mcp::run(&args)),
        Commands::Wokwi(w) => match w.sub {
            WokwiSubcommands::Init(a) => commands::wokwi::run_init(&a),
            WokwiSubcommands::Run(a) => commands::wokwi::run_run(&a),
        },
        Commands::Auth(a) => match a.sub {
            AuthSubcommands::Login(args) => commands::auth::run_login(&args),
            AuthSubcommands::Logout(args) => commands::auth::run_logout(&args),
            AuthSubcommands::Status => commands::auth::run_status(),
        },
        Commands::Repair(args) => commands::repair::run(&args),
        Commands::Provision(p) => match p.sub {
            ProvisionSubcommands::Batch(args) => commands::provision::run_batch(&args),
        },
        Commands::Agent(args) => commands::agent::run(&args),
        Commands::Pi(p) => match p.sub {
            PiSubcommands::Probe(args) => commands::pi::run_probe(&args),
        },
    };

    if let Err(e) = result {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
