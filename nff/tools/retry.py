"""Transient-failure classification and bounded retry for toolchain commands.

A bench loop driven by an agent cannot tell a transient toolchain hiccup
(arduino-cli EINVAL "Invalid argument", a Windows file lock on the build dir,
a serial port re-enumerating after an auto-reset, a slow cold build timing out)
apart from a genuine compile error. The first class is survivable by simply
retrying; the second is authoritative and must fail fast so the agent fixes the
*code* and not the *environment*.

This module is deliberately free of any dependency on ``toolchain`` so that
``serial.py`` can reuse :func:`is_transient` without a circular import. The retry
drivers take the runnable as a callable and accept an injectable ``sleep`` so
tests never actually wait.
"""

from __future__ import annotations

import re
import time
from typing import Callable, Optional, Tuple

# Up to (retries + 1) attempts; the pauses before attempts 2 and 3.
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF: Tuple[float, ...] = (1.0, 3.0)

# A genuine *compile* error is authoritative — never retried.
_COMPILE_ERROR = re.compile(r"\berror:", re.IGNORECASE)

# STRONG transient signals: serial-port / upload / filesystem faults that never
# appear in a genuine *compile* error, so they win even when arduino-cli also
# prints a generic "uploading error:" line on the same failure.
_STRONG_TRANSIENT = re.compile(
    r"could not open port|cannot open|failed to open"
    r"|the port is busy|resource busy|device or resource busy"
    r"|access is denied"                       # Win32 port still held
    r"|the process cannot access the file"     # Win build-dir file lock
    r"|failed uploading|wrong boot mode|no serial data received"
    r"|port .* doesn't exist|serialexception",
    re.IGNORECASE,
)

# WEAK transient signals: ambiguous phrases that could, in principle, appear
# inside a real compiler diagnostic — so a bare "error:" overrides them.
_WEAK_TRANSIENT = re.compile(
    r"invalid argument"                        # EINVAL on COM re-enumeration
    r"|permission denied"
    r"|timed out|timeout",
    re.IGNORECASE,
)


def is_compile_error(output: str) -> bool:
    """True if the output carries a genuine compiler ``error:`` diagnostic."""
    return bool(_COMPILE_ERROR.search(output or ""))


def is_transient(output: str) -> bool:
    """Classify a failure as a transient (retryable) toolchain/OS hiccup.

    A strong serial/upload/filesystem signal always wins — those never occur in
    a genuine compile error, and arduino-cli prints a misleading generic
    "uploading error:" on exactly those failures. Otherwise a real compiler
    ``error:`` fails fast, and only then do the weaker ambiguous phrases count.
    """
    if not output:
        return False
    if _STRONG_TRANSIENT.search(output):
        return True
    if is_compile_error(output):
        return False
    return bool(_WEAK_TRANSIENT.search(output))


def _delay_for(attempt_index: int, backoff: Tuple[float, ...]) -> float:
    return backoff[min(attempt_index, len(backoff) - 1)]


def run_with_retry(
    attempt: Callable[[], "object"],
    *,
    classify: Callable[[str], bool] = is_transient,
    retries: int = DEFAULT_RETRIES,
    backoff: Tuple[float, ...] = DEFAULT_BACKOFF,
    on_retry: Optional[Callable[[int, str], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
):
    """Run a non-streaming ``attempt`` (returning a ``RunResult``) with retry.

    ``attempt`` must return an object with ``.success`` (bool) and ``.output``
    (str). Retries only while ``classify(output)`` is True and attempts remain;
    returns the last result on success, exhaustion, or a non-transient failure.
    """
    result = None
    for i in range(retries + 1):
        result = attempt()
        if result.success:
            return result
        if i == retries or not classify(result.output):
            return result
        if on_retry is not None:
            first = result.output.splitlines()[0] if result.output else ""
            on_retry(i + 1, first)
        sleep(_delay_for(i, backoff))
    return result


def stream_with_retry(
    make_stream: Callable[[], "object"],
    emit: Callable[[str], None],
    run_attempt: Callable[["object", Callable[[str], None]], Tuple[int, str]],
    *,
    classify: Callable[[str], bool] = is_transient,
    retries: int = DEFAULT_RETRIES,
    backoff: Tuple[float, ...] = DEFAULT_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run a live-streaming command with retry, preserving the echo UX.

    ``make_stream`` builds a fresh (single-use) stream per attempt; ``run_attempt``
    consumes one stream, echoing each line via ``emit`` and returning
    ``(returncode, captured_output)``. On a transient non-zero result an explicit
    banner is emitted and a fresh stream is started. Returns the final returncode.
    """
    rc = 0
    for i in range(retries + 1):
        rc, out = run_attempt(make_stream(), emit)
        if rc == 0:
            return 0
        if i == retries or not classify(out):
            return rc
        delay = _delay_for(i, backoff)
        emit(
            f"[nff] transient failure (rc={rc}); retrying in {delay:.0f}s "
            f"(attempt {i + 2}/{retries + 1})…"
        )
        sleep(delay)
    return rc
