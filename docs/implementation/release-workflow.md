# Release workflow sketch (NIT-015 — REVIEW ONLY; nothing lands in .github/ yet)

Proposed GitHub Actions shape for the release candidate. Every action pinned by full
SHA; least-privilege permissions; no untrusted-PR code in privileged contexts (no
`pull_request_target`). Publishing is a separate authorized maintainer action — this
workflow builds, audits and attests; the human presses the button.

```yaml
name: release-prep
on:
  push:
    tags: ["v0.1.*"]
  workflow_dispatch: # manual release-candidate builds

permissions:
  contents: read # the minimum; publishing uses the OIDC trusted-publishing grant
                 # requested ONLY in the publish job, not here

concurrency:
  group: release-prep-${{ github.ref }}
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@<sha> # v7.0.1 3d3c42e5… (same pin as ci.yml)
        with:
          persist-credentials: false
      - uses: astral-sh/setup-uv@<sha> # v10.3.0 1c37ad07… (same pin as ci.yml)
        with:
          python-version: "3.12"
          enable-cache: true
          cache-dependency-glob: uv.lock
      - run: uv sync --frozen --group dev --extra eval
      - run: uv run --extra eval pytest -q            # full offline suite
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run mypy
      - name: Build distributions
        run: uv build
      - name: Record digests
        run: |
          sha256sum dist/* > dist/dists.sha256
          cat dist/dists.sha256 >> "$GITHUB_STEP_SUMMARY"
      - uses: actions/upload-artifact@<sha> # pin at landing; dists + dists.sha256
        with:
          name: dist
          path: dist/
          retention-days: 14 # doc 12 default; only reviewed synthetic data may be uploaded

  attest:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write # artifact attestation via OIDC; scoped to this job
    steps:
      - uses: actions/download-artifact@<sha> # pin at landing
        with: { name: dist, path: dist }
      - uses: actions/attest-build-provenance@<sha> # pin at landing
        with:
          subject-path: "dist/nitelos-*.whl dist/nitelos-*.tar.gz"

  audit: # G6 supply-chain row; ADVISORY DB ACCESS IS NETWORK — disclosed per doc 12
    needs: build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha>
        with: { persist-credentials: false }
      - uses: astral-sh/setup-uv@<sha>
        with: { python-version: "3.12" }
      - run: uv sync --frozen --group dev --extra eval --extra local
      - name: Vulnerability audit over the full lock
        run: uv export --frozen --all-extras --format requirements-txt -o req.txt &&
             uvx pip-audit -r req.txt --strict || echo "::warning::pip-audit findings — triage before publish"
        # network: yes (advisory databases); the only job allowed network
      - name: License inventory completeness (REL-04)
        run: uv run python - <<'PY'
        # sketch of tests/test_license_inventory.py (land at release):
        #   parse uv.lock [[package]] name/version; for the core/eval/local closures,
        #   assert each appears in docs/implementation/dependency-licenses.md
        PY

  release-notes: # G8 honesty gate — the report pack is authored by NIT-013, not CI
    needs: [build, attest, audit]
    runs-on: ubuntu-latest
    steps:
      - run: echo "Release notes are authored from reports/ + release-checklist.md; CI never generates result claims."
```

## Publish job (sketch — enabled only by the maintainer at release time)

Trusted publishing via PyPI OIDC (no long-lived token in the repo):

```yaml
  publish:
    needs: [build, attest, audit]
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    environment: pypi # protected environment; maintainer approval required
    permissions:
      id-token: write # the trusted-publishing grant, scoped here
    steps:
      - uses: actions/download-artifact@<sha>
        with: { name: dist, path: dist }
      - uses: pypa/gh-action-pypi-publish@<sha> # pin at landing
```

## Rules carried into the real workflow

1. Pins: reuse the reviewed checkout/setup-uv SHAs from ci.yml verbatim; new actions
   (upload/download-artifact, attest-build-provenance, pip-audit, pypi-publish) get
   SHA-pinned and recorded in decisions.md before landing.
2. Permissions: `contents: read` everywhere; `id-token: write` only in attest and
   publish; no `pull_request_target`; untrusted PR code never runs privileged.
3. The audit job is the ONLY networked job (advisory DBs) — disclosed in the job
   name/comment per doc 12; findings are triaged by the maintainer, never auto-gated
   to green.
4. Artifact retention 14 days; only dists + digests uploaded (no screenshots, no user
   data — nothing else exists in CI by construction).
5. Publish is manual + protected-environment gated; a failing or failed-recorded G3
   does not block the build, but the release notes must carry the record (ADR-012
   ship rule).
