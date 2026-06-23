# What's new in version 0.3.0 — PlatformIO backend in the shipped Rust binary (unreleased)

The board-universal **PlatformIO backend** — previously only in the Python prototype — is now ported into the shipped Rust binary (`nff-rs/`), so `pip install nff` users get it. **PlatformIO is now the default backend** in both implementations; the classic arduino-cli backend stays available via `NFF_BUILD_BACKEND=arduino` (or `build.backend` in `~/.nff/config.json`). See [Build backends](#build-backends).

### Carried over — four PlatformIO hardening fixes
- **Your own `platformio.ini` is respected.** A project that ships its own `platformio.ini` (custom partitions, PSRAM, build flags) is built as-is and never overwritten.
- **Multi-file sketches build.** A sketch folder with helper `.cpp`/`.h` files or multiple `.ino` tabs now copies every file into the build, not just the first.
- **First-build package flakes self-heal.** A transient PlatformIO `package-manager-ioerror` (or a half-installed framework surfacing as a missing `pins_arduino.h`) is classified as transient, and the broken platform is pruned + reinstalled on retry.
- **`nff clean` clears PlatformIO output too** (`nff_pio` temp root, including the heavy `.pio/build`), not just the arduino temp dir.

### Tooling
- **`nff doctor`** shows the active backend and checks PlatformIO Core; under the PlatformIO backend a missing arduino-cli/esptool is informational, not a failure.
- **`nff install-deps`** auto-installs PlatformIO Core.
- **`nff init --backend <platformio|arduino>`** persists the backend and seeds the PlatformIO board id from the detected device.

> **Note:** `flash --sim` (Wokwi) is not yet wired for the PlatformIO backend — use `NFF_BUILD_BACKEND=arduino` to simulate. Verified end-to-end against real PlatformIO + ESP32; 105 cargo tests pass and `cargo clippy -- -D warnings` is clean.

---

## What's new in v0.2.20 — the "reliable install" release

This release is about making the bench loop **survive on its own**: the previous version (`0.2.19`) worked when a human was watching, but transient toolchain hiccups would surface as hard failures — fatal for an agent driving the loop unattended. It also brings the **Rust binary to full parity** so it becomes the shipped artifact, and adds first-run onboarding so a fresh machine can actually compile.

### Reliability — corrected
- **Transient failures are now retried, not fatal.** A new classifier tells a *transient* toolchain hiccup (arduino-cli `EINVAL` / "Invalid argument", a Windows build-dir file lock, a serial port re-enumerating after auto-reset, a slow build timing out) apart from a *genuine* compile error. Transient failures retry with backoff; real compile errors still fail fast. Previously **any** of these killed `compile`/`flash` outright.
- **Cold builds no longer time out.** The compile timeout was a flat 120 s — a first-time ESP32 build routinely exceeds that and died with "Command timed out". Compile now gets 600 s, upload 180 s, and a timeout is treated as retryable rather than a hard error.
- **Upload-failure misclassification fixed.** arduino-cli prints `uploading error:` on a transient port failure; the naive classifier mistook that for a compile error and refused to retry. A strong serial/upload signal (`failed uploading`, `could not open port`, `the port is busy`) now correctly wins over the bare word `error:`.
- **Serial is resilient.** `serial_read`/`serial_write`/`reset_device` retry transient port faults, and the serial monitor no longer crashes with a raw traceback when a device is unplugged mid-stream — it reports the error cleanly.
- **Stale-library guard.** "Flash to test my fix" could silently build the *old* library. `flash` and `doctor` now warn when a local `nff-sdk-c` checkout is newer than the synced Arduino library, so you never ship stale firmware unknowingly.

### Install / onboarding — added
- **`nff init` now installs the full build toolchain** (the `esp32` core, `PubSubClient`, and the `nff` Arduino library) on first run, so a freshly-set-up machine can compile a sketch that does `#include <nff.h>` without manual `arduino-cli` steps.
- **`doctor` gained an `nff lib` check** reporting the synced library version and flagging staleness.

### New capabilities
- **`nff pi probe`** — detect a directly-connected Raspberry Pi and tell you exactly which link in the chain is missing (cable/power → IP → SSH), via ARP-OUI matching, mDNS, and a TCP/22 probe (with an optional `--sweep`). Groundwork for running nff-pentester on a Pi node.

### Rust port → the shipped binary
- The Rust implementation in `nff-rs/` reached **full feature parity** with the Python package (all of the above, plus the existing CLI/MCP/OAuth surface) and is now the release artifact. Version bumped to **0.2.20** across the Rust crate and the Python package, which stay in lockstep. The Rust port is no longer "paused".

### Quality
- New automated tests across both implementations (retry classifier, serial retry, library sync/staleness, onboarding, `pi`, init). Rust passes `cargo clippy -- -D warnings` and the full `cargo test` suite, and the whole loop (compile → flash → monitor, plus the transient-retry path) was **verified on real ESP32 hardware**.

> **Upgrade note:** the on-disk library marker (`.nff_sync_meta`) gains `version`/`synced_at` fields; libraries synced by `0.2.19` will show `?` in `nff doctor` until the next `nff install-deps`/`nff init` re-syncs them. No action required.

