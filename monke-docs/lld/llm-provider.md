# LLD: llm_provider

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: tools/
> HLD Reference: S3 C1.2.1
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Single gateway for all LLM calls. Wraps LiteLLM's `acompletion()` for unified async chat completion. All providers (AWS Bedrock, Google Gemini, LM Studio / OpenAI-compatible locals) are accessed through this module only. No other module in the codebase imports LiteLLM or calls provider SDKs directly.

Replaces legacy modules: `Tools/liteLM.py` (model factory functions, `ChatLiteLLM`/`LiteLLMModel` wrappers) and the inline `litellm.completion()` calls in `Core/mcPro/anyMCP.py`. Those modules couple provider selection to framework-specific model objects (`ChatLiteLLM`, `LiteLLMModel`) and use synchronous calls. This module eliminates that coupling -- callers pass `LlmConfig` and get back `LlmResponse`, with no knowledge of LiteLLM internals.

## Public API

### Response Model

| Class | Fields | Notes |
|-------|--------|-------|
| `LlmResponse` | `content: str \| None`, `tool_calls: list[ToolCall] \| None`, `usage: TokenUsage`, `model: str`, `latency_ms: float` | Returned by `acomplete()`. `content` is the assistant's text response (None when only tool calls are returned). `tool_calls` is present when the LLM requests tool execution. `usage` is token counts from the provider. `model` is the resolved model identifier (as returned by LiteLLM, may differ from the input slug for aliased models). `latency_ms` is wall-clock time of the LiteLLM call. |

### Functions

| Function | Signature | Notes |
|----------|-----------|-------|
| `acomplete` | `async def acomplete(config: LlmConfig, messages: list[ConversationMessage], tools: list[McpToolDefinition] \| None = None, config_override: LlmConfig \| None = None) -> LlmResponse` | Primary entry point. Converts domain types to LiteLLM wire format, calls `litellm.acompletion()`, converts the response back to domain types. Raises `ProviderError` on LLM failures, `ConfigurationError` on invalid config. When `config_override` is provided (OQ-010), its non-None fields take precedence over the base `config` -- enabling per-request model/temperature/token overrides without constructing a full new LlmConfig. |
| `validate_config` | `def validate_config(config: LlmConfig) -> None` | Validates that `config.model_slug` is non-empty and structurally valid (contains a provider prefix or `api_base` is set for local models). Raises `ConfigurationError` on failure. Called internally by `acomplete` before every call; also available for eager validation at startup. |

### Tool Definition Conversion

`acomplete` converts `McpToolDefinition` objects to the LiteLLM/OpenAI function-calling format internally:

```
McpToolDefinition {                    LiteLLM tool dict {
  name: str           -->                "type": "function",
  description: str    -->                "function": {
  input_schema: dict  -->                  "name": ...,
}                                          "description": ...,
                                           "parameters": ...
                                         }
                                       }
```

`tags` and `category` from `McpToolDefinition` are stripped -- they are SynaptiCore metadata, not part of the LLM tool-calling protocol.

### Message Conversion

`acomplete` converts `ConversationMessage` objects to LiteLLM message dicts:

| `ConversationMessage` field | LiteLLM message key | Notes |
|-----------------------------|---------------------|-------|
| `role` (ConversationRole enum) | `"role"` (str) | Lowercased enum value: `"user"`, `"assistant"`, `"system"`, `"tool"` |
| `content` | `"content"` | Passed through. `None` is valid for assistant messages with tool calls. |
| `tool_calls` | `"tool_calls"` | Converted to list of `{"id": ..., "type": "function", "function": {"name": ..., "arguments": json.dumps(...)}}`. `ToolCall.arguments` (parsed dict) is JSON-encoded at this boundary. |
| `tool_call_id` | `"tool_call_id"` | Present on `TOOL` role messages. Passed through. |
| `name` | `"name"` | Optional. Passed through when present. |

### Response Conversion

LiteLLM `ModelResponse` is converted back to domain types:

| LiteLLM response field | `LlmResponse` field | Notes |
|------------------------|---------------------|-------|
| `choices[0].message.content` | `content` | `None` if absent. |
| `choices[0].message.tool_calls` | `tool_calls` | Each converted to `ToolCall(id=..., name=..., arguments=json.loads(...))`. `arguments` is parsed from JSON string back to dict at this boundary. |
| `usage.prompt_tokens` | `usage.prompt_tokens` | |
| `usage.completion_tokens` | `usage.completion_tokens` | |
| `usage.total_tokens` | `usage.total_tokens` | |
| `model` | `model` | The resolved model identifier from the response. |
| *(computed)* | `latency_ms` | Wall-clock `time.perf_counter()` delta around the `acompletion()` call, converted to milliseconds. |

