pub async fn run(args: &crate::cli::McpArgs) -> anyhow::Result<()> {
    // `nff init` already starts the server in the background, so a manual `nff mcp`
    // would otherwise crash on the bound port. Bail out cleanly if it's already up.
    if crate::tools::daemon::is_running(&args.host, args.port) {
        println!(
            "nff MCP server already running on http://{}:{}/mcp",
            args.host, args.port
        );
        return Ok(());
    }
    let bind = format!("{}:{}", args.host, args.port);
    crate::mcp_server::run(&bind).await
}
