"""GIT-01..13: the git collector on the NIT-017 framework (NIT-018, plan F2).

Real throw-away repositories in tmp dirs (acceptance requires Windows and
Linux); skipped with an explicit reason when no git binary is on PATH. No
network: upstreams are local bare repositories pushed over the filesystem.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from _collector_contract import assert_contract
from nitelos import Verifier, cli, parse_request
from nitelos.collect import (
    CollectorConfig,
    CollectorErrorCode,
    host_trust_bindings,
    run_collector,
)
from nitelos.collect.git import ALLOWLIST, GitCollector, GitCollectorConfig

GIT = shutil.which("git")
pytestmark = pytest.mark.skipif(GIT is None, reason="git binary required for the git collector tests")
SUBJECT = {"repo": "example/app"}


def _git(*args: str, cwd: Path) -> None:
    subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(
    path: Path,
    *,
    commits: int = 1,
    upstream: bool = False,
    extra_local_commits: int = 0,
    dirty_files: int = 0,
    untracked_files: int = 0,
    detach: bool = False,
) -> Path:
    path.mkdir(parents=True)
    _git("init", "-b", "main", cwd=path)
    _git("config", "user.email", "test@example.invalid", cwd=path)
    _git("config", "user.name", "Test", cwd=path)
    for index in range(commits):
        # newline="\n": fixtures stay byte-identical under any autocrlf setting,
        # so the collector's scrubbed-env git (no user config) sees them clean
        (path / f"file{index}.txt").write_text(f"content {index}\n", encoding="utf-8", newline="\n")
        _git("add", ".", cwd=path)
        _git("commit", "-m", "initial commit" if index == 0 else f"commit {index}", cwd=path)
    if upstream:
        origin = path.parent / f"{path.name}-origin.git"
        _git("init", "--bare", "-b", "main", str(origin), cwd=path)
        _git("remote", "add", "origin", str(origin), cwd=path)
        _git("push", "-u", "origin", "main", cwd=path)
    for index in range(extra_local_commits):
        (path / f"local{index}.txt").write_text(f"local {index}\n", encoding="utf-8", newline="\n")
        _git("add", ".", cwd=path)
        _git("commit", "-m", f"local {index}", cwd=path)
    for index in range(dirty_files):
        (path / f"file{index % max(1, commits)}.txt").write_text(
            f"dirty {index}\n", encoding="utf-8", newline="\n"
        )
    for index in range(untracked_files):
        (path / f"untracked{index}.txt").write_text("x\n", encoding="utf-8", newline="\n")
    if detach:
        _git("checkout", "--detach", cwd=path)
    return path


def _config(repo: Path, **over: Any) -> GitCollectorConfig:
    values: dict[str, Any] = {
        "evidence_id": "obs-git-1",
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
        "repo_path": str(repo),
    }
    values.update(over)
    return GitCollectorConfig.model_validate(values)


def _collect(repo: Path, **over: Any) -> Any:
    return run_collector(GitCollector(), _config(repo, **over))


def _git_data(result: Any) -> dict[str, Any]:
    (item,) = result.evidence
    return dict(item.data)["git"]  # type: ignore[return-value]


# --------------------------------------------------------------------------
# GIT-01..06: observations from real repository states
# --------------------------------------------------------------------------


def test_git01_clean_repo_on_main(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    result = _collect(repo)
    assert result.error is None, result.error
    data = _git_data(result)
    assert data["head_sha"]
    assert len(data["head_sha"]) == 40
    assert data["branch"] == "main"
    assert data["detached"] is False
    assert data["dirty_count"] == 0
    assert list(data["dirty_paths"]) == []
    assert data["untracked_count"] == 0
    assert data["last_commit"]["subject_sha256"] == hashlib.sha256(b"initial commit").hexdigest()
    assert isinstance(data["last_commit"]["timestamp"], int)
    (record,) = result.provenance
    assert record.evidence_sha256 == result.evidence[0].sha256
    assert "status --porcelain=v2 --branch" in record.invocation


def test_git02_dirty_and_untracked_counts(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo", commits=2, dirty_files=2, untracked_files=1)
    data = _git_data(_collect(repo))
    assert data["dirty_count"] == 2
    assert data["untracked_count"] == 1
    assert sorted(data["dirty_paths"]) == ["file0.txt", "file1.txt"]


def test_git03_dirty_paths_capped_with_explicit_truncation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo", commits=3, dirty_files=3)
    result = _collect(repo, limits={"max_list_items": 2})
    data = _git_data(result)
    assert len(data["dirty_paths"]) == 2
    assert data["dirty_paths_truncated"] == 1


def test_git04_upstream_ahead_behind(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo", upstream=True, extra_local_commits=1)
    data = _git_data(_collect(repo))
    assert data["upstream"] == "origin/main"
    assert data["ahead"] == 1
    assert data["behind"] == 0


def test_git05_detached_head(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo", detach=True)
    data = _git_data(_collect(repo))
    assert data["detached"] is True
    assert data["branch"] is None


def test_git06_unborn_repo_has_nulls_not_errors(tmp_path: Path) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    _git("init", "-b", "main", cwd=repo)
    result = _collect(repo)
    assert result.error is None, result.error
    data = _git_data(result)
    assert data["head_sha"] is None
    assert data["last_commit"] is None
    assert data["ahead"] is None
    assert data["behind"] is None


# --------------------------------------------------------------------------
# GIT-07..09: failure mapping, hardening, allowlist
# --------------------------------------------------------------------------


def test_git07_not_a_repository_is_unavailable(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    result = _collect(plain)
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.UNAVAILABLE
    assert result.evidence == ()


def test_git08_missing_git_binary_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _init_repo(tmp_path / "repo")
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    result = _collect(repo)
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.UNAVAILABLE


def test_git09_fixed_allowlist_and_hardened_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_repo(tmp_path / "repo", upstream=True)
    import nitelos.collect.git as git_module

    seen: list[dict[str, Any]] = []
    real = git_module.run_allowed

    def _spy(**kwargs: Any) -> Any:
        seen.append({"argv": kwargs["argv"], "extra_env": dict(kwargs["extra_env"])})
        return real(**kwargs)

    monkeypatch.setattr(git_module, "run_allowed", _spy)
    result = _collect(repo)
    assert result.error is None
    assert seen, "the collector must go through the shared runner"
    argv_tuples = {tuple(call["argv"]) for call in seen}
    assert argv_tuples <= set(ALLOWLIST)
    assert ("git", "-c", "core.fsmonitor=false", "status", "--porcelain=v2", "--branch") in argv_tuples
    for call in seen:
        assert call["extra_env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert call["extra_env"]["GIT_CONFIG_NOSYSTEM"] == "1"
        assert "safe.directory" not in " ".join(call["argv"])


def test_git09_allowlist_is_exactly_the_four_plan_commands() -> None:
    assert set(ALLOWLIST) == {
        ("git", "-c", "core.fsmonitor=false", "rev-parse", "HEAD"),
        ("git", "-c", "core.fsmonitor=false", "status", "--porcelain=v2", "--branch"),
        ("git", "-c", "core.fsmonitor=false", "log", "-1", "--format=%s%n%ct"),
        ("git", "-c", "core.fsmonitor=false", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"),
    }


# --------------------------------------------------------------------------
# GIT-10..11: criteria round trip and the contract suite
# --------------------------------------------------------------------------


def _request(result: Any, pointer: str, expected: Any) -> Any:
    (item,) = result.evidence
    document = {
        "schema_version": "1",
        "request_id": "req-git-1",
        "objective": "Repository state matches the claim",
        "checkpoint_id": "cp-1",
        "as_of": item.model_dump(mode="json")["captured_at"],
        "criteria": [
            {
                "id": "c-git",
                "description": "Working tree clean",
                "kind": "assertion",
                "scope": "external",
                "evidence_ids": [item.id],
                "subject": dict(SUBJECT),
                "pointer": pointer,
                "operator": "equals",
                "expected": expected,
            }
        ],
        "evidence": [item.model_dump(mode="json") for item in result.evidence],
        "metadata": {},
    }
    return parse_request(document)


def test_git10_criteria_decide_on_git_state(tmp_path: Path) -> None:
    clean = _collect(_init_repo(tmp_path / "clean"))
    verified = Verifier(trust_bindings=host_trust_bindings(clean)).verify(
        _request(clean, "/git/dirty_count", 0)
    )
    assert verified.decision is not None
    assert verified.decision.value == "success"
    dirty = _collect(_init_repo(tmp_path / "dirty", commits=1, dirty_files=1))
    verified = Verifier(trust_bindings=host_trust_bindings(dirty)).verify(
        _request(dirty, "/git/dirty_count", 0)
    )
    assert verified.decision is not None
    assert verified.decision.value == "failure"


def test_git11_contract_suite_passes(tmp_path: Path) -> None:
    assert_contract(GitCollector(), _config(_init_repo(tmp_path / "repo")))


# --------------------------------------------------------------------------
# GIT-12..13: CLI and config validation
# --------------------------------------------------------------------------


def test_git12_cli_collect_kind(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.KIND_TARGETS["git"] == "nitelos.collect.git:COLLECTOR"
    repo = _init_repo(tmp_path / "repo")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "evidence_id": "obs-git-1",
                "checkpoint_id": "cp-1",
                "subject": dict(SUBJECT),
                "repo_path": str(repo),
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    code = cli.main(["collect", "git", "--config", str(config), "--out", str(out)])
    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["error"] is None
    assert document["collector"]["id"] == "git"
    assert document["evidence"][0]["data"]["git"]["branch"] == "main"
    assert "collected 1" in capsys.readouterr().out


def test_git13_config_validation(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    missing = {
        "evidence_id": "obs-git-1",
        "checkpoint_id": "cp-1",
        "subject": dict(SUBJECT),
    }
    result = run_collector(GitCollector(), missing)
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.CONFIG_INVALID
    unknown = dict(missing)
    unknown["repo_path"] = str(repo)
    unknown["surprise"] = 1
    result = run_collector(GitCollector(), unknown)
    assert result.error is not None
    assert result.error.code is CollectorErrorCode.CONFIG_INVALID
    assert issubclass(GitCollectorConfig, CollectorConfig)