## Internal Design

### Key Design Decisions

1. **`litellm.acompletion()` only -- no synchronous path.** All callers are async (agents, protocol servers). The legacy `litellm.completion()` call in `anyMCP.py` is replaced with `acompletion()`. There is no sync wrapper; callers must `await`.

2. **No framework-specific model objects.** The legacy `liteLM.py` returns `ChatLiteLLM` (LangChain) and `LiteLLMModel` (smolagents) objects. This module returns plain `LlmResponse` Pydantic models. Framework integration (if needed) happens upstream -- agents convert `LlmResponse` to whatever their framework expects.

3. **Stateless function, not a class.** `acomplete` is a module-level async function, not a method on an instance. There is no connection pool, session, or client object to manage. LiteLLM handles connection reuse internally. This makes the module trivially testable (mock `litellm.acompletion`) and avoids lifecycle complexity.

4. **LiteLLM callbacks for structured logging.** A custom LiteLLM callback (`SynaptiCoreLoggingCallback`) is registered at module import time. It logs: model slug, provider, prompt tokens, completion tokens, total tokens, latency, and success/failure status. This replaces the `print()` statements scattered through `anyMCP.py`. The callback uses Python `logging` (not print), at `INFO` for successful calls and `WARNING` for failures.

5. **Provider switching is config-only.** Switching from Bedrock to Gemini to LM Studio requires only changing `LlmConfig.model_slug` (and optionally `api_base` for local models). No code changes, no conditional imports, no `USE_MODEL_INFERENCE` env var checks. The legacy pattern of `if os.environ["USE_MODEL_INFERENCE"] == "GEMINI"` in `serverDeCypher.py` / `mcpClient.py` is replaced by passing the right `LlmConfig` at app construction time.

6. **Tool definitions are optional.** When `tools=None`, the LiteLLM call omits the `tools` and `tool_choice` parameters entirely. When tools are provided, `tool_choice="auto"` is passed (matching the legacy `anyMCP.py` behavior). Future: `tool_choice` could be added to `LlmConfig.extra_params` for caller control.

7. **`extra_params` passthrough.** `LlmConfig.extra_params` is unpacked as keyword arguments to `litellm.acompletion()`. This is the escape hatch for provider-specific options (e.g., Bedrock's `aws_region_name`, Gemini's `safety_settings`) without polluting the core API.

8. **Error wrapping, not forwarding.** All LiteLLM exceptions (rate limits, auth failures, model not found, timeouts, network errors) are caught and re-raised as `ProviderError` with structured `details`. The original exception type and message are preserved in `details` for debugging, but callers never need to import or handle LiteLLM exception types.

9. **Per-request LlmConfig override support (OQ-010).** `acomplete` accepts an optional `config_override: LlmConfig | None` parameter. When provided, its non-None fields are merged over the base `config` to produce an effective config for that single call. This enables callers (e.g., `host_orchestrator`, `decypher_agent`) to adjust model, temperature, or max_tokens on a per-request basis without constructing a full new `LlmConfig`. The merge is shallow: `config_override.model_slug` replaces `config.model_slug` if set, `config_override.temperature` replaces `config.temperature` if set, etc. `extra_params` dicts are merged (override wins on key conflicts). The base `config` is not mutated.

### Module structure

```
synapticore/tools/llm_provider.py
    LlmResponse                        (Pydantic BaseModel)
    SynaptiCoreLoggingCallback         (litellm.Callbacks subclass)
    acomplete()                        (async function -- primary API)
    validate_config()                   (sync function -- config validation)
    _to_litellm_messages()             (internal -- ConversationMessage -> dict conversion)
    _to_litellm_tools()               (internal -- McpToolDefinition -> dict conversion)
    _parse_response()                  (internal -- ModelResponse -> LlmResponse conversion)
    _parse_tool_calls()               (internal -- raw tool calls -> list[ToolCall] conversion)
```

### Data Flow

```
Caller (agent / app)
  |
  |  LlmConfig, list[ConversationMessage], list[McpToolDefinition]?, LlmConfig? (override)
  v
acomplete()
  |-- merge config_override into config (if provided, OQ-010)
  |-- validate_config(effective_config)          raises ConfigurationError
  |-- _to_litellm_messages(messages)             ConversationMessage -> dict
  |-- _to_litellm_tools(tools)                   McpToolDefinition -> dict (if tools provided)
  |-- start = time.perf_counter()
  |-- await litellm.acompletion(                 external call
  |       model=config.model_slug,
  |       messages=litellm_messages,
  |       tools=litellm_tools,                   (omitted if None)
  |       tool_choice="auto",                    (omitted if no tools)
  |       api_base=config.api_base,              (omitted if None)
  |       temperature=config.temperature,
  |       max_tokens=config.max_tokens,
  |       **config.extra_params
  |   )
  |-- latency_ms = (perf_counter() - start) * 1000
  |-- _parse_response(response, latency_ms)      ModelResponse -> LlmResponse
  |
  v
LlmResponse  -->  caller
```

