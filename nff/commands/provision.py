"""nff provision — fleet enrollment provisioning.

`nff provision batch` creates ONE shared bootstrap credential for a whole batch of devices
(DEVICE_OWNERSHIP_DESIGN.md §8). You flash the resulting credentials.h into a single firmware
image and push it to the entire batch with one OTA: every device then announces itself, shows up
in the dashboard Enroll tab, and — once accepted — automatically rolls over to a unique per-device
certificate. No per-device credential generation, no codes.
"""

import os

import click
import requests


def _fleet(fleet_url, secret):
    fleet_url = fleet_url or os.environ.get("NFF_FLEET_URL")
    secret = secret or os.environ.get("NFF_FLEET_SECRET")
    if not fleet_url:
        raise click.UsageError("fleet URL required: pass --fleet-url or set NFF_FLEET_URL")
    if not secret:
        raise click.UsageError("fleet secret required: pass --secret or set NFF_FLEET_SECRET")
    return fleet_url.rstrip("/"), secret


@click.group()
def provision():
    """Provision devices for fleet enrollment."""


@provision.command("batch")
@click.option("--project", "project_id", required=True, help="Target project id (uuid).")
@click.option("--count", type=int, default=None,
              help="Expected batch size. The server rejects enrollments beyond this as a "
                   "cloned-credential anomaly. Omit for no hard quota.")
@click.option("--out", "out_path", type=click.Path(dir_okay=False), default="credentials.h",
              help="Where to write the shared bootstrap credentials.h (default: ./credentials.h).")
@click.option("--fleet-url", default=None, help="nff-fleet base URL (or env NFF_FLEET_URL).")
@click.option("--secret", default=None, help="X-Fleet-Secret (or env NFF_FLEET_SECRET).")
def batch(project_id, count, out_path, fleet_url, secret):
    """Create a batch bootstrap credential and write its shared credentials.h.

    Build ONE firmware image with this header and flash/OTA the whole batch. The credential is
    valid for 24h; unclaimed devices are rotated automatically after that.
    """
    fleet_url, secret = _fleet(fleet_url, secret)
    body = {"project_id": project_id}
    if count is not None:
        body["count"] = count

    try:
        resp = requests.post(
            f"{fleet_url}/internal/provision-batch",
            headers={"X-Fleet-Secret": secret},
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise click.ClickException(f"could not reach fleet at {fleet_url}: {exc}")

    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("error", detail)
        except Exception:
            pass
        raise click.ClickException(f"fleet returned {resp.status_code}: {detail}")

    data = resp.json()
    header = data.get("bootstrap_header")
    if not header:
        raise click.ClickException("fleet did not return the bootstrap header content")

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header)

    click.echo(f"OK: batch {data['batch_id']} created for project {project_id}")
    click.echo(f"  credentials.h written to {out_path}")
    click.echo(f"  valid {data.get('expires_in_hours', 24)}h"
               + (f", quota {count} device(s)" if count else ", no quota"))
    click.echo("  build ONE image with this header and flash/OTA the whole batch; "
               "accept devices in the dashboard Enroll tab.")
