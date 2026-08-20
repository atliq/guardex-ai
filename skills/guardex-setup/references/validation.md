# Validation

Read this before finishing a GuardEx integration or changing this skill.

## Validate a Project Integration

Run the host project's normal tests first. Then add or exercise small tests for
the exact boundaries touched:

- safe input passes and uses `result.text`
- unsafe input blocks or raises at `gate="input"`
- output is screened before returning to the user
- PII masking changes the text passed to the LLM
- `pii_action="block"` raises or branches through the app's refusal path
- prompt-injection text blocks on input gates
- tool and RAG gates use `tool_input`, `tool_output`, `retrieval_query`, or
  `retrieval_result` rather than only `input`
- streaming paths raise on unsafe chunks and do not leak partial vault tokens
- server mode handles `/v1/health` and a safe `/v1/screen` request

Prefer mocked GuardEx results for unit tests in the host app. Use live local
models only for smoke/integration tests because first-run downloads are large
and slow.

## Validate This Repository

From the GuardEx repo root:

```bash
python -m pytest tests/
ruff check guardex tests
mypy
```

For targeted checks:

```bash
python -m pytest tests/test_guard.py tests/test_stream.py tests/test_pii_vault.py
python -m pytest tests/test_observe_only.py tests/test_semantic_router.py
python -m pytest tests/test_server.py tests/test_grounding.py
python -m pytest tests/test_smoke.py tests/test_conversation.py
```

## Common Failure Modes

- Calling `screen()` and expecting it to raise. It returns `ScreenResult`.
- Ignoring `result.text` after a mask decision.
- Using a global `PIIVault` across concurrent requests.
- Installing only `guardex-ai` and then expecting zero-config local ML mode.
- Claiming per-category local filtering without Ollama/LlamaGuard or another
  category-capable classifier.
- Calling grounding live without enabling `GUARDEX_GROUNDING_ENABLED` or the
  `grounding.enabled` setting in `guardex.yaml`.
- Using `GuardExCallbackHandler` when input PII masking must rewrite prompts.
- Treating `block_on_unsafe_* = False` as disabling injection, scope, routes, or
  PII block enforcement.
- Exposing `guardex-server --ui` on a public interface without authentication.
