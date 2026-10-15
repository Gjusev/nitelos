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

ADR-011: VerificationResult.request_id is null exactly when an input error
left no readable caller ID; a readable valid ID is always preserved, and ok
or backend_error results always carry it (immediate BUSY/CLOSED results
salvage the ID from the incoming data, and an unreadable input surfaces as
input_error rather than an id-less backend error).
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
from nitelos.backends.base import (
    BackendOutputError,
    InferenceContext,
    PreparedVisualCriterion,
    validate_backend_finding,
)
from nitelos.context import select_action_context
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
    eligible_evidence,
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
    Score,
    VerificationRequest,
    VerificationResult,
    canonical_json,
    parse_request,
)

logger = logging.getLogger("nitelos")

_DEV_RERAISE_TRUE = {"1", "true", "yes", "on"}


def _parse_dev_reraise_env() -> bool:
    """AR-2 F2: only explicit truth words enable re-raise; junk is a config error."""
    value = os.environ.get("NITELOS_DEV_RERAISE", "")
    if value == "":
        return False
    normalized = value.strip().lower()
    if normalized in _DEV_RERAISE_TRUE:
        return True
    raise ConfigurationError("NITELOS_DEV_RERAISE must be one of 1/true/yes/on (case-insensitive) or unset")


_GENERIC_PATH_SUFFIXES = {
    "$.evidence": ".evidence",
    "$.pointer": ".pointer",
    "$.evidence_refs": ".evidence_refs",
    "$.criteria": "",
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


def _preflight(criterion: Any, capabilities: Any, request: VerificationRequest, index: int) -> None:
    """Doc 04 preflight for every criterion, before any infer call.

    Criterion-kind support is checked for all criteria regardless of policy
    gating; evidence-kind and image-count limits apply to the visual criteria
    the backend would be asked to infer on. Violations are input errors
    (UNSUPPORTED_CAPABILITY) and no inference happens.
    """
    if criterion.kind not in capabilities.criterion_kinds:
        raise _ev(
            InputErrorCode.UNSUPPORTED_CAPABILITY,
            f"$.criteria[{index}]",
            "the backend does not support this criterion kind",
        )
    if criterion.kind != "visual":
        return
    by_id = {item.id: item for item in request.evidence}
    cited = [by_id[evidence_id] for evidence_id in criterion.evidence_ids]
    for item in cited:
        if item.kind not in capabilities.evidence_kinds:
            raise _ev(
                InputErrorCode.UNSUPPORTED_CAPABILITY,
                f"$.criteria[{index}]",
                "the backend does not support a cited evidence kind",
            )
    image_count = sum(1 for item in cited if item.kind == "screenshot")
    if image_count > capabilities.max_images_per_criterion:
        raise _ev(
            InputErrorCode.UNSUPPORTED_CAPABILITY,
            f"$.criteria[{index}]",
            "criterion cites more images than the backend allows",
        )


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
        for protocol_member in ("descriptor", "capabilities", "infer", "close"):
            if not hasattr(effective_backend, protocol_member):
                raise ConfigurationError(
                    "backend must implement the Backend protocol (descriptor, capabilities, infer, close); "
                    "registration is instance injection only"
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
            dev_reraise = _parse_dev_reraise_env()
        self._backend = effective_backend
        self._policy = effective_policy
        self._bindings = bindings
        self._dev_reraise = bool(dev_reraise)
        self._state_lock = threading.Lock()
        self._busy = False
        self._closed = False
        self._backend_closed = False
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
        """Idempotently close; waits for in-flight work and closes the backend once."""
        with self._state_lock:
            self._closed = True
            executor = self._executor
            self._executor = None
            close_backend = not self._backend_closed
            self._backend_closed = True
        if executor is not None:
            executor.shutdown(wait=True)
        if close_backend:
            self._backend.close()
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
                    BackendErrorCode.BUSY,
                    "another verification is in flight",
                    retryable=True,
                    data=request_or_mapping,
                )
            if self._closed:
                return self._immediate_error(
                    BackendErrorCode.CLOSED, "verifier is closed", data=request_or_mapping
                )
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
                    BackendErrorCode.BUSY,
                    "another verification is in flight",
                    retryable=True,
                    data=request_or_mapping,
                )
            if self._closed:
                return self._immediate_error(
                    BackendErrorCode.CLOSED, "verifier is closed", data=request_or_mapping
                )
            self._busy = True
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nitelos-verifier")
            loop = asyncio.get_running_loop()
            # AR-2 F1: submit while still holding the state lock so a concurrent
            # close() can never shut the executor down inside the submit window
            # (run_in_executor enqueues synchronously and never blocks on work).
            # Cancellation of the awaiting task leaves the worker running; _run
            # itself clears the busy flag when the invocation really finishes.
            submission = loop.run_in_executor(self._executor, self._run, request_or_mapping, artifacts)
        return await submission

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
            prepared = prepare_evidence(request, store)  # validates every artifact, used or not
            capabilities = self._backend.capabilities
            for index, criterion in enumerate(request.criteria):
                _preflight(criterion, capabilities, request, index)
            durations: dict[str, float] = {}
            outcomes = []
            emitted_findings: frozenset[str] = frozenset()
            finding_scores: dict[str, Score | None] = {}
            omitted_context: list[str] = []
            for index, criterion in enumerate(request.criteria):
                criterion_start = perf_counter()
                try:
                    if criterion.kind == "visual":
                        outcome, emitted_findings, finding_scores[criterion.id] = self._evaluate_visual(
                            criterion,
                            request,
                            prepared.images,
                            emitted_findings,
                            omitted_context,
                        )
                    else:
                        outcome = evaluate_criterion(criterion, request, self._policy, self._bindings)
                except EvidenceValidationError as error:
                    raise EvidenceValidationError(_repath_issue(error.issue, index)) from None
                durations[criterion.id] = (perf_counter() - criterion_start) * 1000.0
                outcomes.append(outcome)
                completed.append(
                    to_criterion_result(criterion, outcome, score=finding_scores.get(criterion.id))
                )
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
                    omitted_context_ids=tuple(omitted_context),
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
                request_id=request.request_id if request is not None else _salvage_request_id(data),
                start=start,
            )
        except EvidenceValidationError as error:
            return self._error_result(
                code=error.issue.code,
                path=error.issue.field_path,
                message=error.issue.safe_message,
                request=request,
                request_id=request.request_id if request is not None else _salvage_request_id(data),
                start=start,
            )
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            raise
        except BackendOutputError as error:
            logger.error("verify.error code=%s criteria_completed=%d", error.code, len(completed))
            return self._backend_failure(
                error.code,
                error.safe_message,
                request,
                completed,
                start,
                request_id=(request.request_id if request is not None else _salvage_request_id(data)),
            )
        except Exception:  # backend boundary: any evaluation failure becomes a coded
            # BACKEND_EXCEPTION without echoing exception text; cancellation and
            # process-control exceptions were re-raised above and never reach here
            if self._dev_reraise:
                raise
            logger.error("verify.error code=BACKEND_EXCEPTION criteria_completed=%d", len(completed))
            return self._backend_failure(
                BackendErrorCode.BACKEND_EXCEPTION,
                "the backend failed while evaluating the request",
                request,
                completed,
                start,
                request_id=(request.request_id if request is not None else _salvage_request_id(data)),
            )

    # ------------------------------------------------------------------
    # visual backend path
    # ------------------------------------------------------------------

    def _evaluate_visual(
        self,
        criterion: Any,
        request: VerificationRequest,
        images: Mapping[str, Any],
        emitted: frozenset[str],
        omitted_context: list[str],
    ) -> tuple[Any, frozenset[str], Score | None]:
        """Preflighted visual evaluation: eligibility, optional inference, policy."""
        eligible, _ineligible = eligible_evidence(criterion, request, self._bindings)
        if not self._policy.allow_model_inference or not eligible:
            # no invocation: policy gate, or no admissible referenced evidence
            outcome = evaluate_criterion(criterion, request, self._policy, self._bindings)
            return outcome, emitted, None
        eligible_ids = {item.id for item in eligible}
        prepared_images = tuple(
            images[evidence_id] for evidence_id in criterion.evidence_ids if evidence_id in eligible_ids
        )
        prepared_criterion = PreparedVisualCriterion(
            criterion_id=criterion.id,
            description=criterion.description,
            images=prepared_images,
        )
        # bounded action context: the last eight actions at or before the newest
        # cited image; older qualifying actions are recorded as omitted (the
        # helper is only called when a cited image exists, per its contract)
        actions, omitted = select_action_context(
            request.evidence, max_image_sequence=max(image.sequence for image in prepared_images)
        )
        omitted_context.extend(omitted)
        context = InferenceContext(objective=request.objective, actions=actions, deadline=None)
        finding = self._backend.infer(prepared_criterion, context)
        image_map = {image.evidence_id: image for image in prepared_images}
        validate_backend_finding(
            finding, criterion_id=criterion.id, images=image_map, already_emitted=emitted
        )
        outcome = evaluate_criterion(criterion, request, self._policy, self._bindings, visual_finding=finding)
        return outcome, emitted | {criterion.id}, finding.score

    # ------------------------------------------------------------------
    # error result assembly
    # ------------------------------------------------------------------

    def _immediate_error(
        self, code: BackendErrorCode, message: str, *, retryable: bool = False, data: Any = None
    ) -> VerificationResult:
        start = perf_counter()
        elapsed_ms = (perf_counter() - start) * 1000.0
        request_id = data.request_id if isinstance(data, VerificationRequest) else _salvage_request_id(data)
        if request_id is None:
            # ADR-011: backend errors must carry an ID; an input with none is
            # itself invalid, so it surfaces as input_error instead
            return self._error_result(
                code=InputErrorCode.INVALID_SCHEMA,
                path="$",
                message="request must be a mapping or VerificationRequest",
                request=None,
                request_id=None,
                start=start,
            )
        return VerificationResult(
            schema_version="1",
            request_id=request_id,
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

    def _backend_failure(
        self,
        code: BackendErrorCode,
        message: str,
        request: VerificationRequest | None,
        completed: list[CriterionResult],
        start: float,
        *,
        request_id: str | None,
    ) -> VerificationResult:
        elapsed_ms = (perf_counter() - start) * 1000.0
        return VerificationResult(
            schema_version="1",
            request_id=request_id,
            verification_id=str(uuid.uuid4()),
            execution_status=ExecutionStatus.BACKEND_ERROR,
            decision=None,
            criteria=tuple(completed),
            reason_codes=(code,),
            error=ErrorInfo(code=code, safe_message=message),
            diagnostics=build_diagnostics(
                policy=self._policy,
                backend_descriptor=self._backend.descriptor,
                elapsed_ms=elapsed_ms,
                criterion_durations={},
                request=request,
                partial_results=bool(completed),
            ),
        )

    def _error_result(
        self,
        *,
        code: InputErrorCode,
        path: str,
        message: str,
        request: VerificationRequest | None,
        request_id: str | None,
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
