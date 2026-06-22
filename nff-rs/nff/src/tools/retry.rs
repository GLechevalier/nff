//! Transient-failure classification and bounded retry for toolchain commands.
//!
//! A bench loop driven by an agent cannot tell a transient toolchain hiccup
//! (arduino-cli EINVAL "Invalid argument", a Windows file lock on the build dir,
//! a serial port re-enumerating after an auto-reset, a slow cold build timing
//! out) apart from a genuine compile error. The first class is survivable by
//! simply retrying; the second is authoritative and must fail fast so the agent
//! fixes the *code*, not the *environment*.
//!
//! Faithful port of the Python `nff/tools/retry.py`. This module has no
//! dependency on `toolchain` so `serial.rs` can reuse [`is_transient`].

use std::sync::OnceLock;
use std::time::Duration;

use regex::Regex;

/// Up to (backoff.len() + 1) attempts; the slice values are the pauses before
/// each retry. Compile uses this; upload uses a longer slice (board re-enumerates).
pub const DEFAULT_BACKOFF: &[f64] = &[1.0, 3.0];

/// A result that the retry driver can branch on (mirrors the Python duck-typed
/// `.success` / `.output`). Implemented for `toolchain::RunResult`.
pub trait RetryOutcome {
    fn succeeded(&self) -> bool;
    fn text(&self) -> String;
}

fn compile_error_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    // A genuine *compile* error is authoritative — never retried.
    RE.get_or_init(|| Regex::new(r"(?i)\berror:").unwrap())
}

fn strong_transient_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    // STRONG signals: serial-port / upload / filesystem faults that never appear
    // in a genuine compile error, so they win even when arduino-cli also prints a
    // generic "uploading error:" line on the same failure.
    RE.get_or_init(|| {
        Regex::new(concat!(
            r"(?i)could not open port|cannot open|failed to open",
            r"|the port is busy|resource busy|device or resource busy",
            r"|access is denied",
            r"|the process cannot access the file",
            r"|failed uploading|wrong boot mode|no serial data received",
            r"|port .* doesn't exist|serialexception",
        ))
        .unwrap()
    })
}

fn weak_transient_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    // WEAK signals: ambiguous phrases that could appear inside a real compiler
    // diagnostic — so a bare "error:" overrides them.
    RE.get_or_init(|| {
        Regex::new(r"(?i)invalid argument|permission denied|timed out|timeout").unwrap()
    })
}

/// True if the output carries a genuine compiler `error:` diagnostic.
pub fn is_compile_error(output: &str) -> bool {
    compile_error_re().is_match(output)
}

/// Classify a failure as a transient (retryable) toolchain/OS hiccup.
///
/// A strong serial/upload/filesystem signal always wins — those never occur in a
/// genuine compile error, and arduino-cli prints a misleading generic
/// "uploading error:" on exactly those failures. Otherwise a real compiler
/// `error:` fails fast, and only then do the weaker ambiguous phrases count.
pub fn is_transient(output: &str) -> bool {
    if output.is_empty() {
        return false;
    }
    if strong_transient_re().is_match(output) {
        return true;
    }
    if is_compile_error(output) {
        return false;
    }
    weak_transient_re().is_match(output)
}

/// Production sleep; tests pass a no-op closure instead.
pub fn real_sleep(secs: f64) {
    std::thread::sleep(Duration::from_secs_f64(secs));
}

fn delay_for(attempt_index: usize, backoff: &[f64]) -> f64 {
    backoff[attempt_index.min(backoff.len().saturating_sub(1))]
}

