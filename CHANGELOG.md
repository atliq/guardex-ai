# Changelog

All notable changes to GuardEx are documented in this file. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project tries to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Local web UI served by the reference server: `guardex-server --ui` mounts
  a Playground, a Logs view, and a Config editor at `http://127.0.0.1:8001`.
  Install with `pip install 'guardex-ai[ui]'`. The UI has no authentication,
  so `--ui` refuses a non-loopback `--host` unless `--ui-unsafe-bind` is
  passed.
- `GET/PUT /v1/config`, `POST /v1/config/reset`, `POST /v1/config/save` —
  server-side policy defaults applied to any request field left unset.
  Save writes non-default fields to `guardex.policy.yaml` in the working
  directory, loadable via `GuardExPolicy.from_yaml()`.
- `GET /v1/config/schema` — the declarative field list backing the Config
  page, plus the available PII entity and safety category options.
- `GET /v1/logs`, `GET /v1/logs/stats`, `DELETE /v1/logs` — the last 1000
  screening calls held in memory, with per-gate timings taken from the
  diagnostics the runner already produces. Request text is excluded unless
  the server is started with `--log-text`.
- `GET /v1/meta` — package version and which ML engines are loaded.
- `/v1/screen` accepts `pii_deny_list`, `pii_allow_list`, and
  `pii_custom_context_keywords`. All three were already supported by the
  in-process runner but were not reachable over HTTP.

### Changed

- `/v1/screen` resolves an omitted `pii_threshold` to `DEFAULT_PII_THRESHOLD`
  (0.85) instead of a hardcoded 0.7, matching in-process `Guard()`. Callers
  that relied on the looser server default must now pass `pii_threshold`
  explicitly.

### Deprecated

- `guardex-dashboard` is superseded by `guardex-server --ui`. Its span buffer
  only ever filled from in-process `Guard()` usage, so it showed nothing for
  traffic served by `guardex-server`. It will be removed in a future release.

## [0.2.0] - 2026-07-11

### Added

- Reference server: `guardex.server` (FastAPI) exposes the SDK's HTTP
  protocol (`/v1/screen`, `/v1/screen/batch`, `/v1/classify`,
  `/v1/pii/scan`, `/v1/pii/mask`, `/v1/grounding`, `/v1/health`) over an
  in-process `LocalRunner`. Install with `pip install 'guardex-ai[server]'`,
  run with `guardex-server`.
- `pii_custom_regex` works in server mode, for both `screen()` and
  `screen_batch()`. The reference server validates caller patterns at the
  request boundary: at most 32 patterns, 512 characters each, and every
  pattern must compile.

### Changed

- Local pipeline runs safety classification and PII detection concurrently,
  cutting screen latency to roughly the slower of the two gates.
- Server-mode `Guard` now sends `pii_custom_regex` in the `/v1/screen`
  body when the policy sets it (previously local-only and silently
  ignored in server mode). Servers that ignore unknown JSON fields are
  unaffected; a server that rejects unknown fields will now return a
  validation error for policies using custom regex.

### Fixed

- Pinned `ruff` in the dev extras so CI lint results no longer change
  when a new ruff release alters its default rule set.

## [0.1.1] - 2026-07-08

### Changed

- README: corrected the asset URL, and added a
  from-source install option.

### Fixed

- Resolved `ruff` and `mypy` findings across the SDK and tests; no runtime
  behavior change.
- CI installs the `langchain` and `otel` extras so the integration modules
  are type-checked, and skips numpy stubs in mypy.

## [0.1.0] - 2026-07-08

First public open-source release.

### Added

- `Guard` - single-class entry point for screening text at any of 8
  semantic gates (`input`, `prompt`, `output`, `tool_input`, `tool_output`,
  `retrieval_query`, `retrieval_result`, `stream`).
- Local in-process ML pipeline (`LocalRunner`): input validation, keyword
  gate, Unicode/leet normalization, ONNX safety classifier, GLiNER PII
  detection (31 entity types), embedding topic scope, custom safety
  routes, optional Ollama LlamaGuard cascade, optional NLI grounding.
- `GuardExPolicy` - single dataclass for every screening knob, with
  `from_yaml()` loader and per-context resolution via
  `CachedPolicyResolver`.
- `PIIVault` - reversible PII tokenization with `restore()` mapping
  vault tokens back to original values; ships a default system-prompt
  hint to teach LLMs to use tokens naturally.
- `InjectionDetector` - regex-based prompt-injection + jailbreak
  detector with `extra_patterns` extension point and severity property.
- `ConversationGuard` - sliding-window screening that detects
  multi-turn escalation patterns the per-turn classifier would miss.
- `SafetyRouteEngine` - user-defined blocklist categories via example
  utterances with cosine-similarity matching.
- Async API surface (`ascreen`, `ascreen_batch`, `acheck_grounding`,
  `ascreen_grounded`, `astream`) that bridges to sync in local mode.
- OpenTelemetry instrumentation (`screening_span`, `record_result`)
  and structured audit logging via the `guardex.audit` logger.
- Real-time telemetry dashboard at `http://localhost:7865` via
  `guardex-dashboard` CLI or `start_dashboard()`.
- LangChain integration: `GuardedLLM` (full-pipeline wrap) and
  `GuardExCallbackHandler` (callback-based screening).
- Streaming PII vault restoration via
  `Guard.astream(..., vault=..., restore_mode="buffered"|"stream-safe")`.

### Default configuration

- `pii_threshold = 0.85` (calibrated for GLiNER, keeps real-PII recall
  near 100% while excluding the 0.6-0.8 false-positive band).
- `DEFAULT_PII_ALLOW_LIST` ships 21 conversational tokens (hi, hello,
  ok, ...) as defense-in-depth.
- `block_on_unsafe_input = True`, `block_on_unsafe_output = True`.
- `cascade_mode = "safety"` (auto-downgrades to `"speed"` at boot if
  Ollama is not reachable).
- `grounding_enabled = False` (opt-in; enabling adds a ~700 MB NLI
  model download).
- Block-by-default categories: S1 (Violent Crimes), S3 (Sex-Related
  Crimes), S4 (Child Sexual Exploitation), S9 (Indiscriminate Weapons),
  S11 (Suicide & Self-Harm).

### Known limitations

- Cross-lingual safety classification (English-only patterns).
- Image / audio / video moderation not in scope.
- GCG adversarial suffix attacks and many-shot jailbreaking are
  industry-wide unsolved problems.
- A separate self-hosted server distribution is not included.

[Unreleased]: https://github.com/atliq/guardex-ai/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/atliq/guardex-ai/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/atliq/guardex-ai/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/atliq/guardex-ai/releases/tag/v0.1.0
