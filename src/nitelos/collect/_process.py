"""One shared allowlisted subprocess runner for collectors (ADR-015, NIT-017).

Every collector that shells out (git in NIT-018, later others) MUST go through
:func:`run_allowed` instead of calling subprocess itself. The rules enforced
here:

- **Allowlist**: the requested argv must exactly equal one tuple in the
  caller-supplied allowlist (no user-supplied fragment ever reaches argv; pass
  context through ``cwd``, never through path arguments). ``argv[0]`` must be a
  bare name or an absolute path; a relative path with separators is rejected.
- **Executable resolution** (review finding 3): bare names resolve ONLY
  against absolute ``PATH`` entries — never the current directory, never a
  relative ``PATH`` entry — and the resolved executable must be absolute.
  ``.bat``/``.cmd`` targets are rejected outright (they are shell programs).
  A name that does not resolve maps to COLLECTOR_UNAVAILABLE.
- **No shell**; stdin is closed; the child environment is scrubbed to a
  minimal allowlist (PATH, SYSTEMROOT/WINDIR on Windows, LC_ALL=C) plus the
  collector's explicit extras.
- **Bounded memory** (review finding 2a): stdout and stderr are read
  incrementally by reader threads with a running byte count; as soon as the
  combined output exceeds ``max_raw_bytes`` the whole process tree is killed
  and COLLECTOR_OUTPUT_TOO_LARGE is raised — never silent truncation, and
  never unbounded buffering until the timeout.
- **Whole-tree kill** (review finding 2b): the deadline covers process exit
  AND both pipes reaching EOF, so a grandchild holding inherited pipes (the
  ``Git\\cmd\\git.exe`` shim's real git, a test double) cannot extend the
  wait. The kill reaches descendants even after the direct child has exited:
  POSIX runs the child as its own session (``start_new_session``) and kills
  the process group (the group outlives its leader); Windows puts the child in
  a Job Object with KILL_ON_JOB_CLOSE (falling back to ``taskkill /T`` on the
  child pid if the job could not be created or assigned while it was still
  alive). The post-kill reap is bounded (2 s wait, 1 s reader joins); a corpse
  that survives even the tree kill cannot hang the runner, though it may
  briefly outlive it. Pipes whose readers never drained are leaked on purpose
  (closing them under a blocked reader would deadlock).
- Raw output is returned to the caller only (with the exit code) and is never
  logged. An ``OSError`` from process creation (bad cwd, exec format error)
  maps to COLLECTOR_UNAVAILABLE.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO, NamedTuple

from nitelos.collect import CollectorError, CollectorErrorCode

_BASE_ENV_KEYS = ("PATH",)
_WINDOWS_ENV_KEYS = ("SYSTEMROOT", "WINDIR")
_WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
    subprocess, "CREATE_NO_WINDOW", 0
)
_READ_CHUNK = 65_536
_POLL_INTERVAL_S = 0.02
_REAP_TIMEOUT_S = 2.0
_JOIN_TIMEOUT_S = 1.0
_TASKKILL_TIMEOUT_S = 5.0


class ProcessOutput(NamedTuple):
    """Raw captured output plus the child's exit code (review finding 8)."""

    stdout: bytes
    stderr: bytes
    returncode: int  # -1 when the process could not be reaped after the kill


def _scrubbed_env(extra_env: Mapping[str, str] | None) -> dict[str, str]:
    keys = _BASE_ENV_KEYS + (_WINDOWS_ENV_KEYS if os.name == "nt" else ())
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env["LC_ALL"] = "C"
    if extra_env:
        env.update(dict(extra_env))
    return env


