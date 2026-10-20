"""The Playwright page-state helper (plan F6, NIT-022; extra ``playwright``).

:func:`capture_page_state` takes the caller's LIVE Playwright ``Page`` (sync
API) and a tuple of CSS selectors, and captures — never drives: one full-page
screenshot plus, per selector, ``text``/``visible``/``value``/``count``, with
the page URL and title, as one observation (``/page/...``) and one screenshot
evidence item. HARD RULE from v0.1, kept: nitelos NEVER navigates, clicks,
fills, waits or evaluates; the helper touches only ``page.url``,
``page.title()``, ``page.screenshot(full_page=True)`` and
``page.locator(sel)`` with ``text_content()``/``is_visible()``/
``input_value()`` (a non-input element yields ``value: null``, never an
error)/``count()``. The capture shape follows the maintainer's hard-mode
runner (full-page screenshot, per-locator text, URL).

The module imports playwright NEVER — the Page is duck-typed, so the
``nitelos[playwright]`` extra exists for the CALLER's dependency (and install
uniformity); fakes work in core-only environments. Capture runs through the
NIT-017 framework (``run_collector``): provenance, cross-checks, the
observation cap and redaction all apply. Selector keys are dict keys in the
observation, so a selector matching the default secret pattern
(token|secret|password|authorization) is REDACTED — prefer neutral selector
names. Screenshot bytes are handed back via the ``artifacts`` dict (keyed by
artifact id; nitelos never writes files). ``captured_at`` is the capture
moment, so criteria freshness governs page state like any other evidence.
Visible text, URLs and input values are captured as-is; pass
``redact_pointers`` (for example ``/page/selectors/#field/text``) to drop
specific values before the digest. The async Playwright API is not supported
in v0.2. The module-level COLLECTOR is exported for direct/framework use and
is per-process sequential; :func:`capture_page_state` always builds its own
collector instance, so concurrent calls cannot exchange bytes.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    ProvenanceRecord,
    run_collector,
)
from nitelos.schemas import Evidence as _EvidenceFactory
from nitelos.schemas import canonical_json

__all__ = ["COLLECTOR", "PageStateCollector", "PageStateConfig", "capture_page_state"]


class PageStateConfig(CollectorConfig):
    """Capture config: the caller's live Page and the selectors to read.

    Not JSON-constructible (the Page is a live object) — build it in code;
    there is deliberately no CLI kind for this helper.
    """

    page: Any
    selectors: tuple[str, ...] = Field(min_length=1, max_length=32)


class PageStateCollector:
    """Read-only capture of one page's state through the NIT-017 framework."""

    config_model = PageStateConfig

    @property
    def id(self) -> str:
        return "playwright"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(evidence_kinds=("observation", "screenshot"))

    def __init__(self) -> None:
        self._last_screenshot_bytes: bytes | None = None

    def collect(self, config: CollectorConfig) -> CollectionResult:
        cfg = config if isinstance(config, PageStateConfig) else PageStateConfig.model_validate(config)
        page = cfg.page
        captured_at = datetime.now(UTC)
        selectors_state: dict[str, dict[str, Any]] = {}
        for selector in cfg.selectors:
            locator = page.locator(selector)
            count = int(locator.count())
            text = locator.text_content() if count else None
            visible = bool(locator.is_visible())
            try:
                value: str | None = str(locator.input_value()) if count else None
            except Exception:  # noqa: BLE001 - non-input elements have no value; null, never an error
                value = None
            selectors_state[selector] = {"text": text, "visible": visible, "value": value, "count": count}
        screenshot_bytes = bytes(page.screenshot(full_page=True))
        self._last_screenshot_bytes = screenshot_bytes
        url = str(page.url)
        title = str(page.title())
        data: dict[str, Any] = {"page": {"url": url, "title": title, "selectors": selectors_state}}
        observation = _EvidenceFactory.observation(
            id=cfg.evidence_id,
            sequence=cfg.sequence_start,
            captured_at=captured_at,
            checkpoint_id=cfg.checkpoint_id,
            source_id=self.id,
            subject=cfg.subject,
            phase="final",
            channel="external_api",
            data=data,
        )
        shot = _EvidenceFactory.screenshot(
            id=f"{cfg.evidence_id}-shot",
            artifact_id=f"art-{cfg.evidence_id}",
            data=screenshot_bytes,
            sequence=cfg.sequence_start + 1,
            captured_at=captured_at,
            checkpoint_id=cfg.checkpoint_id,
            source_id=self.id,
            subject=cfg.subject,
            phase="final",
        )
        observation_payload = canonical_json(data).encode("utf-8")
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(observation, shot),
            provenance=(
                ProvenanceRecord(
                    evidence_id=observation.id,
                    collector_id=self.id,
                    collector_version=self.version,
                    source="live Playwright page (caller-supplied; sync API)",
                    invocation=f"capture url={url} selectors={len(cfg.selectors)}",
                    captured_at=captured_at,
                    subject=cfg.subject,
                    sha256=hashlib.sha256(observation_payload).hexdigest(),
                    raw_bytes=len(observation_payload),
                    normalized_bytes=len(observation_payload),
                ),
                ProvenanceRecord(
                    evidence_id=shot.id,
                    collector_id=self.id,
                    collector_version=self.version,
                    source="live Playwright page (full-page screenshot)",
                    invocation=f"screenshot url={url} full_page=True",
                    captured_at=captured_at,
                    subject=cfg.subject,
                    sha256=hashlib.sha256(screenshot_bytes).hexdigest(),
                    raw_bytes=len(screenshot_bytes),
                    normalized_bytes=len(screenshot_bytes),
                ),
            ),
        )


COLLECTOR = PageStateCollector()


def capture_page_state(
    page: Any,
    selectors: tuple[str, ...],
    *,
    evidence_id: str,
    checkpoint_id: str,
    subject: dict[str, str],
    artifacts: dict[str, bytes] | None = None,
    **config_overrides: Any,
) -> CollectionResult:
    """Capture one page's state; returns the framework-validated result.

    Screenshot bytes are additionally stored into ``artifacts`` under the
    screenshot's artifact id when the dict is given (nitelos never writes
    files). Absent elements are values (``count: 0``, null fields), never
    errors; framework errors (e.g. the observation cap) come back as the
    structured ``error`` on the result. A private collector instance is
    created per call, so concurrent captures cannot exchange bytes through
    the last-screenshot slot.
    """
    values: dict[str, Any] = {
        "evidence_id": evidence_id,
        "checkpoint_id": checkpoint_id,
        "subject": subject,
        "page": page,
        "selectors": selectors,
    }
    values.update(config_overrides)
    collector = PageStateCollector()
    result = run_collector(collector, PageStateConfig.model_validate(values))
    if artifacts is not None and result.error is None:
        shot = next((item for item in result.evidence if item.kind == "screenshot"), None)
        if shot is not None and collector._last_screenshot_bytes is not None:
            # just captured by THIS call; the provenance digest proves it
            artifacts[shot.artifact_id] = collector._last_screenshot_bytes
    return result
