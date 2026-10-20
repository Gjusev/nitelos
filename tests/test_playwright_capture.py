"""PWS-01..12: F6 Playwright page-state helper (NIT-022, extra ``playwright``).

The Page is caller-supplied and the helper imports playwright NEVER — it
duck-types the sync API — so these tests run offline with a fake Page/Locator
(no browsers in CI; the extra exists for the caller's own dependency). The
live-browser test is env-gated without a custom marker (see the bottom of the
file) so no central marker registration is needed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from _imagekit import png_bytes
from nitelos import Verifier, parse_request
from nitelos.collect import CollectorErrorCode, host_trust_bindings, run_collector
from nitelos.integrations.playwright_capture import (
    COLLECTOR,
    PageStateConfig,
    capture_page_state,
)

PNG = png_bytes(4, 4, "RGB", (10, 20, 30))
SUBJECT = {"page": "checkout"}


class FakeLocator:
    def __init__(
        self,
        *,
        text: str | None,
        visible: bool,
        count: int,
        value: str | None,
        value_error: bool = False,
    ) -> None:
        self._text = text
        self._visible = visible
        self._count = count
        self._value = value
        self._value_error = value_error

    def text_content(self) -> str | None:
        if self._count == 0:
            return None
        return self._text

    def is_visible(self) -> bool:
        return self._visible

    def input_value(self) -> str:
        if self._value_error:
            raise RuntimeError("Node is not an <input>")
        return self._value or ""

    def count(self) -> int:
        return self._count


class FakePage:
    """The slice of Playwright's sync Page the helper touches — nothing else."""

    def __init__(
        self,
        selectors: dict[str, FakeLocator],
        *,
        url: str = "https://shop.example/checkout",
        title: str = "Checkout",
    ) -> None:
        self._selectors = selectors
        self.url = url
        self._title = title
        self.screenshot_calls: list[dict[str, Any]] = []

    def title(self) -> str:
        return self._title

    def screenshot(self, **kwargs: Any) -> bytes:
        self.screenshot_calls.append(dict(kwargs))
        return PNG

    def locator(self, selector: str) -> FakeLocator:
        return self._selectors[selector]


def _page() -> FakePage:
    return FakePage(
        {
            "#confirm": FakeLocator(
                text="Order confirmed", visible=True, count=1, value=None, value_error=True
            ),
            "input[name=email]": FakeLocator(text=None, visible=True, count=1, value="ada@example.com"),
            ".missing": FakeLocator(text=None, visible=False, count=0, value=None),
        }
    )


def _capture(page: Any = None, **over: Any) -> Any:
    values: dict[str, Any] = {
        "evidence_id": "page-1",
        "checkpoint_id": "cp",
        "subject": dict(SUBJECT),
        "page": page if page is not None else _page(),
        "selectors": ("#confirm", "input[name=email]", ".missing"),
    }
    values.update(over)
    config = PageStateConfig.model_validate(values)
    return run_collector(COLLECTOR, config)


def _data(result: Any) -> dict[str, Any]:
    assert result.error is None, result.error
    observation = next(item for item in result.evidence if item.kind == "observation")
    return dict(observation.data)  # type: ignore[no-any-return]


# --------------------------------------------------------------------------
# PWS-01..04: the observation shape
# --------------------------------------------------------------------------


def test_pws01_url_title_and_per_selector_state() -> None:
    data = _data(_capture())
    assert data["page"]["url"] == "https://shop.example/checkout"
    assert data["page"]["title"] == "Checkout"
    selectors = data["page"]["selectors"]
    assert selectors["#confirm"] == {
        "text": "Order confirmed",
        "visible": True,
        "value": None,
        "count": 1,
    }
    assert selectors["input[name=email]"]["value"] == "ada@example.com"
    assert selectors[".missing"] == {"text": None, "visible": False, "value": None, "count": 0}


def test_pws02_screenshot_evidence_with_exact_bytes() -> None:
    page = _page()
    result = _capture(page)
    shot = next(item for item in result.evidence if item.kind == "screenshot")
    assert shot.artifact_id
    record = next(r for r in result.provenance if r.evidence_id == shot.id)
    assert record.sha256 == hashlib.sha256(PNG).hexdigest()
    assert record.raw_bytes == len(PNG)
    assert page.screenshot_calls
    assert page.screenshot_calls[0].get("full_page") is True


