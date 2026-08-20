# PII and Streaming

Read this when the task needs reversible PII tokenization, custom PII labels, or
streaming output screening. For ordinary masking or blocking, `GuardExPolicy`
with `pii_action="mask"` or `"block"` is enough.

## Built-In PII

GuardEx ships 31 built-in PII entity labels, exposed as
`DEFAULT_PII_ENTITIES` / `ALL_PII_ENTITIES`. Defaults:

- `pii_enabled=True`
- `pii_action="mask"`
- `pii_threshold=0.85`
- a small allow-list for conversational tokens like "hi" and "thanks"

Use `guard.pii_scan(text)` for detection only and `guard.pii_mask(text)` for
masking only. Use `guard.screen(..., gate=...)` when the normal safety,
injection, PII, scope, and route cascade should run together.

## Reversible Vault

Masking replaces PII with generic placeholders and cannot restore the original
value. Use `PIIVault` when the LLM must work with a placeholder and the final
answer must restore the user's real value.

```python
from guardex import Guard, PIIVault

guard = Guard()
vault = PIIVault()  # create one vault per request/session, not a global vault

user_text = "Send a confirmation to alice@example.com"
screened = guard.screen(user_text, gate="input")

vaulted_text, vault = vault.vault_text(user_text, screened.pii)

llm_reply = call_llm(
    system=f"You are support. {PIIVault.SYSTEM_PROMPT_HINT}",
    user=vaulted_text,
)

safe_reply = guard.screen_or_raise(llm_reply, gate="output")
final_reply = vault.restore(safe_reply)
```

`vault_text()` returns `(vaulted_text, vault)` and mutates the vault in place.
Always unpack the tuple. Unknown vault tokens are left unchanged on restore.
`PIIVault` is not thread-safe; create one per request, conversation, or other
isolation boundary.

## Custom PII

Use policy fields instead of post-processing `Guard()` output:

```python
from guardex import Guard, GuardExPolicy

policy = GuardExPolicy(
    pii_custom_regex={"employee_id": r"EMP-\d{6}"},
    pii_deny_list=["internal-code-red"],
    pii_allow_list=["Acme Support"],
    pii_custom_context_keywords={"employee_id": ["employee", "staff id"]},
)
guard = Guard(policy=policy)
```

Server mode validates custom regex patterns and limits them to 32 patterns of
512 characters each.

## Streaming

Prefer `guard.stream()` / `guard.astream()` over constructing `StreamGuard`
directly. The guard buffers chunks and screens on content boundaries or once
`flush_every` characters are reached.

```python
for chunk in guard.stream(llm_chunks(), gate="output", flush_every=256):
    send_to_client(chunk)
```

Output gates do not mask PII by default because model-generated names may not
be real user data. Pass `mask_output_pii=True` when the stream itself must mask
detected output PII:

```python
for chunk in guard.stream(
    llm_chunks(),
    gate="output",
    mask_output_pii=True,
):
    send_to_client(chunk)
```

When streaming an LLM response that may contain `PIIVault` tokens, pass the
vault and choose a restore mode:

```python
for chunk in guard.stream(
    llm_chunks(),
    gate="output",
    vault=vault,
    restore_mode="stream-safe",
):
    send_to_client(chunk)
```

- `stream-safe`: keeps live streaming and holds back only a possible partial
  `{{pii:` token until it is complete.
- `buffered`: emits nothing until the stream ends, then restores and emits the
  full text in one piece.
- `off`: default when no vault is provided.

Streaming enforces injection, topic scope, safety routes, and the classifier
verdict according to the same observe-only rules as `screen_or_raise`. A pattern
split across flush boundaries can be evaluated in pieces, so screen the final
full text too when exact whole-response enforcement is required.
