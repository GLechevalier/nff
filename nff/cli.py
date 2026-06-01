"""nff CLI — Click command group wiring all subcommands."""

import click

from nff import __version__
from nff.commands.auth_cmd import auth_cli
from nff.commands.clean import clean
from nff.commands.connect import connect
from nff.commands.doctor import doctor
from nff.commands.flash import flash
from nff.commands.init import init
from nff.commands.install_deps import install_deps
from nff.commands.mcp_cmd import mcp
from nff.commands.monitor import monitor
from nff.commands.ota import ota
from nff.commands.repair import repair
from nff.commands.wokwi_cmd import wokwi_cli


@click.group()
@click.version_option(version=__version__, prog_name="nff")
def cli():
    """nff — Claude Code IoT Bridge."""


cli.add_command(init)
cli.add_command(flash)
cli.add_command(monitor)
cli.add_command(doctor)
cli.add_command(clean)
cli.add_command(connect)
cli.add_command(ota)
cli.add_command(install_deps)
cli.add_command(mcp)
cli.add_command(auth_cli, name="auth")
cli.add_command(wokwi_cli, name="wokwi")
cli.add_command(repair)
