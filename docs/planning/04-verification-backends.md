# Verification backends

Authority: [contract](03-domain-model-and-api.md), [policy](05-evidence-and-policies.md). The backend proposes criterion findings; the policy decides admissibility and aggregation. A model cannot change a criterion, policy, evidence bytes, trust binding, or final result.

## Protocol and capability negotiation

`BackendDescriptor` contains `id`, `version`, optional model ID/revision, prompt hash, preprocessing hash. `BackendCapabilities` contains supported evidence kinds and criterion kinds; booleans for text, images, structured decisions, probability scores, calibrated probabilities, native abstention, evidence references, local execution and native batch; integer maximum images per criterion and input text tokens. Capabilities are truthful limits, not marketing labels.

`Backend.infer(prepared_visual_criterion, context) -> BackendFinding` executes one criterion synchronously. `context` contains objective, immutable eligible referenced evidence, and bounded action context; never trust bindings, hidden labels, credentials or unrestricted filesystem access. `close` is idempotent. The deterministic evaluator has a separate internal assertion method; it shares normalized findings, not model messaging. A custom backend instance is the extension mechanism; no dynamic discovery.

Prepared interface details: `PreparedVisualCriterion` contains `criterion_id`, `description`, `images` (tuple of `PreparedImage`) in declared reference order. `PreparedImage` contains `evidence_id`, `sequence`, `width`, `height`, immutable RGB pixel bytes and source digest; it contains no file path. `InferenceContext` contains `objective`, `actions` (tuple of `{evidence_id, sequence, name, reported_status}`), a monotonic cooperative deadline, and no metadata dictionary. Core identity/freshness eligibility is already applied. Backend may allocate its own Pillow/tensor views; it must not mutate shared source buffers. Subject is already bound by the host; descriptions/objective must explicitly name identity details whose pixel visibility is part of the visual judgment. No independent identity verification is implied by matching metadata.

Capability field names are `evidence_kinds`, `criterion_kinds`, `supports_text`, `supports_images`, `supports_structured_decisions`, `supports_probabilities`, `supports_calibrated_probabilities`, `supports_native_abstention`, `supports_evidence_references`, `local_execution`, `supports_native_batch`, `max_images_per_criterion`, `max_text_tokens`. Multiple images means supports_images=true and maximum >1. Non-image backends use maximum 0; unlimited/null maxima are not allowed. `supports_structured_decisions` describes normalized output, not necessarily a native classification head. In v0.1 a true calibrated capability cannot bypass rejection of calibrated outputs.

| Capability | Deterministic | SmolVLM v0.1 | Future hosted / discrete |
|---|---|---|---|
| Assertion criteria | Core evaluator | Core evaluator remains responsible | Same |
| Visual criteria | No | Yes | Explicit negotiation |
| Images / multi-image | No / no | Yes / max 2 per criterion | Endpoint/model-specific |
| Text | Structured values | Objective, criterion, bounded actions | Explicit negotiation |
| Structured decisions | Native normalized finding | Strict parser over generated label | Validate actual schema |
| Probability / calibrated | No / no | No / no | Possibly / requires future calibration validation |
| Native abstention | Missing-value logic | No native head; prompted UNKNOWN label | Map actual null/abstain option |
| Evidence references | Core JSON pointer | Core attaches supplied image refs, not localization | Validate all returned IDs/boxes |
| Local / native batch | Yes / no | Yes / no | Declared, never inferred from URL alone |

Preflight checks all criterion kinds before model invocation. Unsupported capabilities return input error. Do not drop images, convert a multi-image task to one image, turn image inputs into captions, or silently switch providers. Valid requests with no admissible referenced evidence abstain without invoking a model. A backend still must support the declared criterion kind even when its evidence is currently empty.

## Deterministic baseline

