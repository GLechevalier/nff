"""Client for the nff platform onboarding endpoints (nff-diagnosis backend).

Talks to the user-facing API at config.diagnosis.server_url using the stored login
JWT — never the internal fleet secret. Resolves the user's default project and returns
a bootstrap credentials.h to bake into the device firmware.
"""

import requests

from nff import config
from nff.tools import auth as auth_tools


class ProvisioningError(Exception):
    pass


def provision_batch(count: int | None = None) -> dict:
    """Resolve the user's project and fetch a bootstrap credentials.h.

    Refreshes the access token once on a 401, then retries. Returns the backend's
    JSON: {project_id, batch_id, reused, credentials_h}.
    """
    cfg = config.get_diagnosis_config()
    server_url = (cfg.get("server_url") or "").rstrip("/")
    access = cfg.get("access_token")
    refresh = cfg.get("refresh_token")
    if not server_url:
        raise ProvisioningError("no server configured — run `nff auth login`")
    if not access:
        raise ProvisioningError("not authenticated — run `nff auth login`")

    body = {"count": count} if count is not None else {}

    def _post(token: str) -> requests.Response:
        return requests.post(
            f"{server_url}/api/provision-batch",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=40,
        )

    try:
        resp = _post(access)
        if resp.status_code == 401 and refresh:
            new = auth_tools.refresh_tokens(server_url, refresh)
            config.set_diagnosis_tokens(new.access_token, new.refresh_token)
            resp = _post(new.access_token)
    except requests.RequestException as exc:
        raise ProvisioningError(f"could not reach {server_url}: {exc}")

    if resp.status_code != 200:
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        raise ProvisioningError(f"provisioning failed ({resp.status_code}): {detail}")

    data = resp.json()
    if not data.get("credentials_h"):
        raise ProvisioningError("provisioning returned no credentials")
    return data
