"""nff init — interactive setup wizard (board config + optional platform onboarding)."""

import subprocess
import types

import click

from nff import config
from nff.tools import (
    auth as auth_tools,
    boards as boards_module,
    bootstrap,
    installer,
    netinfo,
    provisioning_client,
    toolchain,
)

_SIM_BOARDS = [
    ("Arduino Uno",       "arduino:avr:uno"),
    ("Arduino Mega 2560", "arduino:avr:mega"),
    ("Arduino Nano",      "arduino:avr:nano"),
    ("Arduino Leonardo",  "arduino:avr:leonardo"),
    ("ESP32",             "esp32:esp32:esp32"),
    ("ESP8266",           "esp8266:esp8266:generic"),
]

# The bootstrap firmware runs Serial at 115200; keep the saved baud in sync so
# `nff monitor` (and onboarding's own serial watch) match the device.
_BOOTSTRAP_BAUD = 115200


def _register_mcp(host: str = "127.0.0.1", port: int = 3010) -> None:
    try:
        url = f"http://{host}:{port}/mcp"
        subprocess.run(
            ["claude", "mcp", "add", "--scope", "user", "--transport", "http", "nff", url],
            check=False,
        )
    except Exception:
        pass


def _ensure_logged_in() -> bool:
    """Make sure we hold a platform token; trigger browser login if not. Mirrors
    `nff auth login` (no-args browser flow)."""
    cfg = config.get_diagnosis_config()
    if cfg.get("access_token"):
        return True
    server_url = cfg.get("server_url")
    click.echo("\nYou're not signed in to the nff platform. Opening your browser…")
    try:
        sock, port = auth_tools.bind_callback_server()
    except Exception as exc:
        click.echo(f"  Could not start login: {exc}")
        return False
    callback_url = f"http://127.0.0.1:{port}/callback"
    portal_url = f"{server_url}/auth/portal?cb={auth_tools.percent_encode(callback_url)}"
    try:
        auth_tools.open_browser(portal_url)
    except Exception:
        pass
    click.echo(f"  If your browser didn't open, visit: {portal_url}")
    try:
        tokens = auth_tools.wait_for_callback(sock, 300)
    except TimeoutError:
        click.echo("  Login timed out.")
        return False
    config.set_diagnosis_tokens(tokens.access_token, tokens.refresh_token)
    click.echo("  ✓ Signed in")
    return True


def _resolve_wifi() -> tuple[str, str]:
    """Detect host WiFi (SSID + password), confirming/prompting as needed."""
    ssid, password = netinfo.detect_wifi()
    if ssid:
        click.echo(f"  Detected WiFi network: {ssid}")
        if not click.confirm("  Use this network for the device?", default=True):
            ssid, password = None, None
    if not ssid:
        ssid = click.prompt("  WiFi SSID")
        password = None
    if password is None:
        password = click.prompt(
            "  WiFi password", hide_input=True, default="", show_default=False
        )
    return ssid, password


