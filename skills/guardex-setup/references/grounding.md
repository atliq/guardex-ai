# Grounding

Read this when the task asks for hallucination checks, answer grounding,
faithfulness to retrieved sources, or RAG answer validation.

Grounding is opt-in. In local mode it is disabled by default because the NLI
model is large; passing `mode="accuracy"` does not enable the provider by
itself. Enable it before relying on `check_grounding`.

```bash
set GUARDEX_GROUNDING_ENABLED=1
```

Or in root-level `guardex.yaml`:

```yaml
grounding:
  enabled: true
  mode: accuracy
```

Then GuardEx compares a model response against source strings and returns a
`GroundingResult` with overall and per-sentence details.

## Check Grounding Only

```python
grounding = guard.check_grounding(
    response_text=answer,
    sources=retrieved_chunks,
    mode="accuracy",
)

if not grounding.grounded:
    unsupported = grounding.hallucinated_sentences
```

Modes:

- `speed`: embedding similarity
- `accuracy`: NLI cross-encoder / hybrid scoring
- `None`: use policy or server default after grounding is enabled

`threshold` can override the default per-sentence grounded score threshold.

## Screen and Ground an Output

Use `screen_grounded` when the output should be safety/PII screened and then
grounded against sources:

```python
screen_result, grounding = guard.screen_grounded(
    response_text=answer,
    sources=retrieved_chunks,
    gate="output",
    grounding_mode="accuracy",
)

if screen_result.blocked:
    return refusal_for(screen_result)
if not grounding.grounded:
    return ask_model_to_revise(answer, grounding.hallucinated_sentences)
```

Async equivalents are `acheck_grounding` and `ascreen_grounded`.

## Policy Defaults

Grounding defaults can live on the policy:

```python
from guardex import GuardExPolicy

policy = GuardExPolicy(
    grounding_mode="accuracy",
    grounding_threshold=0.75,
)
```

Grounding exposes both `grounded` and `hallucinated` booleans; `hallucinated` is
the inverse of `grounded`.

Grounding uses the `/v1/grounding` endpoint in server mode and the local
grounding provider in local mode. In local mode, if grounding is not enabled, the
provider is skipped and only a log line is emitted. Empty sources should be
handled by the host app as a retrieval failure or a skip decision rather than
treated as evidence.
