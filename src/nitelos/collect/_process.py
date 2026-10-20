"""One shared allowlisted subprocess runner for collectors (ADR-015, NIT-017).

Every collector that shells out (git in NIT-018, later others) MUST go through
:func:`run_allowed` instead of calling subprocess itself. The rules enforced
here: the requested argv must exactly equal one tuple in the caller-supplied
allowlist (no user-supplied fragment ever reaches argv; pass context through
``cwd``, never through path arguments); the executable is resolved with
``shutil.which`` (missing -> COLLECTOR_UNAVAILABLE); the shell is never used;
stdin is closed; the child environment is scrubbed to a minimal allowlist plus
the collector's explicit extras; a hard timeout kills the process
(-> COLLECTOR_TIMEOUT); captured output beyond the raw cap is an error
(-> COLLECTOR_OUTPUT_TOO_LARGE), never a silent truncation. Raw stdout/stderr
are returned to the caller only and are never logged.

Limitation (documented, deliberate): the raw cap is checked on the captured
output once the process has ended; a process that streams without exiting is
bounded by the timeout, which also kills. There is no streaming kill at the
byte cap.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from nitelos.collect import CollectorError, CollectorErrorCode

_BASE_ENV_KEYS = ("PATH",)
_WINDOWS_ENV_KEYS = ("SYSTEMROOT", "WINDIR")


def _scrubbed_env(extra_env: Mapping[str, str] | None) -> dict[str, str]:
    keys = _BASE_ENV_KEYS + (_WINDOWS_ENV_KEYS if os.name == "nt" else ())
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env["LC_ALL"] = "C"
    if extra_env:
        env.update(dict(extra_env))
    return env


def run_allowed(
    *,
    argv: Sequence[str],
    allowlist: tuple[tuple[str, ...], ...],
    timeout_s: float,
    max_raw_bytes: int,
    cwd: Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> tuple[bytes, bytes]:
    """Run one fixed, allowlisted argv and return (stdout, stderr) raw bytes.

    Raises :class:`~nitelos.collect.CollectorError` with COLLECTOR_CONFIG_INVALID
    for a non-allowlisted argv (before any process starts), COLLECTOR_UNAVAILABLE
    when the executable cannot be resolved, COLLECTOR_TIMEOUT after killing an
    overdue process, and COLLECTOR_OUTPUT_TOO_LARGE when the captured output
    exceeds ``max_raw_bytes``.
    """
    requested = tuple(argv)
    if not requested or requested not in {tuple(entry) for entry in allowlist}:
        raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    executable = shutil.which(requested[0])
    if executable is None:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    process: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603 - fixed allowlisted argv, scrubbed env, shell never used (ADR-015)
        [executable, *requested[1:]],
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_scrubbed_env(extra_env),
        cwd=cwd,
    )
    try:
        out, err = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise CollectorError(CollectorErrorCode.TIMEOUT) from None
    if len(out) + len(err) > max_raw_bytes:
        raise CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE)
    return out, err
