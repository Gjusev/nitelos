"""AR-2 F1 regression check: averify must submit its worker while holding the
state lock, so a concurrent close() can never shut the executor down inside
the submit window ("cannot schedule new futures after shutdown").

Exit code 0 means the invariant held and the verification completed. Run in a
subprocess for the same Windows asyncio reason as _async_lifecycle_check.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nitelos.verifier as verifier_module
from nitelos import ExecutionStatus, Verifier, parse_request
from test_contract import _criterion, _request
from test_verifier import _obs

verifier = Verifier()
lock_state: dict[str, bool] = {}
real_submit = verifier_module.ThreadPoolExecutor.submit


def recording_submit(self_exec: object, fn: object, *args: object, **kwargs: object) -> object:
    # the fix submits while the state lock is held; close() therefore cannot
    # interleave between lock release and submit
    if verifier._state_lock.acquire(blocking=False):
        verifier._state_lock.release()
        lock_state["held_at_submit"] = False
    else:
        lock_state["held_at_submit"] = True
    return real_submit(self_exec, fn, *args, **kwargs)  # type: ignore[arg-type]


verifier_module.ThreadPoolExecutor.submit = recording_submit  # type: ignore[assignment]

request = parse_request(_request(criteria=[_criterion(operator="equals", expected=True)], evidence=[_obs()]))


async def main() -> None:
    result = await verifier.averify(request)
    assert result.execution_status == ExecutionStatus.OK, f"{result.error}"
    assert lock_state["held_at_submit"] is True, "submit escaped the state lock"
    await asyncio.to_thread(verifier.close)
    print("scenario-close-races-submit")


if __name__ == "__main__":
    asyncio.run(main())
