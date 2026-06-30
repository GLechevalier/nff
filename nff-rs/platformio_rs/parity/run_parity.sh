#!/usr/bin/env bash
# Run the vendored PlatformIO test suite through the CliRunner subprocess shim.
#
# Usage:
#   ./run_parity.sh baseline          # against the Python `pio` on PATH
#   ./run_parity.sh rust              # against target/{debug,release}/pio-rs
#   PIO_BIN=/custom/pio ./run_parity.sh raw [extra pytest args...]
#
# Scope (env PARITY_SCOPE, default "offline"):
#   offline  — curated subset that needs NO network/toolchain downloads. This is
#              the M0 baseline gate: it proves the subprocess shim faithfully
#              reproduces Click's in-process behaviour.
#   full     — everything except skip_ci + test_examples (matches upstream
#              `tox -e testcore`); requires network and is slow.
#
# Network/registry/email tests are excluded (`-k "not skip_ci"`), as is the
# heavyweight examples suite — matching upstream's `tox -e testcore`.

set -euo pipefail

# Curated offline subset (relative to platformio-core/tests). These passed green
# on the Python `pio` baseline with no network access; the rest pull packages
# from the registry and are gated to milestones M2+.
OFFLINE_TESTS=(
  project
  misc
  commands/test_settings.py
  commands/test_boards.py
  package/test_meta.py
  package/test_manifest.py
  package/test_pack.py
)

# Tests that CANNOT run through the subprocess shim: they monkeypatch in-process
# Python state and *then* invoke the CLI, so a fresh subprocess never sees the
# patch. These are reimplemented as Rust unit tests in the relevant milestone
# (the feature they cover is noted). Applied as --deselect in every scope.
SHIM_INCOMPATIBLE=(
  # patches maintenance.__version__ + upgrade.VERSION, then runs `pio platform list`
  # to assert the "new version available" banner -> upgrade-notification logic (M5/M3).
  "misc/test_maintenance.py::test_check_pio_upgrade"
  # hardcodes proc.exec_command(["pio","--help"]) -> ignores $PIO_BIN entirely, so it
  # can't target pio-rs. Reimplement as a Rust test: `pio-rs --help` prints usage (M0/M1).
  "misc/test_misc.py::test_platformio_cli"
)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS="$HERE/platformio-core/tests"
NFF_RS_ROOT="$(cd "$HERE/../.." && pwd)"   # nff-rs/

# Prefer the dedicated harness venv (isolated platformio install) over whatever
# `python` is on PATH, so the heavy/conflicting PlatformIO deps never leak into
# the workspace's shared .venv. Create it once with:
#   python -m venv parity/.venv-harness
#   parity/.venv-harness/Scripts/pip install platformio==6.1.19 jsondiff pytest
PY="python"
for cand in "$HERE/.venv-harness/Scripts/python.exe" "$HERE/.venv-harness/bin/python"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done

mode="${1:-baseline}"
shift || true

case "$mode" in
  baseline)
    # Default to the harness venv's pio, else whatever's on PATH.
    if [ -z "${PIO_BIN:-}" ]; then
      for cand in "$HERE/.venv-harness/Scripts/pio.exe" "$HERE/.venv-harness/bin/pio"; do
        if [ -x "$cand" ]; then PIO_BIN="$cand"; break; fi
      done
    fi
    PIO_BIN="${PIO_BIN:-$(command -v pio || true)}"
    ;;
  rust)
    if [ -x "$NFF_RS_ROOT/target/release/pio-rs" ]; then
      PIO_BIN="$NFF_RS_ROOT/target/release/pio-rs"
    else
      PIO_BIN="$NFF_RS_ROOT/target/debug/pio-rs"
    fi
    ;;
  raw)
    : "${PIO_BIN:?set PIO_BIN for raw mode}"
    ;;
  *)
    echo "unknown mode: $mode (use baseline|rust|raw)" >&2
    exit 2
    ;;
esac

if [ -z "${PIO_BIN:-}" ]; then
  echo "ERROR: no PIO_BIN resolved (is 'pio' installed / has pio-rs been built?)" >&2
  exit 1
fi

scope="${PARITY_SCOPE:-offline}"
echo "== parity run: mode=$mode scope=$scope PIO_BIN=$PIO_BIN =="
export PIO_BIN

targets=()
if [ "$scope" = "offline" ]; then
  for t in "${OFFLINE_TESTS[@]}"; do targets+=("$TESTS/$t"); done
else
  targets=("$TESTS")
fi

# Build a -k filter that drops skip_ci plus every shim-incompatible test (matched
# by its function name, which is unique across the suite). Using -k rather than
# --deselect avoids absolute-path nodeid mismatches on Windows/git-bash.
kfilter="not skip_ci"
for nid in "${SHIM_INCOMPATIBLE[@]}"; do
  fn="${nid##*::}"
  kfilter="$kfilter and not $fn"
done

exec "$PY" -m pytest \
  --rootdir "$HERE" \
  -c /dev/null \
  -p no:cacheprovider \
  -k "$kfilter" \
  --ignore "$TESTS/test_examples.py" \
  "$@" \
  "${targets[@]}"
