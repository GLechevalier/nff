"""Tests for nff.tools.daemon — background MCP server lifecycle."""

from unittest.mock import patch

from nff.tools import daemon


def test_is_running_false_when_port_closed():
    # An unused high port should not be open.
    assert daemon.is_running(port=59999) is False


def test_start_background_noops_when_already_running():
    with patch("nff.tools.daemon.is_running", return_value=True), \
         patch("nff.tools.daemon.subprocess.Popen") as mpopen:
        assert daemon.start_background() is True
    mpopen.assert_not_called()  # never tries to spawn a second server


def test_start_background_spawns_and_confirms():
    # First is_running() (the guard) is False, then True once the child binds.
    states = iter([False, True])
    with patch("nff.tools.daemon.is_running", side_effect=lambda *a, **k: next(states)), \
         patch("nff.tools.daemon.subprocess.Popen") as mpopen:
        assert daemon.start_background() is True
    mpopen.assert_called_once()
    cmd = mpopen.call_args[0][0]
    assert cmd[1:4] == ["-m", "nff", "mcp"]


def test_health_ok_false_when_unreachable():
    with patch("nff.tools.daemon.urllib.request.urlopen", side_effect=OSError("down")):
        assert daemon.health_ok(port=59999) is False