def _resolve_executable(name: str) -> str | None:
    """Resolve an allowlisted argv[0] safely; None means COLLECTOR_UNAVAILABLE.

    Absolute names are used as-is when the file exists. Bare names search only
    ABSOLUTE PATH entries (never the cwd, never relative entries). ``.bat`` and
    ``.cmd`` targets are always rejected (shell programs).
    """
    if not name:
        return None
    lowered = name.lower()
    if lowered.endswith((".bat", ".cmd")):
        return None
    candidate = Path(name)
    if candidate.is_absolute():
        return name if candidate.is_file() else None
    for entry in os.environ.get("PATH", os.defpath).split(os.pathsep):
        directory = Path(entry)
        if not directory.is_absolute():
            continue  # relative PATH entries (including "") are never searched
        names = (name, f"{name}.exe") if os.name == "nt" else (name,)
        for try_name in names:
            resolved = directory / try_name
            if resolved.is_file():
                return str(resolved)
    return None


class _ByteCounter:
    def __init__(self, cap: int) -> None:
        self._lock = threading.Lock()
        self._cap = cap
        self.total = 0

    def add(self, size: int) -> bool:
        """Add bytes; returns True once the combined output is over the cap."""
        with self._lock:
            self.total += size
            return self.total > self._cap


def _drain(stream: BinaryIO, chunks: list[bytes], counter: _ByteCounter, over_cap: threading.Event) -> None:
    """Reader thread: append chunks until EOF or the cap is exceeded."""
    while True:
        chunk = stream.read(_READ_CHUNK)
        if not chunk:
            break
        chunks.append(chunk)
        if counter.add(len(chunk)):
            over_cap.set()
            break


class _WindowsJobKiller:
    """A Job Object with KILL_ON_JOB_CLOSE: closing the handle kills every
    process in the job, including grandchildren spawned after assignment and
    orphaned by an early child exit (which ``taskkill /T`` cannot reach)."""

    def __init__(self) -> None:
        ctypes_lib = self._ctypes = ctypes
        self._handle: int | None = None
        try:
            kernel32 = getattr(ctypes_lib, "windll").kernel32  # noqa: B009 - windll is windows-only; getattr keeps POSIX mypy happy
            self._kernel32 = kernel32
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            job_info = self._extended_limit_info()
            job_info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(
                handle, 9, ctypes.byref(job_info), ctypes.sizeof(job_info)
            ):
                kernel32.CloseHandle(handle)
                return
            self._handle = int(handle)
        except OSError:
            self._handle = None

    def _extended_limit_info(self) -> Any:
        from ctypes import wintypes  # noqa: PLC0415 - windows-only submodule, lazy on POSIX

        class _BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.POINTER(wintypes.ULONG)),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class _IoCounters(ctypes.Structure):
            _fields_ = [(f"Field{index}", ctypes.c_ulonglong) for index in range(6)]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        return _ExtendedLimitInformation()

    @property
    def active(self) -> bool:
        return self._handle is not None

    def assign(self, process: subprocess.Popen[bytes]) -> bool:
        if self._handle is None:
            return False
        try:
            assigned = self._kernel32.AssignProcessToJobObject(
                self._handle,
                int(process._handle),  # type: ignore[attr-defined]  # documented handle attr
            )
        except OSError:
            return False
        return bool(assigned)

    def kill(self) -> None:
        if self._handle is not None:
            with contextlib.suppress(OSError):
                self._kernel32.CloseHandle(self._handle)  # kill() below is the guaranteed path
            self._handle = None


def _kill_tree(process: subprocess.Popen[bytes], job: _WindowsJobKiller | None) -> None:
    """Kill the child AND its descendants; process.kill() is the guaranteed path."""
    if os.name == "nt":
        tree_killed = False
        if job is not None and job.active:
            job.kill()
            tree_killed = True
        if not tree_killed:
            taskkill = _resolve_executable("taskkill")
            if taskkill is not None:
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run(  # noqa: S603 - fixed argv (resolved absolute taskkill), no shell
                        [taskkill, "/F", "/T", "/PID", str(process.pid)],
                        check=False,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=_TASKKILL_TIMEOUT_S,
                    )  # best-effort; the direct kill below still runs
    else:
        killpg = getattr(os, "killpg", None)  # POSIX-only in typeshed; typesafe everywhere
        sigkill = getattr(signal, "SIGKILL", None)
        if killpg is not None and sigkill is not None:
            with contextlib.suppress(OSError):  # best-effort; the direct kill below still runs
                killpg(process.pid, sigkill)  # own session leader via start_new_session
    process.kill()