/// Run a non-streaming `attempt` (returning a [`RetryOutcome`]) with bounded
/// retry. Retries only while the failure classifies as transient and attempts
/// remain; returns the last result on success, exhaustion, or a non-transient
/// (genuine compile) failure. `on_retry(attempt_no, first_line)` fires before
/// each sleep; `sleep` is injectable so tests never actually wait.
pub fn run_with_retry<T, F>(
    mut attempt: F,
    backoff: &[f64],
    mut on_retry: impl FnMut(usize, &str),
    sleep: impl Fn(f64),
) -> T
where
    T: RetryOutcome,
    F: FnMut() -> T,
{
    let retries = backoff.len();
    for i in 0..=retries {
        let result = attempt();
        if result.succeeded() || i == retries || !is_transient(&result.text()) {
            return result;
        }
        let text = result.text();
        let first = text.lines().next().unwrap_or("");
        on_retry(i + 1, first);
        sleep(delay_for(i, backoff));
    }
    unreachable!("loop returns on i == retries")
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Out {
        ok: bool,
        msg: String,
    }
    impl RetryOutcome for Out {
        fn succeeded(&self) -> bool {
            self.ok
        }
        fn text(&self) -> String {
            self.msg.clone()
        }
    }

    #[test]
    fn strong_transient_signals_are_transient() {
        for s in [
            "Invalid argument",
            "esptool: Resource busy",
            "Access is denied",
            "could not open port 'COM7'",
            "The process cannot access the file because it is being used",
            "Command timed out after 600s",
            "Failed uploading: wrong boot mode detected",
            "Port COM5 doesn't exist",
        ] {
            assert!(is_transient(s), "expected transient: {s}");
        }
    }

    #[test]
    fn compile_errors_are_not_transient() {
        for s in [
            "sketch.ino:4:1: error: expected ';' before '}'",
            "linker error: undefined reference to foo",
            "",
            "Sketch uses 1000 bytes",
        ] {
            assert!(!is_transient(s), "expected NOT transient: {s}");
        }
    }

    #[test]
    fn weak_signal_does_not_beat_compile_error() {
        let mixed = "error: expected ';'\nthat operation timed out";
        assert!(is_compile_error(mixed));
        assert!(!is_transient(mixed));
    }

    #[test]
    fn strong_signal_beats_compile_error() {
        // arduino-cli prints "uploading error:" on a transient upload failure.
        let mixed = "Failed uploading: uploading error: exit status 2";
        assert!(is_compile_error(mixed));
        assert!(is_transient(mixed));
    }

    #[test]
    fn real_bad_port_upload_is_transient() {
        let out =
            "A fatal error occurred: Could not open COM99, the port is busy or doesn't exist.\n\
                   (could not open port 'COM99': FileNotFoundError(2, ...))\n\
                   Failed uploading: uploading error: exit status 2";
        assert!(is_transient(out));
    }

    #[test]
    fn run_with_retry_persistent_transient_exhausts() {
        let mut n = 0;
        let r = run_with_retry(
            || {
                n += 1;
                Out {
                    ok: false,
                    msg: "Invalid argument".into(),
                }
            },
            DEFAULT_BACKOFF,
            |_, _| {},
            |_| {},
        );
        assert!(!r.succeeded());
        assert_eq!(n, 3); // 2 retries -> 3 attempts
    }

    #[test]
    fn run_with_retry_compile_error_fails_fast() {
        let mut n = 0;
        let r = run_with_retry(
            || {
                n += 1;
                Out {
                    ok: false,
                    msg: "error: nope".into(),
                }
            },
            DEFAULT_BACKOFF,
            |_, _| {},
            |_| {},
        );
        assert!(!r.succeeded());
        assert_eq!(n, 1);
    }

    #[test]
    fn run_with_retry_transient_then_success() {
        let mut n = 0;
        let r = run_with_retry(
            || {
                n += 1;
                if n == 1 {
                    Out {
                        ok: false,
                        msg: "Invalid argument".into(),
                    }
                } else {
                    Out {
                        ok: true,
                        msg: "ok".into(),
                    }
                }
            },
            DEFAULT_BACKOFF,
            |_, _| {},
            |_| {},
        );
        assert!(r.succeeded());
        assert_eq!(n, 2);
    }

    #[test]
    fn run_with_retry_fires_on_retry() {
        let mut n = 0;
        let mut seen: Vec<(usize, String)> = Vec::new();
        run_with_retry(
            || {
                n += 1;
                if n == 1 {
                    Out {
                        ok: false,
                        msg: "Invalid argument".into(),
                    }
                } else {
                    Out {
                        ok: true,
                        msg: "ok".into(),
                    }
                }
            },
            DEFAULT_BACKOFF,
            |attempt, line| seen.push((attempt, line.to_string())),
            |_| {},
        );
        assert_eq!(seen, vec![(1, "Invalid argument".to_string())]);
    }
}
