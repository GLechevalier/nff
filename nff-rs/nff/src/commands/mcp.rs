pub async fn run() -> anyhow::Result<()> {
    crate::mcp_server::run().await
}
