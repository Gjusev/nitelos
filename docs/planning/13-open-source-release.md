# Open-source release and adoption

Target Apache-2.0 for Nitelos-authored code, docs and fixtures. Package/repository names are proposed, not reserved. No release/publish operation is authorized by this planning deliverable.

## Documentation deliverables for implementation

The later application README should communicate in its first screen: project name/tagline, a concrete incomplete-task example, scope-relative meaning of verified success, a short deterministic quickstart, and the distinction between deterministic checks and experimental visual inference. No benchmark badge before a real run; no model branding in the project title.

Required pages: installation/core/local/eval extras; quickstart; explicit success criteria; evidence/provenance limits; sync/async lifecycle; error and abstention handling; model/backends and compatibility matrix; custom adapter conformance; bounded traces/caller Playwright recipe; evaluation and calibration limitations; security/privacy; performance measurement and known failure modes; contribution guide, issue templates and release changelog. Plain Markdown is sufficient. MkDocs is optional only after content exists.

Examples must include deterministic failure despite an agent success summary; success from an admissible supplied state; abstention with missing external confirmation; optional screenshot inference with `model_inferred` shown; custom backend with invalid-output handling; offline batch evaluation. Use synthetic accounts, IDs and original UI assets. Paid infrastructure is not needed for the primary demo.

## Package and asset release checklist

1. Recheck [PyPI project endpoint](https://pypi.org/pypi/nitelos/json) and publishing authority; initial 404 did not reserve it. Recheck proposed GitHub repository permissions. If name is unavailable, ask the maintainer for a naming decision rather than changing imports silently.
2. Verify `requires-python`, core requirements, extras and final lock against the tested matrix. Build reproducible wheel/sdist from the release revision; record hashes and environment. Bit-for-bit reproducibility is claimed only if actually compared under controlled build timestamps/tool versions.
3. Inspect artifacts: source, py.typed, license/notice and intended small authored fixtures only. No model weights, user traces, private benchmark labels, credentials, caches, virtual environments or giant images.
4. Inventory every direct/transitive distribution in core/local/eval/dev environments, including binary bundled libraries and model-file licensing. Retain source URLs, exact versions/hashes, SPDX/license text, notices and inclusion decision. Optional does not mean exempt from review.
5. Model weights are separately provisioned by users from a pinned upstream revision under their license. Do not bundle model training datasets. Do not bundle AgentHorizon/UI-Venus/AbstentionBench or third-party website screenshots. CUAVerifierBench is separately obtained only after its card and third-party content/privacy review.
6. Confirm all G1–G8 evidence from [scope](09-mvp-scope.md), with unresolved issues explicitly recorded. Prepare release notes with experimental-backend caveat and complete benchmark limitations.
7. Maintainer reviews the concrete artifacts, package availability, notices and publication permissions. If authorized, publish via protected trusted publishing. This plan does not instruct GLM to publish automatically.

Apache project licensing does not relicense dependency assets. The [Apache third-party policy](https://www.apache.org/legal/resolved.html) is review guidance, not project-specific legal advice. Ambiguous or missing rights block copying/redistribution; they do not block citing public documentation.

## Versioning and governance

Initial release 0.1.0, wire schema 1. Patch releases preserve public field semantics and parser behavior; bug fixes that alter documented decisions need explicit release notes and regression cases. Breaking changes require minor pre-1.0 version, ADR and migration guidance. Avoid unstable experimental extras leaking into core imports. Document supported model revision/runtime combinations; no promise of all OpenAI-compatible servers or all Transformers releases.

Use small issue templates for verification bug (request redacted, expected criteria, observed result, versions), backend compatibility, and documentation. Security reports use private reporting and a SECURITY policy. Ask contributors to provide minimal synthetic reproductions, never real screenshots with secrets. DCO sign-off is the recommended lightweight contribution attestation; no CLA infrastructure is needed unless ownership requirements change.

## Adoption validation

Demonstrate the offline incomplete-form scenario in CI and docs. Invite two independent developers to integrate after their own agent checkpoint and report time-to-first-result, contract confusion and missing evidence types. No star/adoption targets or publicity claims. A useful existing Inspect scorer integration may be a better adoption path than adding a dashboard. If users only need their current test assertions, explain that plainly rather than claiming a model adds assurance.

Measured performance table must name CPU/GPU, memory method, model/prompt revision, dependency lock, input sizes, cold/warm latency, valid-output/abstention/error rates and actual cost or null. Synthetic performance is not evidence of production payment/upload reliability. Document that local visual outputs can be wrong and are disallowed by default.