def _onboard_platform(device) -> None:
    """Log in, provision the device's project, bake in WiFi + cloud broker, flash, and
    wait for it to claim — so it shows up in the dashboard automatically."""
    if not _ensure_logged_in():
        click.echo("Skipping platform onboarding.")
        return

    click.echo("\nProvisioning your device on the nff platform…")
    try:
        data = provisioning_client.provision_batch()
    except provisioning_client.ProvisioningError as exc:
        click.echo(f"  Provisioning failed: {exc}")
        return
    config.set_platform_enrollment(data.get("project_id"), data.get("batch_id"))
    click.echo("  ✓ Reusing your existing enrollment batch" if data.get("reused")
               else "  ✓ Enrollment batch ready")

    ssid, password = _resolve_wifi()
    broker_host = config.get_platform_config().get("broker_host")

    try:
        sketch_dir = bootstrap.prepare_bootstrap_sketch(
            data["credentials_h"], ssid, password, broker_host
        )
    except bootstrap.BootstrapError as exc:
        click.echo(f"  Could not prepare firmware: {exc}")
        return

    fqbn = device.fqbn
    click.echo("\nSetting up the ESP32 toolchain (core, PubSubClient, nff library)…")
    ok, msg = installer.ensure_onboarding_toolchain(emit=lambda l: click.echo(f"  {l}"))
    if not ok:
        click.echo(f"  Toolchain setup failed: {msg}")
        click.echo("  Fix the above and re-run `nff init`, or install manually:")
        click.echo(
            "    arduino-cli core install esp32:esp32 --additional-urls "
            "https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json"
        )
        return

    click.echo("\nCompiling onboarding firmware…")
    compile_stream = toolchain.stream_compile(sketch_dir, fqbn)
    for line in compile_stream:
        click.echo(f"  {line}")
    if compile_stream.returncode != 0:
        click.echo(
            "  Compile failed. Onboarding firmware needs the ESP32 core and the nff "
            "Arduino library installed in arduino-cli."
        )
        return

    click.echo("\nFlashing your board…")
    upload_stream = toolchain.stream_upload(sketch_dir, fqbn, device.port)
    for line in upload_stream:
        click.echo(f"  {line}")
    if upload_stream.returncode != 0:
        click.echo("  Flashing failed — check the cable and that the port isn't in use.")
        return

    # Saved firmware runs at 115200; keep config in sync for `nff monitor`.
    config.set_default_device(device.port, device.board, fqbn, _BOOTSTRAP_BAUD)

    click.echo("\nWaiting for your device to connect to the platform…")
    claimed = False
    try:
        for line, result in bootstrap.watch_for_claim(device.port, _BOOTSTRAP_BAUD, timeout_s=150):
            click.echo(f"  {line}")
            if result:
                claimed = True
                break
    except bootstrap.BootstrapError as exc:
        click.echo(f"  (serial read ended: {exc})")

    frontend = config.get_diagnosis_config().get("frontend_url") or "https://nanoforgeflow.com"
    if claimed:
        click.echo("\n✓ Success! Your device is connected and claimed.")
        click.echo(f"  See it in your dashboard: {frontend}")
    else:
        click.echo("\nYour board was flashed and is announcing itself.")
        click.echo(f"  It should appear in your dashboard shortly: {frontend}")
        click.echo("  If it stays offline, re-check the WiFi password and the board's internet access.")


@click.command()
@click.option("--port", default=None)
@click.option("--baud", default=9600, type=int)
@click.option("--force", is_flag=True)
def init(port, baud, force):
    """Interactive setup — detect board and configure nff."""
    click.echo("Welcome to nff init!\n")
    click.echo("  1) Real board (USB)")
    click.echo("  2) Wokwi simulation")
    choice = click.prompt("Select mode", type=click.Choice(["1", "2"]))

    if choice == "1":
        click.pause("\nPlug your board into a USB port, then press any key…")
        devices = boards_module.list_devices()
        if devices:
            click.echo("\nDetected boards:")
            for i, d in enumerate(devices, 1):
                click.echo(f"  {i}) {d.board} on {d.port}")
            if len(devices) == 1:
                selected = devices[0]
            else:
                idx = click.prompt("Select board", type=int, default=1) - 1
                selected = devices[max(0, min(idx, len(devices) - 1))]
            resolved_port = port or selected.port
            board_name, fqbn = selected.board, selected.fqbn
            config.set_default_device(resolved_port, board_name, fqbn, baud)
        else:
            if not port:
                port = click.prompt("No boards detected. Enter port manually")
            resolved_port = port
            board_name = click.prompt("Board name")
            fqbn = click.prompt("Board FQBN (e.g. esp32:esp32:esp32)")
            config.set_default_device(resolved_port, board_name, fqbn, baud)

        if not toolchain.find_arduino_cli():
            click.echo("\narduino-cli not found — installing…")
            try:
                installer.install()
            except Exception as exc:
                click.echo(f"Warning: could not install arduino-cli: {exc}")

        device = types.SimpleNamespace(port=resolved_port, board=board_name, fqbn=fqbn)
        if fqbn.startswith("esp32") and click.confirm(
            "\nConnect this device to the nff platform now?", default=True
        ):
            _onboard_platform(device)

    else:
        click.echo("\nAvailable boards:")
        for i, (name, fqbn) in enumerate(_SIM_BOARDS, 1):
            click.echo(f"  {i}) {name} ({fqbn})")
        idx = click.prompt("Select board", type=int, default=5) - 1
        name, fqbn = _SIM_BOARDS[max(0, min(idx, len(_SIM_BOARDS) - 1))]
        config.set_default_device("", name, fqbn, 9600)

    _register_mcp()
    click.echo("\n✓ nff configured! Run `nff doctor` to verify your setup.")
