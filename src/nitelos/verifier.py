"""End-to-end verifier SDK and lifecycle (NIT-006).

Authority: docs/planning/02-system-architecture.md ("Invocation lifecycle",
"Sync, async, resources"), 03 (VerificationResult, error discipline,
ConfigurationError, the dev-only re-raise), 05 (aggregation), 11 ("Error
handling discipline", demonstration definition). The verifier receives
immutable data and never acts on the agent's behalf.

Lifecycle: one in-flight call per instance. A concurrent call returns
backend_error/BUSY (retryable); a call after close returns backend_error/
CLOSED. close() is idempotent and waits for in-flight work. averify runs the
whole invocation on a single bounded worker thread per instance; cancelling
the awaiting task propagates CancelledError while the worker keeps running
and the instance stays BUSY until it really finishes — a running native
kernel cannot be forcibly stopped in v0.1, and this class makes no hard
timeout promise. Hard isolation requires a caller-owned process.

Errors: input errors become (input_error, null) results with safe codes and
field paths; unexpected evaluation exceptions become BACKEND_EXCEPTION
without echoing exception text; KeyboardInterrupt/SystemExit/CancelledError
propagate. The development-only re-raise is off by default (constructor flag
``dev_reraise`` or env ``NITELOS_DEV_RERAISE``) and must not appear in
release examples. No retries; partial backend-error results are explicitly
non-authoritative.

Logging uses the "nitelos" logger with no installed handlers and only safe
event names, codes, counts and durations.

Known limitation: when an input is too invalid to carry a readable
request_id, doc 02 says to use null, but the result schema requires an ID
string — the placeholder "unknown-request" is used instead (reported to the
orchestrator as a doc-02/doc-03 inconsistency).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import uuid
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any

from pydantic import TypeAdapter, ValidationError

from nitelos.backends import DeterministicBackend
from nitelos.diagnostics import build_diagnostics
from nitelos.errors import (
    BackendErrorCode,
    ConfigurationError,
    EvidenceValidationError,
    InputErrorCode,
    Issue,
    RequestValidationError,
)
from nitelos.evidence import ArtifactStore, prepare_evidence
from nitelos.policy import (
    TrustBinding,
    VerificationPolicy,
    aggregate_decision,
    evaluate_criterion,
    to_criterion_result,
)
from nitelos.schemas import (
    MAX_JSON_DEPTH,
    MAX_METADATA_BYTES,
    MAX_PAYLOAD_BYTES,
    MAX_REQUEST_JSON_BYTES,
    CriterionResult,
    ErrorInfo,
    ExecutionStatus,
    IDType,
    VerificationRequest,
    VerificationResult,
    canonical_json,
    parse_request,
)

logger = logging.getLogger("nitelos")

UNKNOWN_REQUEST_ID = "unknown-request"
_GENERIC_PATH_SUFFIXES = {
    "$.evidence": ".evidence",
    "$.pointer": ".pointer",
    "$.evidence_refs": ".evidence_refs",
}
_TA_ID = TypeAdapter(IDType)


def _ev(code: InputErrorCode, path: str, message: str) -> EvidenceValidationError:
    return EvidenceValidationError(Issue(code, path, message))


def _repath_issue(issue: Issue, index: int) -> Issue:
    """Move a generic policy/evaluator path to its criterion position."""
    suffix = _GENERIC_PATH_SUFFIXES.get(issue.field_path)
    if suffix is None:
        return issue
    return Issue(issue.code, f"$.criteria[{index}]{suffix}", issue.safe_message)


def _check_depth(value: object, depth: int) -> None:
    if isinstance(value, (dict, list)):
        if depth > MAX_JSON_DEPTH:
            raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "nesting exceeds the allowed depth")
        children = value.values() if isinstance(value, dict) else value
        for child in children:
            _check_depth(child, depth + 1)


def _check_typed_ceilings(request: VerificationRequest) -> None:
    """Doc-10 binding item: typed requests bypass parse_request, re-check here."""
    dump = request.model_dump(mode="json")
    if len(canonical_json(dump).encode("utf-8")) > MAX_REQUEST_JSON_BYTES:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$", "request exceeds the JSON size limit")
    metadata = dump.get("metadata") or {}
    if len(canonical_json(metadata).encode("utf-8")) > MAX_METADATA_BYTES:
        raise _ev(InputErrorCode.LIMIT_EXCEEDED, "$.metadata", "metadata exceeds its size limit")
    for index, item in enumerate(dump.get("evidence", [])):
        for field in ("data", "arguments"):
            payload = item.get(field)
            if payload is not None and len(canonical_json(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
                raise _ev(
                    InputErrorCode.LIMIT_EXCEEDED,
                    f"$.evidence[{index}].{field}",
                    "payload exceeds its size limit",
                )
    _check_depth(dump, 1)


def _salvage_request_id(data: object) -> str | None:
    if isinstance(data, Mapping):
        candidate = data.get("request_id")
        if isinstance(candidate, str):
            try:
                _TA_ID.validate_python(candidate)
            except ValidationError:
                return None
            return candidate
    return None


class Verifier:
    """Verifies explicit criteria against supplied evidence.

    The default configuration is deterministic-only: any declared visual
    criterion is an input error (UNSUPPORTED_CAPABILITY) before evaluation.
    The Backend protocol, capabilities and custom/visual backends arrive in
    NIT-007; v0.1 accepts only the built-in DeterministicBackend.
    """

    def __init__(
        self,
        *,
        backend: DeterministicBackend | None = None,
        policy: VerificationPolicy | None = None,
        trust_bindings: Sequence[TrustBinding] = (),
        dev_reraise: bool | None = None,
    ) -> None:
        effective_backend = backend if backend is not None else DeterministicBackend()
        if not isinstance(effective_backend, DeterministicBackend):
            raise ConfigurationError(
                "v0.1 accepts only the built-in DeterministicBackend; the Backend protocol arrives in NIT-007"
            )
        effective_policy = policy if policy is not None else VerificationPolicy()
        if not isinstance(effective_policy, VerificationPolicy):
            raise ConfigurationError("policy must be a VerificationPolicy instance")
        bindings = tuple(trust_bindings)
        seen: set[str] = set()
        for binding in bindings:
            if not isinstance(binding, TrustBinding):
                raise ConfigurationError("trust_bindings must contain TrustBinding instances")
            if binding.evidence_id in seen:
                raise ConfigurationError("duplicate trust bindings for the same evidence id")
            seen.add(binding.evidence_id)
        if dev_reraise is None:
            dev_reraise = os.environ.get("NITELOS_DEV_RERAISE", "") not in ("", "0")
        self._backend = effective_backend
        self._policy = effective_policy
        self._bindings = bindings
        self._dev_reraise = bool(dev_reraise)
        self._state_lock = threading.Lock()
        self._busy = False
        self._closed = False
        self._executor: ThreadPoolExecutor | None = None
        logger.debug(
            "verifier.constructed policy_id=%s backend_id=%s bindings=%d",
            effective_policy.id,
            effective_backend.descriptor.id,
            len(bindings),
        )

    @property
    def policy(self) -> VerificationPolicy:
        return self._policy

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Idempotently close; waits for any in-flight call to finish."""
        with self._state_lock:
            self._closed = True
            executor = self._executor
            self._executor = None
        if executor is not None:
            executor.shutdown(wait=True)
        logger.debug("verifier.closed")

    def __enter__(self) -> Verifier:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # invocation
    # ------------------------------------------------------------------

    def verify(
        self, request_or_mapping: Any, *, artifacts: Mapping[str, Any] | None = None
    ) -> VerificationResult:
        """Synchronously verify; the canonical method (doc 02)."""
        with self._state_lock:
            # busy takes precedence: while work is in flight the instance is
            # still operating (retryable), even if close has been requested
            if self._busy:
                return self._immediate_error(
                    BackendErrorCode.BUSY, "another verification is in flight", retryable=True
                )
            if self._closed:
                return self._immediate_error(BackendErrorCode.CLOSED, "verifier is closed")
            self._busy = True
        try:
            return self._run(request_or_mapping, artifacts)
        finally:
            with self._state_lock:
                self._busy = False

    async def averify(
        self, request_or_mapping: Any, *, artifacts: Mapping[str, Any] | None = None
    ) -> VerificationResult:
        """Async facade over the same invocation on one bounded worker thread."""
        with self._state_lock:
            # busy takes precedence: while work is in flight the instance is
            # still operating (retryable), even if close has been requested
            if self._busy:
                return self._immediate_error(
                    BackendErrorCode.BUSY, "another verification is in flight", retryable=True
                )
            if self._closed:
                return self._immediate_error(BackendErrorCode.CLOSED, "verifier is closed")
            self._busy = True
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nitelos-verifier")
            executor = self._executor
        loop = asyncio.get_running_loop()
        # cancellation of the awaiting task leaves the worker running; _run
        # itself clears the busy flag when the invocation really finishes
        return await loop.run_in_executor(executor, self._run, request_or_mapping, artifacts)

    def _run(self, data: Any, artifacts: Mapping[str, Any] | None) -> VerificationResult:
        try:
            return self._execute(data, artifacts)
        finally:
            with self._state_lock:
                self._busy = False

    # ------------------------------------------------------------------
    # core execution
    # ------------------------------------------------------------------

    def _execute(self, data: Any, artifacts: Mapping[str, Any] | None) -> VerificationResult:
        start = perf_counter()
        request: VerificationRequest | None = None
        completed: list[CriterionResult] = []
        try:
            if isinstance(data, VerificationRequest):
                request = data
                _check_typed_ceilings(request)
            elif isinstance(data, (Mapping, str, bytes, bytearray)):
                request = parse_request(data)
            else:
                raise RequestValidationError(
                    [
                        Issue(
                            InputErrorCode.INVALID_SCHEMA,
                            "$",
                            "request must be a mapping or VerificationRequest",
                        )
                    ]
                )
            store = ArtifactStore(artifacts) if artifacts is not None else ArtifactStore()
            prepare_evidence(request, store)  # validates every artifact, used or not
            for index, criterion in enumerate(request.criteria):
                if criterion.kind == "visual":
                    raise _ev(
                        InputErrorCode.UNSUPPORTED_CAPABILITY,
                        f"$.criteria[{index}]",
                        "the deterministic backend does not support visual criteria",
                    )
            durations: dict[str, float] = {}
            outcomes = []
            for index, criterion in enumerate(request.criteria):
                criterion_start = perf_counter()
                try:
                    outcome = evaluate_criterion(criterion, request, self._policy, self._bindings)
                except EvidenceValidationError as error:
                    raise EvidenceValidationError(_repath_issue(error.issue, index)) from None
                durations[criterion.id] = (perf_counter() - criterion_start) * 1000.0
                outcomes.append(outcome)
                completed.append(to_criterion_result(criterion, outcome))
            aggregate = aggregate_decision(outcomes)
            elapsed_ms = (perf_counter() - start) * 1000.0
            result = VerificationResult(
                schema_version="1",
                request_id=request.request_id,
                verification_id=str(uuid.uuid4()),
                execution_status=ExecutionStatus.OK,
                decision=aggregate.decision,
                criteria=tuple(completed),
                reason_codes=aggregate.reason_codes,
                error=None,
                diagnostics=build_diagnostics(
                    policy=self._policy,
                    backend_descriptor=self._backend.descriptor,
                    elapsed_ms=elapsed_ms,
                    criterion_durations=durations,
                    request=request,
                ),
            )
            logger.info(
                "verify.complete status=ok decision=%s criteria=%d elapsed_ms=%.3f",
                aggregate.decision,
                len(completed),
                elapsed_ms,
            )
            return result
        except RequestValidationError as error:
            issue = error.issues[0]
            return self._error_result(
                code=issue.code,
                path=issue.field_path,
                message=issue.safe_message,
                request=request,
                request_id=(request.request_id if request is not None else _salvage_request_id(data))
                or UNKNOWN_REQUEST_ID,
                start=start,
            )
        except EvidenceValidationError as error:
            return self._error_result(
                code=error.issue.code,
                path=error.issue.field_path,
                message=error.issue.safe_message,
                request=request,
                request_id=(request.request_id if request is not None else _salvage_request_id(data))
                or UNKNOWN_REQUEST_ID,
                start=start,
            )
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            raise
        except Exception:  # backend boundary: any evaluation failure becomes a coded
            # BACKEND_EXCEPTION without echoing exception text; cancellation and
            # process-control exceptions were re-raised above and never reach here
            if self._dev_reraise:
                raise
            logger.error("verify.error code=BACKEND_EXCEPTION criteria_completed=%d", len(completed))
            elapsed_ms = (perf_counter() - start) * 1000.0
            return VerificationResult(
                schema_version="1",
                request_id=(request.request_id if request is not None else UNKNOWN_REQUEST_ID),
                verification_id=str(uuid.uuid4()),
                execution_status=ExecutionStatus.BACKEND_ERROR,
                decision=None,
                criteria=tuple(completed),
                reason_codes=(BackendErrorCode.BACKEND_EXCEPTION,),
                error=ErrorInfo(
                    code=BackendErrorCode.BACKEND_EXCEPTION,
                    safe_message="the backend failed while evaluating the request",
                ),
                diagnostics=build_diagnostics(
                    policy=self._policy,
                    backend_descriptor=self._backend.descriptor,
                    elapsed_ms=elapsed_ms,
                    criterion_durations={},
                    request=request,
                    partial_results=bool(completed),
                ),
            )

    # ------------------------------------------------------------------
    # error result assembly
    # ------------------------------------------------------------------

    def _immediate_error(
        self, code: BackendErrorCode, message: str, *, retryable: bool = False
    ) -> VerificationResult:
        start = perf_counter()
        elapsed_ms = (perf_counter() - start) * 1000.0
        return VerificationResult(
            schema_version="1",
            request_id=UNKNOWN_REQUEST_ID,
            verification_id=str(uuid.uuid4()),
            execution_status=ExecutionStatus.BACKEND_ERROR,
            decision=None,
            criteria=(),
            reason_codes=(code,),
            error=ErrorInfo(code=code, safe_message=message, retryable=retryable),
            diagnostics=build_diagnostics(
                policy=self._policy,
                backend_descriptor=self._backend.descriptor,
                elapsed_ms=elapsed_ms,
                criterion_durations={},
                request=None,
            ),
        )

    def _error_result(
        self,
        *,
        code: InputErrorCode,
        path: str,
        message: str,
        request: VerificationRequest | None,
        request_id: str,
        start: float,
    ) -> VerificationResult:
        elapsed_ms = (perf_counter() - start) * 1000.0
        logger.info("verify.complete status=input_error code=%s", code)
        return VerificationResult(
            schema_version="1",
            request_id=request_id,
            verification_id=str(uuid.uuid4()),
            execution_status=ExecutionStatus.INPUT_ERROR,
            decision=None,
            criteria=(),
            reason_codes=(code,),
            error=ErrorInfo(code=code, safe_message=message, field_path=path),
            diagnostics=build_diagnostics(
                policy=self._policy,
                backend_descriptor=self._backend.descriptor,
                elapsed_ms=elapsed_ms,
                criterion_durations={},
                request=request,
            ),
        )
