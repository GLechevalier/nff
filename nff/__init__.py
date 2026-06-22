"""nff — Claude Code IoT Bridge."""

__version__ = "0.2.20"


def run() -> None:
    """Console-script entry point."""
    from nff.cli import cli
    cli(standalone_mode=True)
