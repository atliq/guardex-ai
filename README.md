<p align="center">
  <img src="https://raw.githubusercontent.com/atliq/guardex-ai/main/docs/assets/guardex.jpeg" alt="GuardEx" width="440">
</p>

# GuardEx: AI Guardrails

<p align="center">
  <a href="https://pypi.org/project/guardex-ai/"><img src="https://img.shields.io/pypi/v/guardex-ai?color=blue" alt="PyPI"></a>
  <a href="https://pypi.org/project/guardex-ai/"><img src="https://img.shields.io/pypi/pyversions/guardex-ai" alt="Python"></a>
  <a href="https://github.com/atliq/guardex-ai/actions"><img src="https://img.shields.io/github/actions/workflow/status/atliq/guardex-ai/ci.yml?label=CI" alt="CI"></a>
  <a href="https://github.com/atliq/guardex-ai?tab=Apache-2.0-1-ov-file"><img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License"></a>
</p>

GuardEx is a Python SDK that screens LLM inputs and outputs for unsafe content, PII, prompt injection, and optional grounding checks. Everything runs in-process, with no external API. It drops in front of any LLM call in about ten lines of code.

> Apache 2.0. Python 3.10+.

---

## Quick Start

```bash
pip install 'guardex-ai[local]'    # adds in-process ML engines
```

Or from source:

```bash
git clone https://github.com/atliq/guardex-ai.git
cd guardex-ai
pip install -e '.[local]'
```

```python
from guardex import Guard

guard = Guard()  # zero-config, models download on first use

result = guard.screen("How do I reset my password?", gate="input")

if result.blocked:
    print(f"Blocked: {result.classify.category} - {result.classify.description}")
else:
    if result.pii.has_pii:
        print(f"PII detected ({len(result.pii.entities)} entities), masked text:")
    print(result.text)
```

The first `Guard()` call downloads about 250 MB of models to `~/.cache/guardex/` and `~/.cache/huggingface/hub/`. Subsequent calls are warm.

Three Colab-ready [notebooks](docs/notebooks/) walk through the quickstart flow, PII detection, and content safety.

