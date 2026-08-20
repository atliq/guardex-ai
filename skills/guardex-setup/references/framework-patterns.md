# Framework Patterns

Read this when wiring GuardEx into an actual app framework, LangChain, tools,
RAG, or multi-turn chat. Prefer the host application's existing error handling
and logging style.

## Plain Python Boundary

Put GuardEx at the boundary where text crosses into or out of the LLM:

```python
safe_input = guard.screen_or_raise(user_text, gate="input")
raw_output = llm_call(safe_input)
safe_output = guard.screen_or_raise(raw_output, gate="output")
```

If the app needs custom refusals, call `screen()` and branch on the structured
result:

```python
result = guard.screen(user_text, gate="input")
if result.blocked:
    log_block(result.gate, result.classify.category, result.request_id)
    return refusal_for(result)

reply = llm_call(result.text)
```

Use `result.text`, not the original input, after a successful input screen
because PII may have been masked.

## Tools and Functions

Use tool gates for function-call arguments and return values:

```python
safe_tool = guard.wrap(search_docs, gate="tool_input")
tool_result = safe_tool(user_query)
```

`wrap()` screens all string positional arguments, then screens a string return
value at the corresponding output gate (`tool_output` for `tool_input`,
`retrieval_result` for `retrieval_query`, and `output` for `input`/`prompt`).

For structured tool payloads, screen the string fields explicitly instead of
serializing the whole object unless that is how the tool actually consumes it.

## RAG

Use retrieval gates around the search operation:

```python
safe_query = guard.screen_or_raise(user_query, gate="retrieval_query")
docs = retriever.search(safe_query)
safe_docs = [
    guard.screen_or_raise(doc.page_content, gate="retrieval_result")
    for doc in docs
]
```

Then use `gate="prompt"` for the assembled prompt if the app creates a single
large prompt from user text, retrieved context, and system instructions.

## LangChain

Install:

```bash
pip install 'guardex-ai[langchain]'
```

Use `GuardedLLM` when GuardEx must be able to rewrite masked input before the
LLM call:

```python
from guardex import GuardedLLM, GuardExPolicy

guarded = GuardedLLM(inner_llm, policy=GuardExPolicy(pii_action="mask"))
response = guarded.invoke(messages)
```

Use `GuardExCallbackHandler` when the chain is already built and callbacks are
the natural extension point:

```python
from guardex import GuardExCallbackHandler

handler = GuardExCallbackHandler(policy=policy)
chain.invoke(inputs, config={"callbacks": [handler]})
```

Callback limitation: LangChain callback prompts are already constructed, so
input `pii_action="mask"` can log but cannot rewrite the prompt. Use
`GuardedLLM` for input masking. Output masking works in callbacks.

## Multi-Turn Conversations

Use `ConversationGuard` when a harmful request may emerge across turns:

```python
from guardex import ConversationGuard, Guard

guard = Guard()
conversation_guard = ConversationGuard(guard, window=6)

result = conversation_guard.screen_turn("user", user_message)
if result.blocked:
    return "I can't help with that."

reply = llm_call(user_message)
conversation_guard.screen_turn("assistant", reply)
```

It prepends a sliding history window before screening the new turn, stores only
unblocked turns, and trims the constructed payload to `max_payload_chars`.

## Async Apps

Use the async methods directly:

```python
async with Guard() as guard:
    safe_input = await guard.ascreen_or_raise(user_text, gate="input")
    raw_output = await async_llm_call(safe_input)
    safe_output = await guard.ascreen_or_raise(raw_output, gate="output")
```

Do not add your own thread-pool wrapper around local `Guard.ascreen`; GuardEx
already bridges local sync work with `asyncio.to_thread`.