def run_allowed(
    *,
    argv: Sequence[str],
    allowlist: tuple[tuple[str, ...], ...],
    timeout_s: float,
    max_raw_bytes: int,
    cwd: Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> ProcessOutput:
    """Run one fixed, allowlisted argv; returns (stdout, stderr, returncode).

    Raises :class:`~nitelos.collect.CollectorError` with COLLECTOR_CONFIG_INVALID
    for a non-allowlisted argv or a relative ``argv[0]`` (before any process
    starts), COLLECTOR_UNAVAILABLE when the executable cannot be resolved or
    the process cannot be created, COLLECTOR_TIMEOUT after killing an overdue
    process tree, and COLLECTOR_OUTPUT_TOO_LARGE as soon as the combined
    output exceeds ``max_raw_bytes``.
    """
    requested = tuple(argv)
    if not requested or requested not in {tuple(entry) for entry in allowlist}:
        raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    head = requested[0]
    if (os.sep in head or (os.altsep and os.altsep in head)) and not Path(head).is_absolute():
        raise CollectorError(CollectorErrorCode.CONFIG_INVALID)
    executable = _resolve_executable(head)
    if executable is None:
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    job = _WindowsJobKiller() if os.name == "nt" else None
    try:
        process: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603 - fixed allowlisted argv, scrubbed env, shell never used (ADR-015)
            [executable, *requested[1:]],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_scrubbed_env(extra_env),
            cwd=cwd,
            start_new_session=os.name != "nt",
            creationflags=_WINDOWS_CREATION_FLAGS if os.name == "nt" else 0,
        )
    except OSError:
        if job is not None:
            job.kill()
        raise CollectorError(CollectorErrorCode.UNAVAILABLE) from None
    if job is not None and not job.assign(process):
        job.kill()  # assignment failed: fall back to taskkill on the child pid
        job = None

    stdout, stderr = process.stdout, process.stderr
    if stdout is None or stderr is None:  # PIPE guarantees these; typeshed does not
        process.kill()
        raise CollectorError(CollectorErrorCode.UNAVAILABLE)
    counter = _ByteCounter(max_raw_bytes)
    over_cap = threading.Event()
    out_chunks: list[bytes] = []
    err_chunks: list[bytes] = []
    readers = [
        threading.Thread(target=_drain, args=(stdout, out_chunks, counter, over_cap), daemon=True),
        threading.Thread(target=_drain, args=(stderr, err_chunks, counter, over_cap), daemon=True),
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout_s
    timed_out = False
    while True:
        if process.poll() is not None and not any(reader.is_alive() for reader in readers):
            break  # clean exit: process done AND both pipes closed
        if over_cap.is_set():
            break  # output cap exceeded: kill now, never buffer until the timeout
        if time.monotonic() > deadline:
            timed_out = True
            break  # covers a still-running child AND a grandchild holding the pipes
        time.sleep(_POLL_INTERVAL_S)
    if process.poll() is None or any(reader.is_alive() for reader in readers):
        _kill_tree(process, job)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=_REAP_TIMEOUT_S)  # a corpse must not hang the runner
    for reader in readers:
        reader.join(timeout=_JOIN_TIMEOUT_S)
    for stream in (stdout, stderr):
        if any(reader.is_alive() for reader in readers):
            break  # deliberate leak: closing a pipe under a blocked reader deadlocks
        with contextlib.suppress(OSError):
            stream.close()  # pipes may already be closed by the kill
    if timed_out:
        raise CollectorError(CollectorErrorCode.TIMEOUT)
    if counter.total > max_raw_bytes:
        raise CollectorError(CollectorErrorCode.OUTPUT_TOO_LARGE)
    returncode = process.returncode if process.returncode is not None else -1
    return ProcessOutput(b"".join(out_chunks), b"".join(err_chunks), returncode)