def test_pws03_helper_returns_result_and_stashes_artifact_bytes() -> None:
    artifacts: dict[str, bytes] = {}
    result = capture_page_state(
        _page(),
        ("#confirm",),
        evidence_id="page-2",
        checkpoint_id="cp",
        subject=dict(SUBJECT),
        artifacts=artifacts,
    )
    assert result.error is None
    (shot,) = [item for item in result.evidence if item.kind == "screenshot"]
    assert artifacts[shot.artifact_id] == PNG


def test_pws03b_two_captures_stash_their_own_bytes() -> None:
    # the review's corruption scenario: two captures, distinct pages/bytes —
    # each artifacts dict must hold its own capture's bytes, never the other's
    other_png = png_bytes(6, 6, "RGB", (200, 100, 50))

    class _OtherPage(FakePage):
        def screenshot(self, **kwargs: Any) -> bytes:
            return other_png

    artifacts_a: dict[str, bytes] = {}
    artifacts_b: dict[str, bytes] = {}
    first = capture_page_state(
        _page(),
        ("#confirm",),
        evidence_id="pa",
        checkpoint_id="cp",
        subject=dict(SUBJECT),
        artifacts=artifacts_a,
    )
    second = capture_page_state(
        _OtherPage({"#confirm": FakeLocator(text="b", visible=True, count=1, value=None)}),
        ("#confirm",),
        evidence_id="pb",
        checkpoint_id="cp",
        subject=dict(SUBJECT),
        artifacts=artifacts_b,
    )
    assert first.error is None
    assert second.error is None
    shot_a = next(i for i in first.evidence if i.kind == "screenshot")
    shot_b = next(i for i in second.evidence if i.kind == "screenshot")
    assert artifacts_a[shot_a.artifact_id] == PNG
    assert artifacts_b[shot_b.artifact_id] == other_png


def test_pws04_one_provenance_per_evidence_with_final_digests() -> None:
    result = _capture()
    assert len(result.evidence) == 2
    assert len(result.provenance) == 2
    for item in result.evidence:
        record = next(r for r in result.provenance if r.evidence_id == item.id)
        assert record.evidence_sha256 == item.sha256


# --------------------------------------------------------------------------
# PWS-05..08: safety and framework composition
# --------------------------------------------------------------------------


def test_pws05_never_drives_the_browser() -> None:
    page = _page()

    def forbidden(method_name: str) -> Any:
        def raise_it(*args: Any, **kwargs: Any) -> None:
            raise AssertionError(f"{method_name} must never be called")

        return raise_it

    for name in (
        "goto",
        "go_back",
        "go_forward",
        "set_content",
        "click",
        "fill",
        "select_option",
        "press",
        "hover",
        "wait_for",
        "wait_for_timeout",
        "wait_for_load_state",
        "wait_for_url",
        "reload",
        "evaluate",
    ):
        setattr(page, name, forbidden(name))
    result = _capture(page)
    assert result.error is None


def test_pws06_selector_keys_flow_through_default_redaction() -> None:
    page = FakePage({"[data-token]": FakeLocator(text="t", visible=True, count=1, value=None)})
    data = _data(_capture(page, selectors=("[data-token]",)))
    # the framework's default secret-key redaction drops selector keys that
    # match the token|secret|password|authorization pattern — documented
    assert data["page"]["selectors"] == {}


def test_pws07_sentinel_text_value_does_not_leak_into_provenance_or_repr() -> None:
    sentinel = "SECRET-value-9f1c"
    page = FakePage({"#msg": FakeLocator(text=f"error {sentinel}", visible=True, count=1, value=None)})
    result = _capture(page, selectors=("#msg",))
    assert result.error is None
    assert sentinel not in repr(result)
    assert sentinel not in json.dumps([r.model_dump(mode="json") for r in result.provenance])


def test_pws08_observation_cap_applies() -> None:
    big = "x" * 10_000
    page = FakePage({"#big": FakeLocator(text=big, visible=True, count=1, value=None)})
    from nitelos.collect import CollectorLimits

    result = _capture(page, selectors=("#big",), limits=CollectorLimits(max_observation_bytes=1024))
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.OUTPUT_TOO_LARGE