### Callback Design

```python
class SynaptiCoreLoggingCallback(litellm.Callbacks):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        # Log: model, provider, prompt_tokens, completion_tokens, latency_ms
    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        # Log: model, provider, error_type, error_message
```

Registered once at module level: `litellm.callbacks = [SynaptiCoreLoggingCallback()]`. This is additive -- if other callbacks are registered elsewhere, they are preserved.

## Dependencies

### Internal

- `types/common_types` -- `LlmConfig`, `ConversationMessage`, `ConversationRole`, `ToolCall`, `TokenUsage`, `ProviderError`, `ConfigurationError`
- `types/mcp_types` -- `McpToolDefinition` (for tool definition input)

### External

- `litellm` -- `acompletion()`, `Callbacks`, exception types (`AuthenticationError`, `RateLimitError`, `BadRequestError`, `Timeout`, `APIConnectionError`, `ServiceUnavailableError`)
- `pydantic` -- `BaseModel`, `Field`
- `json` -- `dumps()`, `loads()` (for tool call argument serialization boundary)
- `time` -- `perf_counter()` (latency measurement)
- `logging` -- structured logging in callback

## Error Contracts

### Raised by this module

| Error | When | Details contents |
|-------|------|-----------------|
| `ProviderError` | LiteLLM call fails (any provider-side error) | `{"original_error": str, "error_type": str, "model_slug": str, "provider": str}` |
| `ProviderError` | LiteLLM returns a response with no choices | `{"reason": "empty_response", "model_slug": str}` |
| `ProviderError` | Tool call argument JSON parsing fails | `{"reason": "invalid_tool_call_json", "raw_arguments": str, "tool_name": str}` |
| `ConfigurationError` | `model_slug` is empty or None | `{"config_key": "model_slug"}` |
| `ConfigurationError` | `model_slug` has no provider prefix and `api_base` is not set | `{"config_key": "model_slug", "hint": "Use 'provider/model' format or set api_base for local models"}` |

### LiteLLM exception mapping

| LiteLLM Exception | Mapped to | Notes |
|-------------------|-----------|-------|
| `litellm.AuthenticationError` | `ProviderError` | Missing or invalid API keys / AWS credentials |
| `litellm.RateLimitError` | `ProviderError` | Provider rate limit hit |
| `litellm.BadRequestError` | `ProviderError` | Invalid model, bad parameters, content policy |
| `litellm.Timeout` | `ProviderError` | Provider call timed out |
| `litellm.APIConnectionError` | `ProviderError` | Network failure to provider |
| `litellm.ServiceUnavailableError` | `ProviderError` | Provider is down |
| Any other `Exception` | `ProviderError` | Catch-all for unexpected LiteLLM errors |

### Not raised

- `ToolExecutionError` -- this module does not execute tools, only passes tool definitions to the LLM.
- `ToolNotFoundError` -- tool lookup is the caller's responsibility (via `tool_registry`).

## Test Plan

### Unit tests (`tests/unit/tools/test_llm_provider.py`)

All unit tests mock `litellm.acompletion` -- no real LLM calls.

**`LlmResponse` model:**
- Constructs with all fields (content, tool_calls, usage, model, latency_ms)
- Constructs with `content=None` and `tool_calls` present
- Constructs with `tool_calls=None` and content present
- `usage` is a `TokenUsage` instance
- Serialization round-trip: `model_dump()` -> `model_validate()`

**`acomplete` -- happy path:**
- Returns `LlmResponse` with text content when LLM returns a simple text response
- Returns `LlmResponse` with tool calls when LLM requests tool execution
- Returns `LlmResponse` with both content and tool calls (some providers do this)
- `usage` fields match the mocked LiteLLM response
- `model` field matches the mocked LiteLLM response model
- `latency_ms` is a positive float

**`acomplete` -- message conversion:**
- USER message converts to `{"role": "user", "content": "..."}`
- ASSISTANT message converts with role `"assistant"`
- SYSTEM message converts with role `"system"`
- TOOL message converts with `"role": "tool"`, `"tool_call_id"`, and `"content"`
- ASSISTANT message with tool_calls: `ToolCall.arguments` (dict) is JSON-encoded to string
- Message with `name` field passes it through
- Message with `content=None` passes None through