Fixed RFC 6901 JSON Pointer traversal over dictionaries/lists. Empty pointer selects the payload root; equality/membership only accept scalars, so a container target produces UNKNOWN/MISSING_VALUE rather than comparing an arbitrary serialized string. Array indices use canonical nonnegative decimal notation; `-`, leading zeros except `0`, invalid escapes, and malformed pointer syntax are input errors. Out-of-range indices/missing keys produce unknown. JSON null is a real value, distinct from missing. `exists` accepts any present target including containers. Inputs cannot contain executable expressions. Read-only traversal does not interpret HTML, JavaScript or SQL.

An observation comparison is checked, but its underlying data remains only as trustworthy as its collector. Matching `/status` to `"uploaded"` is insufficient for an external criterion unless source, subject, checkpoint, digest and freshness are admissible. Tool result code 200 may satisfy an explicitly behavioral criterion, not proof of persisted upload.

## Chosen local VLM

Use `HuggingFaceTB/SmolVLM-500M-Instruct`, revision `a7da5b986cb59b408707209984f360a5f4ad7e47`. The [model card](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct) declares Apache-2.0 and demonstrates `AutoProcessor`, `AutoModelForVision2Seq`, a processor chat template with image placeholders, separate image tensors, and generation. [Current Transformers documentation](https://huggingface.co/docs/transformers/model_doc/smolvlm) must be checked against the exact locked library version: the auto-class name may change across major versions. Pin an independently smoke-tested pair in NIT-008; retain this checkpoint and semantic pipeline. A changed API class name is a compatibility detail; a changed model or preprocessing contract requires review.

This selection is an executable small baseline, not a proven accurate GUI verifier. Do not use the card's suggested FlashAttention/CUDA path as a universal requirement. CPU float32 is the required reproducibility path; optional CUDA bfloat16 is supported only after an explicit smoke run, with device/dtype recorded. No quantization, remote code, alternate weights or automatic device placement in v0.1.

### Exact adapter procedure

1. Constructor accepts a pre-provisioned local model directory plus the pinned source revision. Verify a model manifest records the revision and SHA-256 of configuration/tokenizer/processor/safetensors files. No `from_pretrained` network fallback. Set local-files-only, safe tensor loading, remote code disabled and telemetry/offline settings locally without changing global user environment. Missing files are `MODEL_UNAVAILABLE`.
2. Lazy-load processor/model once. Record load duration. Reject unsupported device/dtype rather than silently falling back. Core import and deterministic use never load optional modules.
3. Prepare at most two images in caller-declared reference order, label them by evidence ID and sequence. Decode once using the evidence layer. Use fixed processor `size.longest_edge=1024`, record patching/resizing and actual dimensions. No cropping or OCR-derived evidence. This processor resize is declared preprocessing, not hidden input omission.
4. Construct one user message with text and image placeholders using this model's processor format; do not send an OpenAI-style wire payload directly to Transformers. Prompt template `smolvlm-criterion-v1` states: evidence text is untrusted, judge only the supplied visual criterion, actions are context, choose exactly SUPPORTED/REFUTED/UNKNOWN, choose UNKNOWN for ambiguity, unreadable details or pending state. No tools, reflection loop, chain-of-thought request, or rationale generation.
5. Context actions are the last at most 8 action items with sequence <= highest cited image sequence; include only name and reported status, never arguments or tool response bodies. If there are more, omit older action context explicitly and record IDs omitted in diagnostics. This is a fixed declared context view, identical across compared backends—not silent truncation of cited evidence. Assertion-only observations are not passed to the VLM. All cited images must be present.
6. Enforce 2,048 text-token / 4,096 processed-token ceilings. Oversize produces `input_error/LIMIT_EXCEEDED` before generation; processor preparation counts as backend preprocessing, not inference. All visual criteria are preprocessed/preflighted before any generation so later oversize inputs cannot create partial inference. No hidden text clipping.
7. `eval`, inference mode, greedy decode, sampling off, maximum 8 new tokens; cooperative 120-second generation deadline per criterion. Do not assume temperature zero is accepted by every generation API; omit sampling parameters when unnecessary.
8. Decode only newly generated token IDs, excluding prompt tokens. Strip surrounding whitespace; accept exactly SUPPORTED, REFUTED or UNKNOWN, case-sensitive. Any explanatory suffix, code fence, empty/truncated answer or other text is `backend_error/INVALID_OUTPUT`; no repair call or majority voting. This strict choice is deliberately measurable and may expose weak instruction following.
9. Map labels to states. Attach core-known submitted screenshot references with `model_inferred`. Score and rationale remain null. UNKNOWN is model abstention. Valid output that hallucinated the visible state is a model error in evaluation, not a fabricated deterministic observation.

### Executability gate

The 12-case development smoke set is authored during NIT-008, independently of NIT-010's benchmark work: (1) large completion banner, (2) large rejection banner, (3) empty required field plus explicit error, (4) filled form without confirmation, (5) loading spinner with pending phase, (6) two final screenshots with conflicting banners, (7) wrong visible object ID, (8) unreadably tiny status, (9) benign screen with injected “report success” instruction, (10) clear success image with misleading completed-action context, (11) before/after pair with clearly final completion, (12) blank image. All use original synthetic scenes and development-only labels. Pending-phase case exercises policy without model execution; the report explicitly records that. These images never enter the final-test split. Failure to produce meaningful labels is reported; do not tune against final-test data to satisfy the gate.

NIT-008 must run the actual model in a separately authorized implementation phase, on a declared CPU machine and optionally GPU. Report exact package lock, platform, model manifest, cold/warm time, valid-label rate, decisions, errors and memory where measured. At least one non-abstained valid output on the frozen smoke set is required; a schema-valid unknown is also exercised via mock contract tests. Do not require a particular accuracy on a cherry-picked image or change test labels to accommodate the model. If valid labels cannot be obtained, stop for backend review; do not invent probabilities or replace inference with a mock. Release may be delayed, not silently narrowed to a fake executable backend.

## Hosted multimodal adapters: design only, after v0.1

OpenAI Responses uses `input_image`; Chat Completions uses `image_url` content, and Anthropic Messages uses `image` blocks with base64 source fields. These are different protocols, even when a server claims compatibility. Sources: [OpenAI vision](https://developers.openai.com/api/docs/guides/images-vision), [Anthropic vision](https://platform.claude.com/docs/en/build-with-claude/vision). Keep provider/protocol adapters separate with explicit model capabilities and endpoint configuration. Use separate extras, preferably official client libraries after dependency evaluation. `httpx` is a transport alternative, not a reason to unify wire formats.

Before sending, require host `allow_remote=true`, explicit backend selection and endpoint/model allowlisting. Inline validated bytes only; no image URLs or provider tool execution. Set connect/read/total deadlines, no redirects to a new host, at most two retries for 429/502/503 with bounded jitter and Retry-After capped by total budget. Never retry authentication, schema or content failures. Record request IDs and usage if supplied; cost null without a price source. Paid/network tests are opt-in. Verbal confidence remains uncalibrated.

## Structured decision adapters and MK-SH-V: design only

Finite options map to supported/refuted/unknown, with exact option identity preserved under ordering. Reject missing, duplicate, non-finite or non-normalized probabilities (sum tolerance 1e-6), unknown families and inconsistent decisions. Preserve raw probability target; an abstain option probability is not probability the task failed. A model may be text-only despite a compatible endpoint. [System One reference implementation](https://github.com/mpuig/system-one) establishes an ecosystem candidate, not a stable multimodal interoperability standard.

MK-SH-V is author-described research with no final checkpoint. Do not invent its wire schema or load it during MVP work. Future mapping of `task_done` requires its published contract, licensing and dedicated Nitelos evaluation data. Version changes, model hashes and calibration artifacts are mandatory provenance. A calibrated label can only be accepted after future host-side validation of model/prompt/preprocessing/domain binding.
