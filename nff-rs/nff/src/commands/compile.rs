use crate::cli::CompileArgs;
use crate::tools::{config, toolchain};

/// `nff compile <file>` — compile a sketch only (no upload, no port required).
pub fn run(args: &CompileArgs) -> anyhow::Result<()> {
    let fqbn = args
        .board
        .clone()
        .or_else(|| config::get_default_device().ok().and_then(|d| d.fqbn))
        .unwrap_or_default();
    if fqbn.is_empty() {
        anyhow::bail!("No board FQBN — pass --board or run `nff init`");
    }

    let result = toolchain::compile_only(&fqbn, None, Some(&args.file))
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    if args.json {
        println!("{}", serde_json::to_string_pretty(&result.to_json())?);
        if !result.ok {
            std::process::exit(1);
        }
        return Ok(());
    }

    if !result.ok {
        eprintln!("Compile failed");
        let errors = result.errors();
        if errors.is_empty() {
            eprintln!("{}", result.output);
        } else {
            for line in errors {
                eprintln!("{line}");
            }
        }
        std::process::exit(1);
    }

    println!("Compile succeeded ({fqbn})");
    if let Some(elf) = result.elf() {
        println!("elf:   {}", elf.display());
    }
    if let Some(image) = result.image() {
        if Some(image) != result.elf() {
            println!("image: {}", image.display());
        }
    }
    Ok(())
}
