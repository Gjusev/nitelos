"""Bounded action-context selection for visual backends (NIT-009; reused by NIT-007).

Authority: docs/planning/04-verification-backends.md step 5 and doc 11
("Trace schema-v1, exact minimum" — the last-eight action paragraph), plus the
interface contract recorded by the orchestrator in decisions.md: NIT-007's
InferenceContext consumes ``actions: tuple[ActionContextItem, ...]`` from this module.
The view is the documented fixed context handed to a visual model: the last at most
``limit`` (default 8) action items whose sequence does not exceed the highest cited
image sequence, name and reported status only — never arguments or tool response
bodies. When more actions qualify than fit the window, the older ones are omitted
explicitly and their evidence IDs are returned so diagnostics can record them. This is
a fixed declared context view, identical across compared backends — not silent
truncation of cited evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nitelos.schemas import ActionEvidence, ReportedStatus

__all__ = ["ActionContextItem", "select_action_context"]

_DEFAULT_LIMIT = 8


@dataclass(frozen=True)
class ActionContextItem:
    """One action in the model context view: identifiers, name and status only."""

    evidence_id: str
    sequence: int
    name: str
    reported_status: ReportedStatus

    def __repr__(self) -> str:
        # safe repr: identifiers and status only; name is caller text
        return (
            f"ActionContextItem(evidence_id={self.evidence_id!r}, "
            f"sequence={self.sequence}, reported_status={self.reported_status!s})"
        )


def select_action_context(
    evidence: Sequence[object],
    *,
    max_image_sequence: int,
    limit: int = _DEFAULT_LIMIT,
) -> tuple[tuple[ActionContextItem, ...], tuple[str, ...]]:
    """Select the bounded action context for one visual criterion (pure, no I/O).

    ``max_image_sequence`` is the highest image sequence cited by the criterion; actions
    with a greater sequence are excluded (they happened after the newest cited image and
    are not context for it). Callers with no cited image do not call this helper. The
    selected items keep ascending sequence order; the second value lists the evidence
    IDs of qualifying actions that fell outside the last-``limit`` window, also in
    ascending sequence order, so the caller records them as omitted context.
    """
    qualifying = [
        item for item in evidence if isinstance(item, ActionEvidence) and item.sequence <= max_image_sequence
    ]
    window = qualifying[-limit:] if limit > 0 else []
    omitted = tuple(item.id for item in qualifying[: len(qualifying) - len(window)])
    items = tuple(
        ActionContextItem(
            evidence_id=item.id,
            sequence=item.sequence,
            name=item.name,
            reported_status=item.reported_status,
        )
        for item in window
    )
    return items, omitted
