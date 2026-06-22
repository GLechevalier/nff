"""nff clean — remove build artifacts."""

import shutil
import tempfile
from pathlib import Path

import click


@click.command()
def clean():
    """Remove nff build artifacts."""
    # nff_sketch = arduino-cli backend; nff_pio = PlatformIO backend (each scaffold's
    # heavy .pio/build output lives nested inside nff_pio, so one rmtree clears it).
    tmp = Path(tempfile.gettempdir())
    removed = []
    for name in ("nff_sketch", "nff_pio"):
        d = tmp / name
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            removed.append(str(d))
    if removed:
        click.echo("\n".join(f"Removed {p}" for p in removed))
    else:
        click.echo("Nothing to clean.")
