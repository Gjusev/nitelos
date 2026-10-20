"""The git collector (plan section F2, NIT-018; extra ``nitelos[git]``).

Stdlib-only; runs exactly four fixed, hardened argvs through the shared
NIT-017 runner (``nitelos.collect._process.run_allowed`` — no shell, absolute
PATH-only executable resolution, scrubbed environment, hard tree-killing
timeout, raw-output cap):

- ``git -c core.fsmonitor=false rev-parse HEAD``
- ``git -c core.fsmonitor=false status --porcelain=v2 --branch``
- ``git -c core.fsmonitor=false log -1 --format=%s%n%ct``
- ``git -c core.fsmonitor=false rev-list --left-right --count @{upstream}...HEAD``

plus the environment hardening ``GIT_OPTIONAL_LOCKS=0`` and
``GIT_CONFIG_NOSYSTEM=1``. There is DELIBERATELY no ``safe.directory``
bypass: a repository git refuses as dubious ownership fails the collection
(COLLECTOR_UNAVAILABLE) instead of silently bypassing git's ownership check.

Observations are one item whose data is ``{"git": {...}}`` so criteria point
at ``/git/head_sha``, ``/git/dirty_count`` and friends. Semantics:
``dirty_count``/``dirty_paths`` count tracked changes (porcelain v2 ``1``/``2``/``u``
entries); untracked files are counted separately (``untracked_count``). A
detached head reports ``branch: null`` with ``detached: true``; a repository
without commits (or without an upstream) reports ``head_sha``/``last_commit``
/``ahead``/``behind`` as null rather than failing. ``dirty_paths`` is capped
at 200 and by ``limits.max_list_items`` (the framework limit wins), with the
dropped count in ``dirty_paths_truncated``. The provenance ``sha256`` digests
the concatenated raw stdouts of the commands that ran; ``raw_bytes`` is their
total size (zero-clean trees are legitimate).
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from nitelos.collect import (
    CollectionResult,
    CollectorCapabilities,
    CollectorConfig,
    CollectorError,
    CollectorErrorCode,
    ProvenanceRecord,
    cap_list,
)
from nitelos.collect._process import ProcessOutput, run_allowed
from nitelos.schemas import Evidence, canonical_json

__all__ = ["ALLOWLIST", "COLLECTOR", "GitCollector", "GitCollectorConfig"]

_HARDENING = ("-c", "core.fsmonitor=false")
ALLOWLIST: tuple[tuple[str, ...], ...] = (
    ("git", *_HARDENING, "rev-parse", "HEAD"),
    ("git", *_HARDENING, "status", "--porcelain=v2", "--branch"),
    ("git", *_HARDENING, "log", "-1", "--format=%s%n%ct"),
    ("git", *_HARDENING, "rev-list", "--left-right", "--count", "@{upstream}...HEAD"),
)
_GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1"}
_MAX_DIRTY_PATHS = 200
_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _run(*, argv: tuple[str, ...], cwd: Path, timeout_s: float, max_raw_bytes: int) -> ProcessOutput:
    """The only subprocess path: fixed argv, hardened env, through the shared runner."""
    return run_allowed(
        argv=argv,
        allowlist=ALLOWLIST,
        timeout_s=timeout_s,
        max_raw_bytes=max_raw_bytes,
        cwd=cwd,
        extra_env=_GIT_ENV,
    )


class GitCollectorConfig(CollectorConfig):
    """Git collector config: where the repository lives (context via cwd, never argv)."""

    repo_path: str = Field(min_length=1, max_length=1024)


class GitCollector:
    """Read-only collector over one git repository's current state."""

    config_model = GitCollectorConfig

    @property
    def id(self) -> str:
        return "git"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(evidence_kinds=("observation",))

    def collect(self, config: GitCollectorConfig) -> CollectionResult:
        repo = Path(config.repo_path)
        outputs: list[bytes] = []
        invocations: list[str] = []

        def run(argv: tuple[str, ...]) -> ProcessOutput:
            output = _run(
                argv=argv,
                cwd=repo,
                timeout_s=config.limits.timeout_s,
                max_raw_bytes=config.limits.max_raw_bytes,
            )
            outputs.append(output.stdout)
            invocations.append(" ".join(argv))
            return output

        status = run(ALLOWLIST[1])
        if status.returncode != 0:
            # not a repository, dubious ownership, or a broken git: no state to collect
            raise CollectorError(CollectorErrorCode.UNAVAILABLE)
        state = _parse_status(status.stdout.decode("utf-8", errors="replace"))

        head_sha: str | None = None
        last_commit: dict[str, Any] | None = None
        if state["has_commits"]:
            rev_parse = run(ALLOWLIST[0])
            candidate = rev_parse.stdout.decode("utf-8", errors="replace").strip()
            if rev_parse.returncode == 0 and _SHA_RE.fullmatch(candidate):
                head_sha = candidate
            log = run(ALLOWLIST[2])
            if log.returncode == 0:
                subject, _, stamp = log.stdout.decode("utf-8", errors="replace").partition("\n")
                timestamp = int(stamp.strip()) if stamp.strip().isdigit() else None
                last_commit = {
                    "subject_sha256": hashlib.sha256(subject.encode("utf-8")).hexdigest(),
                    "timestamp": timestamp,
                }

        ahead: int | None = state["ahead"]
        behind: int | None = state["behind"]
        if state["upstream"]:
            counts = run(ALLOWLIST[3])
            if counts.returncode == 0:
                left, _, right = counts.stdout.decode("utf-8", errors="replace").partition("\t")
                if left.strip().isdigit() and right.strip().isdigit():
                    behind = int(left.strip())
                    ahead = int(right.strip())

        paths, truncated = cap_list(state["dirty_paths"], min(_MAX_DIRTY_PATHS, config.limits.max_list_items))
        data: dict[str, Any] = {
            "git": {
                "head_sha": head_sha,
                "branch": state["branch"],
                "detached": state["detached"],
                "dirty_count": len(state["dirty_paths"]),
                "dirty_paths": list(paths),
                "dirty_paths_truncated": truncated,
                "untracked_count": state["untracked_count"],
                "ahead": ahead,
                "behind": behind,
                "upstream": state["upstream"],
                "last_commit": last_commit,
            }
        }
        item = Evidence.observation(
            id=config.evidence_id,
            sequence=config.sequence_start,
            captured_at=datetime.now(UTC),
            checkpoint_id=config.checkpoint_id,
            source_id=self.id,
            subject=config.subject,
            phase="final",
            channel="external_api",
            data=data,
        )
        raw = b"".join(outputs)
        return CollectionResult(
            collector_id=self.id,
            collector_version=self.version,
            evidence=(item,),
            provenance=(
                ProvenanceRecord(
                    evidence_id=item.id,
                    collector_id=self.id,
                    collector_version=self.version,
                    source="git repository (path in config)",
                    invocation="; ".join(invocations),
                    captured_at=item.captured_at,
                    subject=config.subject,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    raw_bytes=len(raw),
                    normalized_bytes=len(canonical_json(data).encode("utf-8")),
                ),
            ),
        )


