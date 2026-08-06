# SDK Reference: GuardExClient

`guardex.GuardExClient` - Synchronous HTTP client for a self-hosted GuardEx server. Returns raw `dict` responses.

!!! tip "Prefer Guard for most use cases"
    The [`Guard`](guard.md) class provides the same functionality with typed result objects, streaming, and function wrapping. Use `GuardExClient` when you need raw dict responses or low-level control over your self-hosted server.

---

## Import

```python
from guardex import GuardExClient
```

---

## Constructor

```python
GuardExClient(
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 30.0,
    max_retries: int = 2,
    fail_open: bool = False,
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_key` | `str \| None` | `None` | Reserved for future use. Not required for the OSS server; leave as `None`. |
| `base_url` | `str \| None` | `GUARDEX_BASE_URL` env var, or `http://localhost:8001` | Self-hosted GuardEx server URL. |
| `timeout` | `float` | `30.0` | Request timeout in seconds. Applies to read phase; connect is capped at 5s. |
| `max_retries` | `int` | `2` | Number of retries on 429/5xx errors. |
| `fail_open` | `bool` | `False` | If `True`, return safe defaults on errors (except 401/403/422). |

---

## Context Manager

```python
with GuardExClient(base_url="http://localhost:8001") as client:
    result, request_id = client.screen("Hello", stage="input")
# HTTP client automatically closed
```

---

## Methods

### screen()

Combined PII detection + safety classification + scope in one call.

```python
client.screen(
    text: str,
    stage: str = "input",  # Any Gate value: "input", "output", "prompt", "tool_input", etc.
    pii_action: Literal["mask", "block", "none"] = "mask",
    categories: list[str] | None = None,
    pii_entities: list[str] | None = None,
    pii_threshold: float = 0.85,
    scope_topics: list[str] | None = None,
    scope_utterances: dict[str, list[str]] | None = None,
    scope_examples: list[str] | None = None,
    scope_width: str = "moderate",
    scope_threshold: float | None = None,
    scope_alpha: float = 0.0,
    cascade_mode: str = "safety",
    audit_log: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> tuple[dict, str | None]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text` | `str` | (required) | Text to screen |
| `stage` | `str` | `"input"` | Gate/stage name. Accepts all 8 gate values: `"input"`, `"output"`, `"prompt"`, `"stream"`, `"tool_input"`, `"tool_output"`, `"retrieval_query"`, `"retrieval_result"`. |
| `pii_action` | `"mask" \| "block" \| "none"` | `"mask"` | PII handling: mask values, block request, or skip PII detection |
| `categories` | `list[str] \| None` | `None` | Blocked category codes (uses dashboard default if `None`). Supports both category codes and semantic names. |
| `pii_entities` | `list[str] \| None` | `None` | PII entity types to detect (e.g., `["email", "phone", "ssn"]`) |
| `pii_threshold` | `float` | `0.7` | PII confidence threshold (0.0 - 1.0). Lower = more sensitive. |
| `scope_topics` | `list[str] \| None` | `None` | Allowed topic anchors for scope restriction. Scope filtering only active if provided. |
| `scope_utterances` | `dict[str, list[str]] \| None` | `None` | Per-topic example phrases (semantic-router pattern); more precise than topics alone |
| `scope_examples` | `list[str] \| None` | `None` | Example in-scope queries (improves scope accuracy) |
| `scope_width` | `str` | `"moderate"` | Scope strictness: `"narrow"`, `"moderate"`, or `"broad"` |
| `scope_threshold` | `float \| None` | `None` | Manual cosine similarity threshold override for scope (0.0-1.0) |
| `scope_alpha` | `float` | `0.0` | Hybrid matching weight (0.0 = dense only, 1.0 = sparse/BM25 only); only effective with `scope_utterances` |
| `cascade_mode` | `str` | `"safety"` | Cascade control: `"safety"` (full 4-layer checks) or `"speed"` (skip LlamaGuard for clear-cut cases, lower latency). |
| `audit_log` | `bool` | `False` | If `True`, include detailed audit log in server-side records for this request. |
| `extra_headers` | `dict[str, str] \| None` | `None` | Additional HTTP headers to forward to server (e.g., `X-GuardEx-Context`, `X-GuardEx-Policy-Hash`, `X-GuardEx-Session-Id`). |