**`acomplete` -- tool definition conversion:**
- `McpToolDefinition` converts to `{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}`
- `tags` and `category` are stripped from the output
- Empty tool list results in `tools` and `tool_choice` being omitted from the LiteLLM call
- `None` tools results in `tools` and `tool_choice` being omitted

**`acomplete` -- config passthrough:**
- `temperature` from `LlmConfig` is passed to `acompletion()`
- `max_tokens` from `LlmConfig` is passed to `acompletion()`
- `api_base` from `LlmConfig` is passed to `acompletion()` when set
- `api_base=None` is omitted from the `acompletion()` call
- `extra_params` dict is unpacked as kwargs to `acompletion()`
- `extra_params=None` results in no extra kwargs

**`acomplete` -- per-request config override (OQ-010):**
- `config_override` with `model_slug` overrides base config's `model_slug`
- `config_override` with `temperature` overrides base config's `temperature`
- `config_override` with `max_tokens` overrides base config's `max_tokens`
- `config_override` with `extra_params` merges with base config's `extra_params` (override wins on conflict)
- `config_override=None` uses base config unchanged
- `config_override` with all `None` fields uses base config unchanged
- Base `config` object is not mutated by override
- Merged config is validated (raises `ConfigurationError` if override produces invalid config)

**`acomplete` -- response parsing:**
- Tool call `arguments` (JSON string from LiteLLM) is parsed to dict in `ToolCall.arguments`
- Multiple tool calls in a single response are all parsed
- Tool call with no arguments (`"{}"`) parses to empty dict

**`acomplete` -- error handling:**
- `litellm.AuthenticationError` raises `ProviderError` with `error_type` in details
- `litellm.RateLimitError` raises `ProviderError`
- `litellm.BadRequestError` raises `ProviderError`
- `litellm.Timeout` raises `ProviderError`
- `litellm.APIConnectionError` raises `ProviderError`
- `litellm.ServiceUnavailableError` raises `ProviderError`
- Unexpected exception raises `ProviderError` (catch-all)
- All `ProviderError` instances include `model_slug` and original error message in `details`
- Empty response (no choices) raises `ProviderError` with `reason: "empty_response"`
- Malformed tool call JSON raises `ProviderError` with `reason: "invalid_tool_call_json"`

**`validate_config`:**
- Accepts valid slugs: `"bedrock/claude-3-sonnet"`, `"gemini/gemini-1.5-flash"`, `"openai/local-model"`
- Accepts slug without provider prefix when `api_base` is set (LM Studio scenario)
- Rejects empty string `model_slug` with `ConfigurationError`
- Rejects `None` `model_slug` with `ConfigurationError`
- Rejects slug without provider prefix when `api_base` is also not set

**Callback:**
- `SynaptiCoreLoggingCallback.async_log_success_event` logs at INFO level
- `SynaptiCoreLoggingCallback.async_log_failure_event` logs at WARNING level

### Integration tests (`tests/integration/tools/test_llm_provider_integration.py`)

Real LLM call against one provider. Gated by environment (skip if no API keys configured).

- `acomplete` with a simple prompt returns `LlmResponse` with non-empty content
- `acomplete` with tool definitions returns `LlmResponse` (may or may not include tool calls depending on prompt)
- `acomplete` with invalid model slug raises `ProviderError`
- Token usage fields are all positive integers
- `latency_ms` is a positive float in a reasonable range (>0, <60000)

### Edge cases

- `ConversationMessage` list with only a system message (no user message) -- LiteLLM may reject; verify `ProviderError` is raised
- Very long message list (token budget exceeded) -- verify `ProviderError` wraps the provider's context length error
- `LlmConfig` with `extra_params` containing provider-specific keys (e.g., `{"aws_region_name": "us-west-2"}`)
- Tool definition with empty `input_schema` (`{}`) -- valid, some tools take no parameters
- Response where `usage` is None (some local models) -- handle gracefully with zero-value `TokenUsage`

## ADR References

- None pending. LiteLLM is the established provider abstraction (already in `pyproject.toml`). No alternative evaluation needed.
- Future ADR candidate: retry policy (exponential backoff on `RateLimitError`). Currently not implemented -- callers handle retries if needed.
- Future ADR candidate: streaming support (`acompletion` with `stream=True`). Not in v1 scope. When added, will likely be a separate `astream_complete()` function returning `AsyncIterable[LlmStreamChunk]`.

## Maturity

All functions: `stub` (rewrite target)
