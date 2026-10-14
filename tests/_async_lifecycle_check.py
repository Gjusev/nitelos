"""Standalone async lifecycle check for NIT-006 (run via subprocess).

Windows asyncio loops create their self-pipe with socket.socketpair(), whose
emulation connects over loopback; the offline conftest fixture denies that
inside the pytest process. These scenarios therefore run in a clean
subprocess: exit code 0 means every assertion passed, and any failure prints
its message on stderr. Not collected by pytest directly.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nitelos.verifier as verifier_module
from nitelos import ExecutionStatus, Verifier, parse_request
from test_contract import _criterion, _request
from test_verifier import _obs


def _ok_request() -> Any:
    return parse_request(_request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()]))


def _blocking_seam() -> dict[str, threading.Event]:
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

    verifier_module.prepare_evidence = blocked  # type: ignore[assignment]
    return {"entered": entered, "release": release, "finished": finished}


async def _wait_event(event: threading.Event) -> None:
    await asyncio.get_running_loop().run_in_executor(None, event.wait, 30)


async def scenario_cancellation_and_busy() -> None:
    events = _blocking_seam()
    verifier = Verifier()
    request = _ok_request()
    task = asyncio.get_running_loop().create_task(verifier.averify(request))
    await _wait_event(events["entered"])
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation did not propagate")
    busy = await verifier.averify(request)
    assert busy.error is not None, f"expected BUSY, got {busy.error}"
    assert busy.error.code == "BUSY", f"expected BUSY, got {busy.error}"
    events["release"].set()
    await _wait_event(events["finished"])
    await asyncio.get_running_loop().run_in_executor(None, verifier.close)
    assert not verifier._busy, "busy flag survived the worker finishing"
    closed = verifier.verify(request)
    assert closed.error is not None, f"expected CLOSED, got {closed.error}"
    assert closed.error.code == "CLOSED", f"expected CLOSED, got {closed.error}"


async def scenario_averify_matches_verify() -> None:
    verifier = Verifier()
    request = _ok_request()
    sync_result = verifier.verify(request)
    async_result = await verifier.averify(request)
    assert sync_result.execution_status == ExecutionStatus.OK
    assert async_result.execution_status == ExecutionStatus.OK
    assert sync_result.decision == async_result.decision
    assert [c.state for c in async_result.criteria] == ["supported"]


async def scenario_averify_after_close() -> None:
    verifier = Verifier()
    verifier.close()
    result = await verifier.averify(_ok_request())
    assert result.error is not None, f"expected CLOSED, got {result.error}"
    assert result.error.code == "CLOSED", f"expected CLOSED, got {result.error}"


async def scenario_close_waits_while_busy() -> None:
    events = _blocking_seam()
    verifier = Verifier()
    request = _ok_request()
    task = asyncio.get_running_loop().create_task(verifier.averify(request))
    await _wait_event(events["entered"])
    closer = asyncio.get_running_loop().create_task(asyncio.to_thread(verifier.close))
    await asyncio.sleep(0)  # let the closer start without sleeping on time
    busy = await verifier.averify(request)
    assert busy.error is not None, f"expected BUSY, got {busy.error}"
    assert busy.error.code == "BUSY", "close should wait, instance should stay busy"
    events["release"].set()
    await closer
    result = await task
    assert result.execution_status == ExecutionStatus.OK, f"in-flight call failed: {result.error}"
    closed = verifier.verify(request)
    assert closed.error is not None
    assert closed.error.code == "CLOSED"


async def main() -> None:
    for scenario in (
        scenario_cancellation_and_busy,
        scenario_averify_matches_verify,
        scenario_averify_after_close,
        scenario_close_waits_while_busy,
    ):
        await scenario()
    for record in ("scenario-cancellation", "scenario-parity", "scenario-closed", "scenario-close-waits"):
        print(record)


if __name__ == "__main__":
    asyncio.run(main())