**Returns:**

```python
(
    {
        "pii": {
            "has_pii": bool,
            "entities": [{"text": str, "label": str, "score": float, "start": int, "end": int}, ...],
            "masked_text": str | None,
        },
        "classify": {
            "safe": bool,
            "category": str | None,
            "categories": [str, ...],
            "confidence": float,
            "description": str | None,
        },
        "text": str,  # Processed text (masked if PII was found)
    },
    request_id: str | None  # X-GuardEx-Request-Id from response header (if present)
)
```

**Raises:**

- `PIIViolation` - When `pii_action='block'` and PII is detected.
- `GuardExAPIError` - On 4xx/5xx API errors.

**Example:**

```python
result, request_id = client.screen(
    "My SSN is 123-45-6789",
    stage="input",
    pii_action="mask",
    categories=["hate"],
)
print(result["text"])  # "My SSN is [SSN]"
print(request_id)      # "req_abc123xyz"
```

---

### screen_batch()

Screen multiple texts in a single round-trip (efficient for bulk operations).

```python
client.screen_batch(
    texts: list[str],
    stage: str = "input",  # accepts all 8 gate values
    pii_action: Literal["mask", "block", "none"] = "mask",
    categories: list[str] | None = None,
    pii_entities: list[str] | None = None,
    pii_threshold: float = 0.85,
    cascade_mode: str = "safety",
    extra_headers: dict[str, str] | None = None,
) -> list[dict]
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `texts` | `list[str]` | (required) | List of texts to screen. Each processed independently. |
| `stage` | `str` | `"input"` | Gate/stage name (accepts all 8 gate values). Applied to all texts in batch. |
| `pii_action` | `"mask" \| "block" \| "none"` | `"mask"` | Applied to all texts in batch. |
| `categories` | `list[str] \| None` | `None` | Applied to all texts in batch. |
| `pii_entities` | `list[str] \| None` | `None` | Applied to all texts in batch. |
| `pii_threshold` | `float` | `0.7` | Applied to all texts in batch. |
| `cascade_mode` | `str` | `"safety"` | Applied to all texts in batch. |
| `extra_headers` | `dict[str, str] \| None` | `None` | Additional HTTP headers to forward to server. |

**Returns:**

```python
[
    {
        "pii": {...},
        "classify": {...},
        "text": str,
    },
    ...  # One result per input text, in same order
]
```

**Fallback Behavior:**

If the server does not support the `/v1/screen/batch` endpoint (returns 404), the client automatically falls back to sequential `screen()` calls. This ensures compatibility with older GuardEx deployments.

```python
# Sent as single batch request to /v1/screen/batch if supported.
# If 404, falls back to 3 sequential screen() calls instead.
results = client.screen_batch([
    "Check this text",
    "And this one",
    "And one more",
])
# results[0], results[1], results[2] - same result structure as screen()
```

---

### classify()

Classify text for safety (no PII detection).

```python
client.classify(
    text: str,
    stage: str = "input",  # accepts all 8 gate values
    categories: list[str] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict
```

**Returns:**

```python
{
    "safe": bool,
    "category": str | None,
    "categories": [str, ...],
    "description": str | None,
    "_request_id": str | None,  # X-GuardEx-Request-Id (if present)
}
```

---

### pii_scan()

Scan text for PII without masking or blocking.

```python
client.pii_scan(
    text: str,
    entities: list[str] | None = None,
    threshold: float = 0.85,
    extra_headers: dict[str, str] | None = None,
) -> dict
```

**Returns:**

```python
{
    "has_pii": bool,
    "entities": [
        {"text": str, "label": str, "score": float, "start": int, "end": int},
        ...
    ],
}
```

---

### pii_mask()

Scan and mask PII in text.

```python
client.pii_mask(
    text: str,
    entities: list[str] | None = None,
    threshold: float = 0.85,
    extra_headers: dict[str, str] | None = None,
) -> dict
```

**Returns:**

```python
{
    "has_pii": bool,
    "entities": [...],
    "masked_text": str,
}
```

---

### get_effective_config()

Fetch the merged effective configuration (dashboard + code policy).

```python
client.get_effective_config() -> EffectiveConfig
```

**Returns:** [`EffectiveConfig`](policy.md#sdk-reference-effectiveconfig) object.

---

### health()

Check API server health (no authentication required).

```python
client.health() -> dict
```

**Returns:**

```python
{
    "status": "ok",
    "version": "0.1.0",
    "models": { ... }
}
```

---

### close()

Close the underlying HTTP client.

```python
client.close()
```

Called automatically when using the context manager.

---

## AsyncGuardExClient

Async version of `GuardExClient` with identical methods (except noted below).

```python
from guardex import AsyncGuardExClient

async with AsyncGuardExClient(base_url="http://localhost:8001") as client:
    result, request_id = await client.screen("Hello", stage="input")
    results = await client.screen_batch(["text1", "text2"])
    result = await client.classify("Hello", stage="input")
    result = await client.pii_scan("My email is test@test.com")
    result = await client.pii_mask("My email is test@test.com")
    health = await client.health()
```

Use `await client.aclose()` instead of `client.close()`.

!!! note "Async support"
    `get_effective_config()` is available on both the synchronous `GuardExClient` and the `AsyncGuardExClient` (use `await client.get_effective_config()`).

---

## Retry Behavior

The client automatically retries transient failures with exponential backoff and jitter.

| Error Type | Retried? | Backoff Strategy |
|-----------|----------|------------------|
| 429 (Rate Limit) | Yes | Respects `Retry-After` header if present; falls back to exponential backoff |
| 5xx (Server Error) | Yes | Exponential backoff: 0.5 * 2^n + random(0, 0.25) seconds |
| 401 (Auth Error) | No | Always raises `GuardExAPIError` immediately |
| 403 (Forbidden) | No | Always raises `GuardExAPIError` immediately |
| 422 (Validation) | No | Always raises `GuardExAPIError` immediately |
| Network Errors | Yes | Exponential backoff: 0.5 * 2^n + random(0, 0.25) seconds |

**Exponential Backoff Formula:**

```
backoff = (2 ^ attempt) * 0.5 + random(0, 0.25)
```

Where:
- `attempt` starts at 0 (first retry), increments for each subsequent attempt
- First retry waits 0.5–0.75 seconds
- Second retry waits 1.0–1.25 seconds
- Third retry waits 2.0–2.25 seconds (if `max_retries >= 3`)

**Retry-After Header:**

On HTTP 429 responses, the client respects the `Retry-After` header if present. The wait time is capped at 30 seconds to prevent excessive delays.

```python
# Server responds: 429 with Retry-After: 5
# Client waits 5 seconds before retrying (up to max_retries times)
```

---

## Fail-Open Behavior

When `fail_open=True` and an unrecoverable error occurs (after all retries exhausted), the client returns safe defaults instead of raising:

| Method | Fail-Open Return Value |
|--------|----------------------|
| `classify()` | `{"safe": True, "category": None, "categories": [], "_request_id": None}` |
| `pii_scan()` | `{"has_pii": False, "entities": []}` |
| `pii_mask()` | `{"has_pii": False, "entities": [], "masked_text": original_text}` |
| `screen()` | `({"pii": {"has_pii": False, "entities": []}, "classify": {"safe": True, "category": None, "categories": []}, "text": original_text}, None)` |
| `screen_batch()` | Falls back to sequential `screen()` calls instead of returning all-safe |

**Important:** 401, 403, and 422 errors always raise regardless of `fail_open`, as these indicate misconfiguration or invalid input.

---

## HTTP Headers

### Request Headers

| Header | Value | Notes |
|--------|-------|-------|
| `Authorization` | `Bearer {api_key}` | Optional; included only when `api_key` is set |
| `User-Agent` | `guardex-python/0.1.0` | SDK version identifier |
| `X-SDK-Version` | `0.1.0` | SDK version for compatibility tracking |

### Forward Custom Headers via extra_headers

The client supports forwarding additional headers to the server for context and policy tracking:

```python
result, request_id = client.screen(
    "Check this",
    extra_headers={
        "X-GuardEx-Context": "user_123:conversation_456",
        "X-GuardEx-Policy-Hash": "sha256:abc123...",
        "X-GuardEx-Session-Id": "sess_xyz789",
    }
)
```

**Common Headers:**

| Header | Purpose |
|--------|---------|
| `X-GuardEx-Context` | Custom context string for audit trail (forwarded to server) |
| `X-GuardEx-Policy-Hash` | Hash of applied policy for verification (forwarded to server) |
| `X-GuardEx-Session-Id` | Session identifier for grouping related requests (forwarded to server) |
| `X-GuardEx-Request-Id` | **Response only** - Server-generated request ID for correlation |

### Response Headers

The client reads the following response headers:

| Header | Usage |
|--------|-------|
| `X-GuardEx-Request-Id` | Returned as second element of `screen()` tuple for request correlation |
| `Retry-After` | Consulted on 429 responses to determine backoff wait time |

---

## Connection Pooling

The client uses HTTP/2 multiplexing with persistent connection pooling for efficiency:

- **Max connections:** 20
- **Keep-alive connections:** Up to 10 persistent connections
- **Keep-alive expiry:** 5 minutes
- **Protocol:** HTTP/2 with multiplexing enabled

This means multiple concurrent requests reuse the same connection, reducing latency and improving throughput for batch operations.

---

## Examples

### Basic Screening

```python
from guardex import GuardExClient

client = GuardExClient(base_url="http://localhost:8001")

# Screen user input for PII and safety
result, request_id = client.screen(
    "I'm looking for recipes with my credit card 4532-1234-5678-9012",
    stage="input",
    pii_action="mask",
)

print(result["text"])  # "I'm looking for recipes with my credit card [CREDIT_CARD]"
print(result["classify"]["safe"])  # True or False
print(request_id)  # "req_xyz123..." for logging
```

### Batch Processing

```python
# Screen 1000 user comments efficiently
comments = fetch_user_comments(limit=1000)

results = client.screen_batch(
    texts=comments,
    stage="input",
    pii_action="block",  # Reject any comment with PII
    categories=["hate", "violent_crimes"],
)

for i, result in enumerate(results):
    if not result["classify"]["safe"]:
        print(f"Comment {i} flagged: {result['classify']['category']}")
    if result["pii"]["has_pii"]:
        print(f"Comment {i} contains PII")
```

### Fail-Open for Resilience

```python
# Application continues even if GuardEx server is unavailable
client = GuardExClient(
    base_url="http://localhost:8001",
    fail_open=True,  # Return safe defaults on errors
)

result, _ = client.screen("Anything goes")  # Never raises; returns safe defaults on error
```

### Custom Retry Behavior

```python
# Reduce timeout and retry count for latency-sensitive applications
client = GuardExClient(
    base_url="http://localhost:8001",
    timeout=5,
    max_retries=1,  # Quick fail vs. retrying
)
```

### Custom Context for Audit Trail

```python
# Forward custom headers for server-side audit logging
result, request_id = client.screen(
    "user input",
    extra_headers={
        "X-GuardEx-Context": "user_abc123:session_def456",
        "X-GuardEx-Policy-Hash": "sha256:policy_hash_value",
    }
)
# Server receives and logs these headers for audit trail
```

---

## Error Handling

### GuardExAPIError

Raised on server errors (401, 403, 422, or other unrecoverable errors when `fail_open=False`).

```python
from guardex import GuardExAPIError

try:
    result, _ = client.screen("text")
except GuardExAPIError as e:
    print(f"API Error ({e.status_code}): {e.message}")
    print(f"Code: {e.code}")
    print(f"Type: {e.error_type}")
```

### PIIViolation

Raised by `screen()` when `pii_action='block'` and PII is detected.

```python
from guardex import PIIViolation

try:
    result, _ = client.screen(
        "My SSN is 123-45-6789",
        pii_action="block",
    )
except PIIViolation:
    print("Request blocked: PII detected")
```

---

## Version Compatibility

This documentation covers SDK v0.1.0.

- **API Endpoint Version:** `/v1/` (stable)
- **Batch Endpoint:** `/v1/screen/batch` (with 404 fallback to sequential)
- **Python:** 3.10+
- **Dependencies:** `httpx` (HTTP/2 support)

Check your server version with `client.health()` to ensure compatibility.
