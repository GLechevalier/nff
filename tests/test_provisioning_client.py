"""Tests for nff.tools.provisioning_client.provision_batch."""

from unittest.mock import MagicMock, patch

import pytest

from nff.tools import provisioning_client
from nff.tools.provisioning_client import ProvisioningError


def _resp(status, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.json.return_value = payload if payload is not None else {}
    return r


def _diag(**over):
    base = {
        "server_url": "https://api.test",
        "access_token": "acc",
        "refresh_token": "ref",
    }
    base.update(over)
    return base


def test_provision_batch_success():
    payload = {"project_id": "p1", "batch_id": "b1", "reused": False,
               "credentials_h": "// creds"}
    with patch("nff.tools.provisioning_client.config.get_diagnosis_config", return_value=_diag()), \
         patch("nff.tools.provisioning_client.requests.post", return_value=_resp(200, payload)) as mpost:
        data = provisioning_client.provision_batch()

    assert data["credentials_h"] == "// creds"
    # bearer header carries the stored access token
    assert mpost.call_args.kwargs["headers"]["Authorization"] == "Bearer acc"


def test_provision_batch_refreshes_on_401_then_retries():
    from nff.tools.auth import TokenResponse
    payload = {"credentials_h": "// creds", "project_id": "p", "batch_id": "b"}
    responses = [_resp(401), _resp(200, payload)]

    with patch("nff.tools.provisioning_client.config.get_diagnosis_config", return_value=_diag()), \
         patch("nff.tools.provisioning_client.requests.post", side_effect=responses) as mpost, \
         patch("nff.tools.provisioning_client.auth_tools.refresh_tokens",
               return_value=TokenResponse("acc2", "ref2")) as mref, \
         patch("nff.tools.provisioning_client.config.set_diagnosis_tokens") as mset:
        data = provisioning_client.provision_batch()

    assert data["credentials_h"] == "// creds"
    mref.assert_called_once()
    mset.assert_called_once_with("acc2", "ref2")
    # retry used the refreshed token
    assert mpost.call_args.kwargs["headers"]["Authorization"] == "Bearer acc2"


def test_provision_batch_raises_without_access_token():
    with patch("nff.tools.provisioning_client.config.get_diagnosis_config",
               return_value=_diag(access_token=None)):
        with pytest.raises(ProvisioningError, match="not authenticated"):
            provisioning_client.provision_batch()


def test_provision_batch_raises_without_server_url():
    with patch("nff.tools.provisioning_client.config.get_diagnosis_config",
               return_value=_diag(server_url="")):
        with pytest.raises(ProvisioningError, match="no server configured"):
            provisioning_client.provision_batch()


def test_provision_batch_raises_on_non_200():
    with patch("nff.tools.provisioning_client.config.get_diagnosis_config", return_value=_diag()), \
         patch("nff.tools.provisioning_client.requests.post",
               return_value=_resp(500, {"detail": "kaboom"})):
        with pytest.raises(ProvisioningError, match="kaboom"):
            provisioning_client.provision_batch()


def test_provision_batch_raises_on_missing_credentials():
    with patch("nff.tools.provisioning_client.config.get_diagnosis_config", return_value=_diag()), \
         patch("nff.tools.provisioning_client.requests.post",
               return_value=_resp(200, {"project_id": "p"})):
        with pytest.raises(ProvisioningError, match="no credentials"):
            provisioning_client.provision_batch()


def test_provision_batch_wraps_network_error():
    import requests
    with patch("nff.tools.provisioning_client.config.get_diagnosis_config", return_value=_diag()), \
         patch("nff.tools.provisioning_client.requests.post",
               side_effect=requests.RequestException("dns fail")):
        with pytest.raises(ProvisioningError, match="could not reach"):
            provisioning_client.provision_batch()