def _parse_status(text: str) -> dict[str, Any]:
    """Parse ``git status --porcelain=v2 --branch`` output (documented format).

    Paths may contain spaces (field-split with limits); C-quoted paths are
    taken verbatim (documented limitation: exotic names stay quoted).
    """
    branch: str | None = None
    detached = False
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    has_commits = False
    dirty_paths: list[str] = []
    untracked_count = 0
    for line in text.splitlines():
        if line.startswith("# branch.oid "):
            has_commits = line.split()[2] != "(initial)"
        elif line.startswith("# branch.head "):
            value = line.split()[2]
            if value == "(detached)":
                detached = True
            else:
                branch = value
        elif line.startswith("# branch.upstream "):
            upstream = line.split()[2]
        elif line.startswith("# branch.ab "):
            for token in line.split()[2:]:
                if token.startswith("+") and token[1:].isdigit():
                    ahead = int(token[1:])
                elif token.startswith("-") and token[1:].isdigit():
                    behind = int(token[1:])
        elif line.startswith("1 "):
            dirty_paths.append(line.split(None, 8)[8])
        elif line.startswith("2 "):
            dirty_paths.append(line.split(None, 9)[9].partition("\t")[0])
        elif line.startswith("u "):
            dirty_paths.append(line.split(None, 9)[9])
        elif line.startswith("? "):
            untracked_count += 1
    return {
        "branch": branch,
        "detached": detached,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "has_commits": has_commits,
        "dirty_paths": dirty_paths,
        "untracked_count": untracked_count,
    }


#: The instance the CLI kind table points at ("module:attribute").
COLLECTOR = GitCollector()
