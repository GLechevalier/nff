pub async fn run(args: &crate::cli::McpArgs) -> anyhow::Result<()> {
    let bind = format!("{}:{}", args.host, args.port);
    crate::mcp_server::run(&bind).await
}
