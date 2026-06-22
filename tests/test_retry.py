"""Tests for nff.tools.retry — classification and bounded retry drivers."""

from dataclasses import dataclass

import pytest

from nff.tools import retry


@dataclass
class _Result:
    success: bool
    output: str


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Invalid argument",
    "esptool: Resource busy",
    "Access is denied",
    "could not open port 'COM7'",
    "The process cannot access the file because it is being used",
    "Command timed out after 600s: arduino-cli",
    "Failed uploading: wrong boot mode detected",
    "Port COM5 doesn't exist",
])
def test_is_transient_true(text):
    assert retry.is_transient(text)


@pytest.mark.parametrize("text", [
    "sketch.ino:4:1: error: expected ';' before '}'",
    "linker error: undefined reference to foo",
    "",
    "Sketch uses 1000 bytes",
])
def test_is_transient_false(text):
    assert not retry.is_transient(text)


def test_weak_transient_does_not_beat_compile_error():
    # A bare "error:" overrides ambiguous (weak) phrases — fail fast.
    mixed = "error: expected ';'\nthat operation timed out"
    assert retry.is_compile_error(mixed)
    assert not retry.is_transient(mixed)


def test_strong_transient_beats_compile_error():
    # Strong I/O signals win even though arduino-cli prints "uploading error:".
    mixed = "Failed uploading: uploading error: exit status 2"
    assert retry.is_compile_error(mixed)  # bare "error:" is present...
    assert retry.is_transient(mixed)      # ...but the upload signal wins


def test_real_upload_to_missing_port_is_transient():
    # Regression: the exact arduino-cli/esptool text seen flashing to a bad port.
    out = (
        "A fatal error occurred: Could not open COM99, the port is busy or doesn't exist.\n"
        "(could not open port 'COM99': FileNotFoundError(2, ...))\n"
        "Failed uploading: uploading error: exit status 2"
    )
    assert retry.is_transient(out)


# ---------------------------------------------------------------------------
# run_with_retry
# ---------------------------------------------------------------------------

def _driver(results):
    seq = iter(results)
    calls = {"n": 0}

    def attempt():
        calls["n"] += 1
        return next(seq)

    return attempt, calls


def test_run_with_retry_persistent_transient_exhausts():
    attempt, calls = _driver([_Result(False, "Invalid argument")] * 3)
    out = retry.run_with_retry(attempt, sleep=lambda _s: None)
    assert not out.success
    assert calls["n"] == 3  # retries=2 -> 3 attempts


def test_run_with_retry_compile_error_fails_fast():
    attempt, calls = _driver([_Result(False, "error: nope")] * 3)
    out = retry.run_with_retry(attempt, sleep=lambda _s: None)
    assert not out.success
    assert calls["n"] == 1


def test_run_with_retry_transient_then_success():
    attempt, calls = _driver([
        _Result(False, "Invalid argument"),
        _Result(True, "ok"),
    ])
    out = retry.run_with_retry(attempt, sleep=lambda _s: None)
    assert out.success
    assert calls["n"] == 2


def test_run_with_retry_invokes_on_retry():
    attempt, _ = _driver([_Result(False, "Invalid argument"), _Result(True, "ok")])
    seen = []
    retry.run_with_retry(
        attempt, sleep=lambda _s: None, on_retry=lambda n, why: seen.append((n, why))
    )
    assert seen == [(1, "Invalid argument")]


# ---------------------------------------------------------------------------
# stream_with_retry
# ---------------------------------------------------------------------------

class _FakeStream:
    def __init__(self, lines, returncode):
        self._lines = lines
        self.returncode = returncode

    def __iter__(self):
        yield from self._lines


def _run_attempt(stream, emit):
    captured = []
    for line in stream:
        emit(line)
        captured.append(line)
    return (stream.returncode or 0), "\n".join(captured)


def test_stream_with_retry_recovers():
    streams = iter([
        _FakeStream(["Invalid argument"], 1),
        _FakeStream(["done"], 0),
    ])
    emitted = []
    rc = retry.stream_with_retry(
        lambda: next(streams), emitted.append, _run_attempt, sleep=lambda _s: None
    )
    assert rc == 0
    assert any("retrying" in line for line in emitted)


def test_stream_with_retry_compile_error_fails_fast():
    calls = {"n": 0}

    def make():
        calls["n"] += 1
        return _FakeStream(["error: boom"], 1)

    rc = retry.stream_with_retry(
        make, lambda _l: None, _run_attempt, sleep=lambda _s: None
    )
    assert rc == 1
    assert calls["n"] == 1
