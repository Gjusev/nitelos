"""OTEL-01..07: F12 OpenTelemetry export for nitelos (extra ``otel``)."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from nitelos import Verifier, canonical_json
from nitelos.integrations.otel import (
    GEN_AI_EVALUATION_NAME_SEMCONV,
    GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV,
    span_attributes,
    verify_traced,
)

ROOT = Path(__file__).resolve().parents[1]

BASE_KEYS = frozenset(
    (
        "nitelos.execution_status",
        "nitelos.verification_id",
        "nitelos.criteria.count",
        "nitelos.criteria.supported",
        "nitelos.criteria.refuted",
        "nitelos.criteria.unknown",
        "nitelos.reason_codes",
        "nitelos.limitation_codes",
        "nitelos.backend.id",
        "nitelos.backend.version",
        "nitelos.elapsed_ms",
        "nitelos.collector.ids",
        "nitelos.evidence.cited_count",
    )
)
OK_EXTRA_KEYS = frozenset(
    ("nitelos.decision", GEN_AI_EVALUATION_NAME_SEMCONV, GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV)
)
ERROR_EXTRA_KEYS = frozenset(("nitelos.error.code",))
DURATION_KEY = "nitelos.collector.durations_ms"


@pytest.fixture
def tracer_setup() -> Iterator[tuple[Any, Any]]:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    yield tracer, exporter
    provider.shutdown()


def _observation(data: dict[str, Any], *, subject_form: str = "registration-1") -> dict[str, Any]:
    obs = {
        "id": "obs-form",
        "kind": "observation",
        "sequence": 0,
        "captured_at": "2026-10-20T10:00:00Z",
        "checkpoint_id": "cp-final",
        "source_id": "my-runner",
        "subject": {"form": subject_form},
        "phase": "final",
        "channel": "dom",
        "data": data,
    }
    obs["sha256"] = hashlib.sha256(canonical_json(obs["data"]).encode("utf-8")).hexdigest()
    return obs


def _request(evidence: list[dict[str, Any]], criteria: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "request_id": "otel-test-1",
        "objective": "Complete the registration form",
        "checkpoint_id": "cp-final",
        "as_of": "2026-10-20T10:01:00Z",
        "criteria": criteria,
        "evidence": evidence,
    }


def _no_errors_criteria() -> list[dict[str, Any]]:
    return [
        {
            "id": "no-errors",
            "description": "No validation error remains on the form",
            "kind": "assertion",
            "scope": "observed_state",
            "evidence_ids": ["obs-form"],
            "subject": {"form": "registration-1"},
            "pointer": "/validation_error",
            "operator": "equals",
            "expected": False,
        }
    ]


def test_otel01_span_and_exact_allowlist_ok_success(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    request = _request([_observation({"validation_error": False})], _no_errors_criteria())
    result = verify_traced(Verifier(), request, tracer=tracer, collector_ids=("collector-a",))
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "nitelos.verify"
    assert set(span.attributes) == BASE_KEYS | OK_EXTRA_KEYS
    attrs = span.attributes
    assert attrs["nitelos.execution_status"] == "ok"
    assert attrs["nitelos.decision"] == "success"
    assert attrs["nitelos.criteria.count"] == 1
    assert attrs["nitelos.criteria.supported"] == 1
    assert attrs["nitelos.criteria.refuted"] == 0
    assert attrs["nitelos.criteria.unknown"] == 0
    assert attrs["nitelos.reason_codes"] == ("ALL_CRITERIA_SUPPORTED",)
    assert attrs["nitelos.collector.ids"] == ("collector-a",)
    assert attrs["nitelos.evidence.cited_count"] == 1
    assert attrs[GEN_AI_EVALUATION_NAME_SEMCONV] == "nitelos.verify"
    assert attrs[GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV] == "success"
    assert isinstance(attrs["nitelos.elapsed_ms"], float)
    assert result.execution_status == "ok"


def test_otel01_allowlist_ok_failure(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    request = _request([_observation({"validation_error": True})], _no_errors_criteria())
    verify_traced(Verifier(), request, tracer=tracer)
    span = exporter.get_finished_spans()[0]
    assert set(span.attributes) == BASE_KEYS | OK_EXTRA_KEYS
    attrs = span.attributes
    assert attrs["nitelos.decision"] == "failure"
    assert attrs["nitelos.criteria.refuted"] == 1
    assert attrs[GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV] == "failure"


def test_otel01_allowlist_ok_abstained(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    criteria = [
        {
            "id": "stored",
            "description": "The file exists in the external store",
            "kind": "assertion",
            "scope": "external",
            "evidence_ids": [],
            "subject": {"file": "upload-1"},
            "pointer": "/exists",
            "operator": "equals",
            "expected": True,
        }
    ]
    verify_traced(Verifier(), _request([], criteria), tracer=tracer)
    span = exporter.get_finished_spans()[0]
    assert set(span.attributes) == BASE_KEYS | OK_EXTRA_KEYS
    attrs = span.attributes
    assert attrs["nitelos.decision"] == "abstained"
    assert attrs["nitelos.criteria.unknown"] == 1
    assert attrs["nitelos.evidence.cited_count"] == 0


def test_otel01_allowlist_input_error(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    verify_traced(Verifier(), {"schema_version": "1"}, tracer=tracer)
    assert len(exporter.get_finished_spans()) == 1
    span = exporter.get_finished_spans()[0]
    assert set(span.attributes) == BASE_KEYS | ERROR_EXTRA_KEYS
    attrs = span.attributes
    assert "nitelos.decision" not in attrs
    assert attrs["nitelos.execution_status"] == "input_error"
    assert attrs["nitelos.error.code"] == "INVALID_SCHEMA"
    assert attrs["nitelos.criteria.count"] == 0


def test_otel01_durations_key_only_when_given(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    request = _request([_observation({"validation_error": False})], _no_errors_criteria())
    verify_traced(
        Verifier(),
        request,
        tracer=tracer,
        collector_ids=("collector-a", "collector-b"),
        collector_durations_ms={"collector-a": 1.5, "collector-b": 2.0},
    )
    attrs = exporter.get_finished_spans()[0].attributes
    assert set(attrs) == BASE_KEYS | OK_EXTRA_KEYS | {DURATION_KEY}
    assert attrs[DURATION_KEY] == (1.5, 2.0)


def test_otel02_no_raw_values_in_span(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    sentinel = "SECRET-sentinel-value"
    request = _request(
        [_observation({"validation_error": True, "note": sentinel}, subject_form=sentinel)],
        [
            {
                "id": "no-errors",
                "description": sentinel,
                "kind": "assertion",
                "scope": "observed_state",
                "evidence_ids": ["obs-form"],
                "subject": {"form": sentinel},
                "pointer": "/validation_error",
                "operator": "equals",
                "expected": False,
            }
        ],
    )
    request["objective"] = sentinel
    request["request_id"] = "rid-" + sentinel
    verify_traced(Verifier(), request, tracer=tracer, collector_ids=("collector-a",))
    span = exporter.get_finished_spans()[0]
    blob = json.dumps({"attrs": {k: str(v) for k, v in span.attributes.items()}})
    assert sentinel not in blob
    assert sentinel not in span.name
    assert sentinel not in str(span.status.description or "")


def test_otel03_status_mapping(tracer_setup: tuple[Any, Any]) -> None:
    from opentelemetry.trace import StatusCode

    tracer, exporter = tracer_setup
    verify_traced(Verifier(), {"schema_version": "1"}, tracer=tracer)
    error_span = exporter.get_finished_spans()[0]
    assert error_span.status.status_code == StatusCode.ERROR
    assert error_span.status.description == "INVALID_SCHEMA"

    request = _request([_observation({"validation_error": True})], _no_errors_criteria())
    verify_traced(Verifier(), request, tracer=tracer)
    failure_span = exporter.get_finished_spans()[1]
    assert failure_span.status.status_code != StatusCode.ERROR


def test_otel04_bad_inputs_raise_before_span(tracer_setup: tuple[Any, Any]) -> None:
    tracer, exporter = tracer_setup
    request = _request([_observation({"validation_error": False})], _no_errors_criteria())
    many = tuple(f"c-{i}" for i in range(65))
    with pytest.raises(ValueError, match="ID pattern"):
        verify_traced(Verifier(), request, tracer=tracer, collector_ids=("bad id!",))
    with pytest.raises(ValueError, match="at most 64"):
        verify_traced(Verifier(), request, tracer=tracer, collector_ids=many)
    with pytest.raises(ValueError, match="finite"):
        verify_traced(
            Verifier(),
            request,
            tracer=tracer,
            collector_ids=("collector-a",),
            collector_durations_ms={"collector-a": float("nan")},
        )
    with pytest.raises(ValueError, match="finite"):
        verify_traced(
            Verifier(),
            request,
            tracer=tracer,
            collector_ids=("collector-a",),
            collector_durations_ms={"collector-a": -1.0},
        )
    assert not exporter.get_finished_spans()


_SUBPROCESS_CODE = (
    "import sys\n"
    'sys.modules["opentelemetry"] = None\n'
    "import nitelos\n"
    'print("core-ok")\n'
    "try:\n"
    "    import nitelos.integrations.otel\n"
    "except Exception as exc:\n"
    "    print(type(exc).__name__)\n"
    '    print("nitelos[otel]" in str(exc))\n'
    "else:\n"
    '    raise SystemExit("should have raised")\n'
)


def test_otel05_missing_extra_is_actionable_and_core_stays_clean() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_CODE],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "core-ok" in proc.stdout
    assert "ImportError" in proc.stdout or "RuntimeError" in proc.stdout
    assert "True" in proc.stdout


def test_otel06_semconv_constants_match_installed_package() -> None:
    from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
        GEN_AI_EVALUATION_NAME,
        GEN_AI_EVALUATION_SCORE_LABEL,
    )

    assert GEN_AI_EVALUATION_NAME_SEMCONV == GEN_AI_EVALUATION_NAME
    assert GEN_AI_EVALUATION_SCORE_LABEL_SEMCONV == GEN_AI_EVALUATION_SCORE_LABEL


_FIXED_RESULT: list[Any] = [None]


class _FixedResultVerifier:
    def verify(self, request: Any, *, artifacts: Any = None) -> Any:
        return _FIXED_RESULT[0]


class _ExplodingVerifier:
    def verify(self, request: Any, *, artifacts: Any = None) -> Any:
        raise RuntimeError("SECRET internal detail")


def test_otel07_no_global_side_effects(tracer_setup: tuple[Any, Any]) -> None:
    from opentelemetry import trace

    tracer, _exporter = tracer_setup
    provider_before = trace.get_tracer_provider()
    handlers_before = list(logging.getLogger("nitelos").handlers)
    _FIXED_RESULT[0] = Verifier().verify({"schema_version": "1"})
    returned = verify_traced(_FixedResultVerifier(), {"anything": True}, tracer=tracer)
    assert returned is _FIXED_RESULT[0]
    assert trace.get_tracer_provider() is provider_before
    assert logging.getLogger("nitelos").handlers == handlers_before


def test_otel07b_verifier_exception_records_type_only_and_reraises(
    tracer_setup: tuple[Any, Any],
) -> None:
    from opentelemetry.trace import StatusCode

    tracer, exporter = tracer_setup
    with pytest.raises(RuntimeError, match="SECRET internal detail"):
        verify_traced(_ExplodingVerifier(), {"x": 1}, tracer=tracer)
    span = exporter.get_finished_spans()[0]
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description == "RuntimeError"
    assert not span.events
    assert "SECRET" not in json.dumps({k: str(v) for k, v in span.attributes.items()})


def test_otel08_span_attributes_pure_function_shapes() -> None:
    attrs = span_attributes(Verifier().verify({"schema_version": "1"}))
    assert set(attrs) == BASE_KEYS | ERROR_EXTRA_KEYS
