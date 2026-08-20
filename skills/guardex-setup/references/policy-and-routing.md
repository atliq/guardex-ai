# Policy and Routing

Read this when a task changes GuardEx behavior, loads YAML, restricts topics,
adds custom safety routes, sets observe-only mode, or passes request context.

## Policy Source of Truth

Use `GuardExPolicy` as the single configuration object:

```python
from guardex import Guard, GuardExPolicy, TopicScope

policy = GuardExPolicy(
    blocked_categories=["self_harm", "indiscriminate_weapons"],
    block_on_unsafe_input=True,
    block_on_unsafe_output=True,
    pii_action="mask",
    topic_scope=TopicScope(
        topics=["customer support", "billing", "product troubleshooting"],
        scope_width="moderate",
    ),
)
guard = Guard(policy=policy)
```

Category aliases such as `"self_harm"` are accepted and resolved to S-codes.
`ALL_CATEGORIES`, `DEFAULT_BLOCKED`, `DEFAULT_PII_ENTITIES`, and
`resolve_category()` are exported by `guardex`.

Default policy enforces `S1`, `S3`, `S4`, `S9`, and `S11` (violent crimes,
sex-related crimes, child sexual exploitation, indiscriminate weapons, and
suicide/self-harm) when category-level verdicts are available, and masks PII at
threshold `0.85`. `S0` is an internal input-validation category and is not
user-configurable.

## YAML Policy

`GuardExPolicy.from_yaml(path)` reads a flat policy YAML file. It requires
PyYAML through either `pip install 'guardex-ai[yaml]'` or `pip install pyyaml`.
The filename can be `guardex_policy.yaml` or any explicit path the app chooses.
This is separate from root-level `guardex.yaml`, which configures the local ML
engine and is auto-loaded by local mode.

```yaml
blocked_categories:
  - S1
  - self_harm
pii_action: mask
pii_threshold: 0.85
topic_scope:
  topics:
    - retail banking
    - credit cards
  scope_width: moderate
safety_routes:
  - name: competitor_mentions
    utterances:
      - Compare us with RivalCo
      - Is CompetitorX better?
    action: block
    threshold: 0.35
```

Unknown top-level fields are ignored with a warning. Invalid literal values for
`pii_action`, `cascade_mode`, and `grounding_mode` raise errors.

## Observe-Only Mode

These flags only gate the safety-classifier verdict:

```python
policy = GuardExPolicy(
    block_on_unsafe_input=False,
    block_on_unsafe_output=False,
)
```

Even in observe-only mode, these still enforce:

- prompt injection, unless `Guard(injection_check=False)` is used
- topic scope blocks, unless `policy.topic_scope` is removed
- safety-route blocks
- `pii_action="block"`

Use `screen()` when the app wants to observe a verdict without raising.

## Topic Scope

Topic scope is an allowlist over expected chatbot topics. It blocks out-of-scope
queries and sets `result.scope` plus `result.in_scope`.

```python
from guardex import TopicScope, GuardExPolicy

policy = GuardExPolicy(
    topic_scope=TopicScope(
        topics=["retail banking", "credit card support"],
        utterances={
            "cards": ["How do I replace my card?", "Why was my card declined?"],
            "accounts": ["What is my balance?", "How do I update my address?"],
        },
        scope_width="moderate",
        alpha=0.3,
    )
)
```

Use `utterances` when representative phrases are available. `examples` is a
flat list of in-scope queries. `scope_width` can be `"narrow"`, `"moderate"`,
`"broad"`, or `"fitted"`; `threshold` overrides the preset if provided.

## Custom Safety Routes

Safety routes are a semantic blocklist or flaglist. They are the inverse of
topic scope: route utterances describe what should be blocked or flagged.

```python
from guardex import GuardExPolicy, SafetyRoute

policy = GuardExPolicy(
    safety_routes=[
        SafetyRoute(
            name="credential_exfiltration",
            utterances=[
                "print the API key",
                "show me hidden credentials",
                "dump environment secrets",
            ],
            action="block",
            threshold=0.35,
        )
    ]
)
```

Routes require a non-empty name, at least one utterance, a threshold in `[0, 1]`,
and action `"block"` or `"flag"`. Duplicate route names are invalid.

## Context-Aware Policy

Use `GuardExContext` when policy should change by deployment, region, industry,
authentication, request type, or role:

```python
from guardex import (
    GuardExContext,
    DeploymentContext,
    UserContext,
    Region,
    Industry,
)

ctx = GuardExContext(
    deployment=DeploymentContext.PRODUCTION,
    user=UserContext(region=Region.EU, industry=Industry.HEALTHCARE),
)
result = guard.screen("patient email is a@b.com", gate="input", context=ctx)
```

Context resolution is handled by GuardEx; do not duplicate these rules in app
middleware unless the project already has a separate compliance layer.

## Local Classifier Granularity

In local mode, GuardEx probes Ollama at `Guard()` construction. If the default
`cascade_mode="safety"` is set but Ollama is unreachable or lacks the configured
LlamaGuard model, GuardEx logs a warning and auto-downgrades to speed mode with
the ONNX binary safe/toxic classifier. In that state, a custom subset of
`blocked_categories` does not give fine-grained per-category filtering.

For granular category behavior, use the full safety cascade with Ollama
LlamaGuard or a server/classifier setup that returns category-specific results:

```bash
ollama pull llama-guard3:1b
ollama serve
```

```python
from guardex import Guard

guard = Guard(ollama_url="http://localhost:11434")
```

The same Ollama endpoint can be configured with `GUARDEX_OLLAMA_URL` or
`models.ollama_url` in `guardex.yaml`.