# --------------------------------------------------------------------------
# PWS-09..10: trust and criteria round trip
# --------------------------------------------------------------------------


def _request(result: Any, pointer: str, expected: Any) -> Any:
    # the criterion cites only the observation; the screenshot (whose artifact
    # lives in the host's store, not the request) stays out of this request
    observation = next(item for item in result.evidence if item.kind == "observation")
    return parse_request(
        json.dumps(
            {
                "schema_version": "1",
                "request_id": "pws-9",
                "objective": "The confirmation is visible",
                "checkpoint_id": "cp",
                "as_of": observation.model_dump(mode="json")["captured_at"],
                "criteria": [
                    {
                        "id": "c-visible",
                        "description": "Confirmation element is visible",
                        "kind": "assertion",
                        "scope": "external",
                        "evidence_ids": [observation.id],
                        "subject": dict(SUBJECT),
                        "pointer": pointer,
                        "operator": "equals",
                        "expected": expected,
                    }
                ],
                "evidence": [observation.model_dump(mode="json")],
                "metadata": {},
            }
        )
    )


def test_pws09_criteria_decide_on_page_state() -> None:
    result = _capture()
    verified = Verifier(trust_bindings=host_trust_bindings(result)).verify(
        _request(result, "/page/selectors/#confirm/visible", True)
    )
    assert verified.decision is not None
    assert verified.decision.value == "success"
    refuted = Verifier(trust_bindings=host_trust_bindings(result)).verify(
        _request(result, "/page/selectors/#confirm/visible", False)
    )
    assert refuted.decision is not None
    assert refuted.decision.value == "failure"


def test_pws10_unbound_page_evidence_abstains_untrusted() -> None:
    result = _capture()
    verified = Verifier().verify(_request(result, "/page/selectors/#confirm/visible", True))
    assert verified.decision is not None
    assert verified.decision.value == "abstained"
    assert "UNTRUSTED_EXTERNAL" in verified.reason_codes


# --------------------------------------------------------------------------
# PWS-11..12: contract, validation
# --------------------------------------------------------------------------


def test_pws11_contract_suite_passes() -> None:
    from _collector_contract import assert_contract

    assert_contract(
        COLLECTOR,
        PageStateConfig.model_validate(
            {
                "evidence_id": "page-3",
                "checkpoint_id": "cp",
                "subject": dict(SUBJECT),
                "page": _page(),
                "selectors": ("#confirm",),
            }
        ),
    )


def test_pws12_config_validation() -> None:
    with pytest.raises(Exception, match="selectors"):
        PageStateConfig.model_validate(
            {
                "evidence_id": "page-4",
                "checkpoint_id": "cp",
                "subject": dict(SUBJECT),
                "page": _page(),
                "selectors": (),
            }
        )
    with pytest.raises(Exception, match="page"):
        PageStateConfig.model_validate(
            {
                "evidence_id": "page-5",
                "checkpoint_id": "cp",
                "subject": dict(SUBJECT),
                "selectors": ("#confirm",),
            }
        )


def test_pws13_live_browser_self_gating() -> None:
    """No custom marker needed: self-skip unless explicitly opted in."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    if os.environ.get("NITELOS_RUN_PLAYWRIGHT_LIVE") != "1":
        pytest.skip(
            "live browser capture: set NITELOS_RUN_PLAYWRIGHT_LIVE=1 "
            "(needs nitelos[playwright] + installed browsers)"
        )
    code = (
        "from playwright.sync_api import sync_playwright\n"
        "from nitelos.integrations.playwright_capture import capture_page_state\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.launch()\n"
        "    page = browser.new_page()\n"
        "    page.goto('data:text/html,<h1 id=h>ok</h1>')\n"
        "    result = capture_page_state(\n"
        "        page, ('#h',), evidence_id='live-1', checkpoint_id='cp', subject={'page': 'live'}\n"
        "    )\n"
        "    assert result.error is None, result.error\n"
        "    browser.close()\n"
        "print('live-ok')\n"
    )
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True, cwd=root)
    assert proc.returncode == 0, proc.stderr
    assert "live-ok" in proc.stdout
