"""LIFE-01/02: verifier ownership, busy/closed and async cancellation (NIT-006).

Authority: docs/planning/02-system-architecture.md ("Sync, async, resources"),
03 (BUSY/CLOSED/BACKEND_EXCEPTION semantics), 12 (events and barriers only,
no sleep-based timing). Sync scenarios block by monkeypatching internal
module seams (prepare_evidence), never by sleeping.

The async scenarios run in a subprocess (tests/_async_lifecycle_check.py):
Windows asyncio loops build their self-pipe from socket.socketpair(), whose
emulation connects over loopback, which the offline conftest fixture denies
inside the pytest process. The subprocess pattern matches the established
packaging-test isolation; its exit code carries the verdict.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

import nitelos.verifier as verifier_module
from nitelos import ExecutionStatus, VerificationRequest, Verifier, parse_request
from test_contract import _criterion, _request
from test_verifier import _obs

ROOT = Path(__file__).resolve().parents[1]


def _ok_request() -> VerificationRequest:
    return parse_request(_request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()]))


# --------------------------------------------------------------------------
# LIFE-01: busy, closed, idempotent close (in-process)
# --------------------------------------------------------------------------


def test_life01_concurrent_call_returns_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    real = verifier_module.prepare_evidence

    def blocked(request: Any, store: Any) -> Any:
        entered.set()
        release.wait(timeout=30)
        return real(request, store)

    monkeypatch.setattr(verifier_module, "prepare_evidence", blocked)
    verifier = Verifier()
    request = _ok_request()
    outcome: dict[str, Any] = {}

    def first_call() -> None:
        outcome["result"] = verifier.verify(request)

    worker = threading.Thread(target=first_call)
    worker.start()
    assert entered.wait(timeout=30), "first call never reached the blocked seam"
    concurrent = verifier.verify(request)
    assert concurrent.execution_status == ExecutionStatus.BACKEND_ERROR
    assert concurrent.error is not None
    assert concurrent.error.code == "BUSY"
    assert concurrent.error.retryable is True
    assert concurrent.decision is None
    release.set()
    worker.join(timeout=30)
    assert outcome["result"].execution_status == ExecutionStatus.OK
    # the instance is usable again once the first call really finished
    assert verifier.verify(request).execution_status == ExecutionStatus.OK


def test_life01_call_after_close_returns_closed() -> None:
    verifier = Verifier()
    verifier.close()
    result = verifier.verify(_ok_request())
    assert result.execution_status == ExecutionStatus.BACKEND_ERROR
    assert result.error is not None
    assert result.error.code == "CLOSED"
    assert result.error.retryable is False


def test_life01_close_is_idempotent_and_context_manager_works() -> None:
    verifier = Verifier()
    verifier.close()
    verifier.close()  # idempotent
    with Verifier() as managed:
        assert managed.verify(_ok_request()).execution_status == ExecutionStatus.OK
    result = managed.verify(_ok_request())
    assert result.error is not None
    assert result.error.code == "CLOSED"


# --------------------------------------------------------------------------
# LIFE-02: cancellation, close-waits, process-control exceptions
# --------------------------------------------------------------------------


def test_life02_async_scenarios_in_subprocess() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "_async_lifecycle_check.py")],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "scenario-cancellation" in proc.stdout
    assert "scenario-close-waits" in proc.stdout


def test_life02_close_waits_for_inflight_call(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    real = verifier_module.prepare_evidence

    def blocked(request: Any, store: Any) -> Any:
        entered.set()
        release.wait(timeout=30)
        try:
            return real(request, store)
        finally:
            finished.set()

    monkeypatch.setattr(verifier_module, "prepare_evidence", blocked)
    verifier = Verifier()
    request = _ok_request()
    outcome: dict[str, Any] = {}

    def call() -> None:
        outcome["result"] = verifier.verify(request)

    worker = threading.Thread(target=call)
    worker.start()
    assert entered.wait(timeout=30)
    closer = threading.Thread(target=verifier.close)
    closer.start()
    # close is waiting: the call is still in flight and busy
    busy = verifier.verify(request)
    assert busy.error is not None
    assert busy.error.code == "BUSY"
    release.set()
    closer.join(timeout=30)
    worker.join(timeout=30)
    assert outcome["result"].execution_status == ExecutionStatus.OK
    assert verifier._busy is False
    closed = verifier.verify(request)
    assert closed.error is not None
    assert closed.error.code == "CLOSED"


def test_life02_keyboard_interrupt_and_system_exit_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _ok_request()

    def interrupted(criterion: Any, *args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt()

    monkeypatch.setattr(verifier_module, "evaluate_criterion", interrupted)
    with pytest.raises(KeyboardInterrupt):
        Verifier().verify(request)

    def exiting(criterion: Any, *args: Any, **kwargs: Any) -> Any:
        raise SystemExit(3)

    monkeypatch.setattr(verifier_module, "evaluate_criterion", exiting)
    with pytest.raises(SystemExit):
        Verifier().verify(request)
