---
name: guardex-setup
description: Install or integrate the guardex-ai Python SDK into an LLM application for local or self-hosted screening of prompts, outputs, tools, retrieval, PII, prompt injection, safety categories, topic scope, custom safety routes, grounding, streaming, or LangChain. Use for GuardEx setup/configuration tasks and for generic Python AI guardrail requests when guardex-ai is an acceptable dependency; do not use for unrelated moderation providers or non-Python apps unless the user asks to port concepts.
---

# GuardEx Setup

GuardEx is a Python SDK for screening LLM traffic in-process by default. One
`Guard` can screen text at eight gates and returns a `ScreenResult` with safety,
PII, scope, route, diagnostics, and processed text.

Zero-config `Guard()` already has a production baseline: it screens for unsafe
content, masks PII at confidence `0.85`, and enforces the default high-severity
category policy (`S1`, `S3`, `S4`, `S9`, `S11`) when the classifier returns
category-level verdicts. In local mode without Ollama/LlamaGuard, GuardEx
auto-downgrades to the ONNX binary safe/toxic classifier, so per-category
filtering is unavailable even though unsafe/toxic content is still screened.
Override policy through `GuardExPolicy`, not by adding ad hoc regex/category
checks around `Guard()`.

## Install

Choose the smallest extra that satisfies the integration. For a new local
integration, prefer `[local]` because zero-config `Guard()` needs the in-process
ML runtimes:

```bash
pip install 'guardex-ai[local]'
```

Use narrower extras only when the project truly needs a smaller dependency set:

```bash
pip install guardex-ai              # core SDK only; use with server mode or injection-only code
pip install 'guardex-ai[pii]'       # GLiNER PII provider
pip install 'guardex-ai[safety]'    # ONNX safety classifier
pip install 'guardex-ai[scope]'     # topic-scope embeddings
pip install 'guardex-ai[yaml]'      # GuardExPolicy.from_yaml support
pip install 'guardex-ai[langchain]' # GuardedLLM and callback handler
```

Local mode downloads models on first use to the GuardEx and Hugging Face cache
directories. If this is unacceptable for the host environment, use the
self-hosted server path in `references/server-and-ui.md`.

For full local LlamaGuard category classification, run Ollama with the configured
model (`ollama pull llama-guard3:1b`, then `ollama serve`) and either use the
default `http://localhost:11434`, set `GUARDEX_OLLAMA_URL`, configure
`models.ollama_url` in `guardex.yaml`, or pass
`Guard(ollama_url="http://localhost:11434")`.

## Default Wiring

For a normal chat or completion wrapper, screen user input before the LLM call
and screen the model output before returning it. Use `screen_or_raise` when the
host app already has an exception/refusal path. Use `screen` when the app needs
to inspect `result.blocked`, `result.text`, `result.classify`, `result.pii`,
`result.scope`, `result.safety_route`, or `result.diagnostics`.

```python
from guardex import Guard, GuardExViolation

guard = Guard()

def call_llm_safely(user_text: str, llm_call) -> str:
    try:
        safe_input = guard.screen_or_raise(user_text, gate="input")
        raw_output = llm_call(safe_input)
        return guard.screen_or_raise(raw_output, gate="output")
    except GuardExViolation as exc:
        return f"Request blocked by GuardEx at {exc.stage}: {exc.category}"
```

Async apps should use `ascreen`, `ascreen_or_raise`, `ascreen_batch`,
`acheck_grounding`, `ascreen_grounded`, and `astream`; local async methods
bridge to the local runner internally.

## Gate Choice

Do not screen everything as `input` or `output`. Match the gate to where the
text enters or leaves the LLM workflow:

- `input`: raw user text
- `prompt`: assembled system, context, and user prompt
- `stream`: streaming chunks, normally via `guard.stream` or `guard.astream`
- `output`: full LLM response
- `tool_input` and `tool_output`: function/tool call arguments and return text
- `retrieval_query` and `retrieval_result`: RAG query text and retrieved chunks

`Guard.wrap(fn, gate="tool_input")` screens string args and, by default, screens
the return value at the matching output gate.

## Policy

Configure behavior with `GuardExPolicy`; do not add parallel regex or category
logic around GuardEx unless the user has a project-specific reason.

```python
from guardex import Guard, GuardExPolicy

policy = GuardExPolicy(
    blocked_categories=["S1", "S3", "S4", "S9", "S11"],
    pii_enabled=True,
    pii_action="mask",      # "mask" or "block"
    pii_threshold=0.85,
    fail_open=False,
)
guard = Guard(policy=policy)
```

Keep GuardEx's two YAML/config files distinct:

- `guardex_policy.yaml` or any path passed to `GuardExPolicy.from_yaml(...)`:
  application policy knobs such as blocked categories, PII action/threshold,
  topic scope, safety routes, and grounding defaults.
- `guardex.yaml` in the project root: local ML engine settings such as model
  repositories, cache directory, Ollama, and provider toggles; it is auto-loaded
  by local mode and is not the policy file.

Important enforcement detail: `block_on_unsafe_input` and
`block_on_unsafe_output` only control the safety-classifier verdict. Prompt
injection, topic scope blocks, safety-route blocks, and `pii_action="block"`
still enforce.

## Read More When Needed

- Policy YAML, topic scope, custom safety routes, context-aware policy, category
  aliases, and observe-only mode: `references/policy-and-routing.md`
- PII vault tokenization, custom PII rules, and streaming response screening:
  `references/pii-and-streaming.md`
- Self-hosted HTTP server, local UI, and deployment split between local and
  server mode: `references/server-and-ui.md`
- LangChain, tool wrappers, RAG gates, callbacks, and multi-turn conversations:
  `references/framework-patterns.md`
- Grounding and hallucination checks: `references/grounding.md`
- Verification checklist and tests to run after an integration: `references/validation.md`

Keep integrations surgical: place GuardEx at the existing request/response,
tool, stream, or retrieval boundary; preserve the application's current refusal,
logging, dependency, and deployment conventions.
