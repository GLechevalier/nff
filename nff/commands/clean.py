"""nff clean — remove build artifacts."""

import shutil
import tempfile
from pathlib import Path

import click


@click.command()
def clean():
    """Remove nff build artifacts."""
    sketch_dir = Path(tempfile.gettempdir()) / "nff_sketch"
    if sketch_dir.exists():
        shutil.rmtree(sketch_dir, ignore_errors=True)
        click.echo(f"Removed {sketch_dir}")
    else:
        click.echo("Nothing to clean.")