For full S1-S14 safety classification, run LlamaGuard through Ollama (see the note below). Without Ollama, GuardEx uses the ONNX fast gate. Grounding is opt-in and downloads an additional ~700 MB NLI model; see [Configuration](#configuration) to change either default.

> **Optional - deep safety classification via Ollama:**
> ```bash
> ollama pull llama-guard3:1b && ollama serve
> ```
> ```python
> guard = Guard(ollama_url="http://localhost:11434")
> ```
> If Ollama is not reachable at boot, GuardEx auto-downgrades the cascade
> to ONNX-only mode with a single WARNING log line - no failures.

---

## Async

```python
import asyncio
from guardex import Guard

async def main():
    async with Guard() as guard:
        result = await guard.ascreen("What's your refund policy?", gate="input")
        print(result.action, result.classify.category)

asyncio.run(main())
```

Every sync method has an async mirror (`ascreen`, `ascreen_batch`, `acheck_grounding`, `ascreen_grounded`, `astream`). In local mode they bridge to sync via `asyncio.to_thread` so you do not need a server.

---

## PII Vault (reversible tokenization)

When the LLM needs to echo personal data back to the user ("send a confirmation to ..."), masking is the wrong tool. Vault tokens map placeholders to original values:

```python
from guardex import Guard, PIIVault

guard = Guard()
vault = PIIVault()

text = "Send a confirmation to alice@example.com"
r = guard.screen(text, gate="input")

# vault_text mutates `vault` in place
vaulted_text, _ = vault.vault_text(text, r.pii)
# vaulted_text == "Send a confirmation to {{pii:email:a3f9b2...}}"

# Use vaulted_text with the LLM; the model never sees the email.
llm_reply = call_my_llm(vaulted_text)

# Restore before showing the user.
final_reply = vault.restore(llm_reply)
```

For streaming responses use `Guard.astream(..., vault=vault, restore_mode="buffered")` to restore tokens correctly across chunk boundaries. Streaming output gates do not mask PII by default; pass `mask_output_pii=True` when you need it.

---

## Policy

`GuardExPolicy` is the single configuration object. Common knobs:

```python
from guardex import Guard, GuardExPolicy, TopicScope

policy = GuardExPolicy(
    blocked_categories=["S1", "S3", "S4", "S9", "S11"],  # default-blocked set
    block_on_unsafe_input=True,
    block_on_unsafe_output=True,
    pii_enabled=True,
    pii_action="mask",                                    # or "block"
    pii_threshold=0.85,
    topic_scope=TopicScope(
        topics=["customer support", "product help"],
        scope_width="moderate",
    ),
    audit_logging=True,
)
guard = Guard(policy=policy)
```

Load a policy from YAML:

```python
policy = GuardExPolicy.from_yaml("guardex_policy.yaml")
```

`from_yaml` reads a flat policy file (`pii_action`, `blocked_categories`,
`topic_scope`, `safety_routes`, …). This is a **different file** from
`guardex.yaml`, which configures the local ML engine (model repos, cache
dir) and is auto-loaded from your project root. `guardex.yaml.example` is
its template. See [configuration.md](docs/guides/configuration.md) for both.

Need domain-specific PII entities (medical record numbers, employee IDs)?
`GuardExPolicy(pii_custom_regex={...})` adds your own label → regex rules,
in local and server mode. See [PII Detection: Custom Regex Patterns](docs/guides/pii-detection.md#custom-regex-patterns).

---

## Features

| Feature | Description | Latency (warm) |
|---|---|---|
| Safety classification | Binary toxicity gate (ONNX, always on); full S1-S14 categories via LlamaGuard 3 (optional Ollama) | ~20 ms / ~500 ms |
| PII detection and masking | 31 entity types (GLiNER) across 5 categories | ~15 ms |
| Prompt injection defense | Client-side regex (31 patterns) | ~1 ms |
| Hallucination detection | NLI + embedding hybrid with claim decomposition (opt-in) | ~50-200 ms |
| Topic scope restriction | Embedding-based topic filtering | ~5 ms |
| Streaming support | Buffered + stream-safe vault restoration | per-chunk |
| Multi-turn awareness | `ConversationGuard` detects escalation across turns | per-turn |
| Custom safety routes | User-defined blocklist categories via example utterances | ~5 ms |

By default, the ONNX fast gate makes a binary safe/toxic decision: it reliably catches toxic language but not neutrally-phrased harmful requests (e.g. "how do I make a weapon"). Per-category S1-S14 verdicts and coverage of those requests need the optional LlamaGuard layer via Ollama (see the note under Quick Start). Latencies measured on an Apple M2; cold-start adds the model download (~250 MB without grounding, ~950 MB with grounding enabled).

---

## Integration Examples

### Gemini

```bash
pip install google-genai
```

```python
from google import genai
from guardex import Guard, GuardExViolation

guard = Guard()
client = genai.Client()  # reads GEMINI_API_KEY

user_msg = "How do I reset my password?"

try:
    input_text = guard.screen_or_raise(user_msg, gate="input")
except GuardExViolation as e:
    print(f"Refused at input gate: {e.category}")
    raise

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=input_text,
)

try:
    safe_output = guard.screen_or_raise(response.text, gate="output")
except GuardExViolation as e:
    print(f"Refused at output gate: {e.category}")
    raise

print(safe_output)
```

The same two-gate pattern works with any provider - swap the model call and keep the guards.

### RAG with hallucination detection

Grounding is opt-in - set `GUARDEX_GROUNDING_ENABLED=1` or pass `grounding_mode=` to `screen_grounded`.

```python
from guardex import Guard

guard = Guard()

screen_result, grounding = guard.screen_grounded(
    response_text=llm_response,
    sources=retrieved_chunks,
    gate="output",
    grounding_mode="accuracy",
)

if screen_result.blocked:
    return "I can't help with that."
if grounding.hallucinated:
    print(f"Faithfulness {grounding.faithfulness_score:.0%}; flagging for human review.")
    for s in grounding.hallucinated_sentences:
        print(f"  - {s.sentence}")
```

### Conversation guard (escalation detection)

```python
from guardex import Guard
from guardex.conversation import ConversationGuard

guard = Guard()
cg = ConversationGuard(guard, window=6)

result = cg.screen_turn("user", user_message)
if result.blocked:
    return guard.policy.refusal_messages.get(
        result.classify.category,
        "I can't help with that.",
    )

llm_reply = call_llm(user_message)
cg.screen_turn("assistant", llm_reply)
```

---

## Server mode

`Guard()` with no `api_key` or `base_url` runs the models in-process (local
mode). Pass either one and the SDK instead talks HTTP to a GuardEx server:

```python
guard = Guard(base_url="http://your-host:8001")   # your self-hosted server
```

A reference server ships with the SDK - the same local pipeline behind
FastAPI:

```bash
pip install 'guardex-ai[local,server]'
guardex-server --host 0.0.0.0 --port 8001
```

Models load at startup; the server accepts traffic once the pipeline is
warm. It has no built-in auth: run it on a private network or front it with
your own auth proxy. Pass `api_key=` only if your deployment puts auth in
front of the endpoint; there is no GuardEx-hosted service.

---

## Local UI

The reference server can also serve a browser UI on the same port:

```bash
pip install 'guardex-ai[local,ui]'
guardex-server --ui          # http://127.0.0.1:8001
```

- **Playground** — screen text and see the verdict, detected entities, and
  per-gate timings
- **Logs** — the last 1000 screening calls, in memory, cleared on restart
- **Config** — every policy knob, applied live, saveable to
  `guardex.policy.yaml`

No Node required: the wheel ships prebuilt assets. There is no
authentication, so `--ui` refuses a non-loopback `--host` unless you pass
`--ui-unsafe-bind`. See [docs/guides/local-ui.md](docs/guides/local-ui.md).

---

## Architecture

```
Guard()
   |
   |  in-process
   v
LocalRunner pipeline
   |
   +-- Input validation (length / repetition / character flood)
   +-- Keyword gate (zero-latency hard blocks for passive ideation)
   +-- Text normalization (homoglyph + invisible-char removal)
   +-- Safety classifier
   |     +-- Layer 0: ONNX fast gate
   |     +-- Layer 1: LlamaGuard 3 via Ollama (optional, ~500 ms)
   +-- PII detection (GLiNER, 31 entity types)
   +-- Topic scope (sentence-transformers embedding)
   +-- Custom safety routes (user-defined blocklist categories)
   +-- Grounding / hallucination (DeBERTa NLI + embedding hybrid, opt-in)
   +-- Prompt injection (client-side regex, 31 patterns)
```

---

## Safety Categories

GuardEx uses the canonical LlamaGuard 3 / MLCommons taxonomy (`S1`-`S14`)
verbatim, plus a GuardEx-specific `S0` emitted by the input validator. The
default-blocked set is:

| Code | Category |
|---|---|
| S1 | Violent Crimes |
| S3 | Sex-Related Crimes |
| S4 | Child Sexual Exploitation |
| S9 | Indiscriminate Weapons |
| S11 | Suicide & Self-Harm |

See [safety-categories.md](docs/guides/safety-categories.md) for the full
S0-S14 table and how to change which categories block.

---

## Configuration

Override defaults via environment variables (`GUARDEX_*`) or `guardex.yaml` in your project root. See `guardex.yaml.example` for the local engine settings it honors. Common overrides:

```bash
export GUARDEX_CASCADE_MODE=speed           # skip LlamaGuard, use ONNX only
export GUARDEX_GROUNDING_ENABLED=1          # enable NLI grounding (~700 MB)
export GUARDEX_CACHE_DIR=/data/guardex      # custom model cache
export GUARDEX_ONNX_USE_GPU=1               # CUDA for ONNX classifier
```

---

## What this SDK does not do

- Image, audio, or video moderation
- Role / permission models (no built-in RBAC)
- Cross-lingual safety classification (English-only patterns)
- A managed cloud service (run in-process or self-host the reference server)
- Real-time policy hot-reload from a remote store (use YAML + restart)

---

## Contributing

Bug reports, feature requests, and pull requests are welcome. Before opening
a PR, please read [CONTRIBUTING.md](CONTRIBUTING.md) for the development
setup, branch strategy, and code-style expectations. For security issues,
follow the responsible-disclosure process in [SECURITY.md](SECURITY.md).
Do not open a public issue for security vulnerabilities.

## License

Apache 2.0. See [LICENSE](LICENSE) for details.
