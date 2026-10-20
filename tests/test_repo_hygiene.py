"""HYG-01..03: repository hygiene guards for NIT-016 (changelog, issue forms, README framing)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMS = ("bug_report.yml", "feature_request.yml", "false_verdict.yml")


def test_hyg01_changelog_exists_with_unreleased_and_010() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [Unreleased]" in changelog
    assert "## [0.1.0] - 2026-10-16" in changelog


def test_hyg02_issue_templates_exist_with_required_keys() -> None:
    template_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
    for name in FORMS:
        text = (template_dir / name).read_text(encoding="utf-8")
        for key in ("name:", "description:", "body:"):
            assert re.search(rf"^{key}", text, re.MULTILINE), (name, key)
    config = (template_dir / "config.yml").read_text(encoding="utf-8")
    assert re.search(r"^blank_issues_enabled:", config, re.MULTILINE)


def test_hyg03_readme_has_no_first_claims_and_names_conformance_denominator() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in readme.splitlines()
        if re.search(r"(?i)\bfirst\b", line) and "run a first check" not in line
    ]
    assert not offenders, offenders
    section = readme.split("## Evaluation status", 1)[1].split("\n## ", 1)[0]
    assert "conformance" in section
    assert "120 of 120" in section
