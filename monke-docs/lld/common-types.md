# LLD: common_types

> Container: C1 (synapticore-core) | Subpackage: types/
> HLD Reference: S3 C1.1.4
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Shared domain models crossing subpackage boundaries -- LLM config, conversation primitives, error base classes.

## Public API

### LLM Configuration

| Class | Fields | Notes |
|-------|--------|-------|
| `LlmConfig` | `model_slug: str`, `provider: str \| None = None`, `temperature: float = 0.7`, `max_tokens: int = 4096`, `api_base: str \| None = None`, `extra_params: dict[str, Any] \| None = None` | Passed to `tools/llm_provider` for all LLM calls. `model_slug` is a LiteLLM-compatible identifier (e.g., `"bedrock/claude-3-sonnet"`, `"gemini/gemini-1.5-flash"`, `"openai/local-model"`). `api_base` enables LM Studio and other OpenAI-compatible local endpoints. `provider` is optional hint for LiteLLM routing. `extra_params` is a passthrough dict for provider-specific options. |

### Conversation Primitives

| Class | Fields | Notes |
|-------|--------|-------|
| `ConversationRole` | `str, Enum`: `USER`, `ASSISTANT`, `SYSTEM`, `TOOL` | Role in a conversation turn. Aligns with LiteLLM/OpenAI message roles. |
| `ConversationMessage` | `role: ConversationRole`, `content: str \| None = None`, `tool_calls: list[ToolCall] \| None = None`, `tool_call_id: str \| None = None`, `name: str \| None = None` | Single conversation turn. `content` is the text payload. `tool_calls` is present when the assistant requests tool execution. `tool_call_id` is present when this message is a tool result. `name` is an optional display name. |

### Tool Call & Result

| Class | Fields | Notes |
|-------|--------|-------|
| `ToolCall` | `id: str`, `name: str`, `arguments: dict[str, Any]` | Represents an LLM-requested tool invocation. `arguments` is the parsed (not JSON-encoded) argument dict. |
| `ToolResult` | `tool_call_id: str`, `content: str`, `is_error: bool = False` | Result of executing a `ToolCall`. `content` is the stringified result. `is_error` signals failure to the LLM. |

### Token Usage

| Class | Fields | Notes |
|-------|--------|-------|
| `TokenUsage` | `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int` | Returned by `llm_provider` with every LLM response. Used for logging and cost tracking. |

### Error Hierarchy

| Class | Inherits | Fields | Notes |
|-------|----------|--------|-------|
| `SynaptiCoreError` | `Exception` | `message: str`, `details: dict[str, Any] \| None = None` | Base exception for all SynaptiCore errors. All custom exceptions inherit from this. `details` carries structured context for logging. |
| `ProviderError` | `SynaptiCoreError` | `provider: str \| None = None`, `model_slug: str \| None = None` | LLM provider failures (rate limits, auth errors, model not found, timeouts). Raised by `tools/llm_provider`. |
| `ConfigurationError` | `SynaptiCoreError` | `config_key: str \| None = None` | Missing or invalid configuration (env vars, model slugs, connection strings). Replaces the legacy `MissingAPIKeyError` from `a2a_types`. |
| `ToolExecutionError` | `SynaptiCoreError` | `tool_name: str`, `original_error: str \| None = None` | Tool execution failures (search API down, SQL error, PDF parse failure). Raised by individual tool modules. |
| `ToolNotFoundError` | `SynaptiCoreError` | `tool_name: str` | Requested tool not registered in `tool_registry`. |
| `DuplicateToolError` | `SynaptiCoreError` | `tool_name: str` | Attempt to register a tool with a name that already exists. |

### Error-to-Protocol Mapping Guide

This module defines the error hierarchy. Each protocol server maps these to protocol-specific error codes:

| Internal Error | A2A (JSON-RPC) | MCP | AG-UI (SSE) |
|---------------|----------------|-----|-------------|
| `SynaptiCoreError` | `InternalError` (-32603) | MCP internal error | `RunErrorEvent` |
| `ProviderError` | `InternalError` (-32603) | MCP internal error | `RunErrorEvent` |
| `ConfigurationError` | `InternalError` (-32603) | MCP internal error | `RunErrorEvent` |
| `ToolExecutionError` | `InternalError` (-32603) | MCP tool error | `RunErrorEvent` |
| `ToolNotFoundError` | `InvalidParamsError` (-32602) | MCP tool not found | `RunErrorEvent` |
| `pydantic.ValidationError` | `InvalidRequestError` (-32600) | MCP invalid params | HTTP 400 |

## Internal Design

### Key Design Decisions

1. **Domain models, not protocol models** -- `ConversationMessage` and `ToolCall` represent internal domain concepts. They are distinct from A2A `Message`/`Part` and AG-UI `AgUiMessage`/`AgUiToolCall`. Protocol layers translate between domain and wire types.
2. **`LlmConfig` is the sole LLM configuration surface** -- Every component that needs LLM access accepts an `LlmConfig`. No component constructs LiteLLM calls with raw strings. This ensures provider switching is a config change, not a code change.
3. **`ToolCall.arguments` is a parsed dict** -- Unlike AG-UI's `AgUiToolCall.arguments` (JSON-encoded string), the internal `ToolCall.arguments` is already parsed. The AG-UI layer handles the JSON string encoding/decoding at the boundary.
4. **Error hierarchy is exception-based** -- Unlike `a2a_types` where JSON-RPC errors are Pydantic models (for serialization), `common_types` errors are Python exceptions (for `raise`/`except`). This separation is intentional: protocol errors serialize, domain errors propagate.
5. **`details` on `SynaptiCoreError`** -- Structured error context for logging. Protocol layers extract `message` for user-facing responses and log `details` for debugging. Never exposed to end users.
6. **Replaces scattered legacy utilities** -- `MissingAPIKeyError` (from a2a common_types), `genFuncs` error handling, `langFuncs` state assumptions -- all consolidated into this module.

### Module structure

```
synapticore/types/common_types.py
    LlmConfig
    ConversationRole (enum)
    ConversationMessage
    ToolCall
    ToolResult
    TokenUsage
    SynaptiCoreError (base exception)
    ProviderError
    ConfigurationError
    ToolExecutionError
    ToolNotFoundError
    DuplicateToolError
```

## Dependencies

### Internal
- None. This is a leaf module in `types/`.

### External
- `pydantic` (BaseModel, Field)
- `typing` (Any)
- `enum` (Enum)

## Error Contracts

### Defined by this module (Python exceptions -- raised by downstream consumers)
- `SynaptiCoreError` -- base, never raised directly
- `ProviderError` -- raised by `tools/llm_provider`
- `ConfigurationError` -- raised by any module during startup or config validation
- `ToolExecutionError` -- raised by tool modules (`web_search`, `calculator`, `snowflake_connector`, `pdf_processor`)
- `ToolNotFoundError` -- raised by `tools/tool_registry`
- `DuplicateToolError` -- raised by `tools/tool_registry`

### Raised implicitly
- `pydantic.ValidationError` on invalid model construction (e.g., missing `model_slug` on `LlmConfig`).

## Test Plan

### Unit tests (`tests/unit/types/test_common_types.py`)

**LlmConfig:**
- Constructs with `model_slug` only (all defaults)
- Constructs with all fields specified
- Rejects empty `model_slug` (validator -- empty string is not a valid slug)
- `temperature` defaults to 0.7, `max_tokens` defaults to 4096
- `api_base` accepts valid URL strings
- `extra_params` preserves arbitrary nested dicts

**ConversationMessage:**
- Constructs user message (role=USER, content="hello")
- Constructs assistant message with tool calls
- Constructs tool result message (role=TOOL, tool_call_id set, content set)
- `ConversationRole` enum covers all 4 values

**ToolCall & ToolResult:**
- `ToolCall` constructs with id, name, and parsed arguments dict
- `ToolResult` constructs with tool_call_id and content
- `ToolResult` with `is_error=True`

**TokenUsage:**
- Constructs with all three token counts
- `total_tokens` equals `prompt_tokens + completion_tokens` (test convention, not enforced by validator)

**Error hierarchy:**
- `SynaptiCoreError` is subclass of `Exception`
- `ProviderError` is subclass of `SynaptiCoreError`
- `ConfigurationError` is subclass of `SynaptiCoreError`
- `ToolExecutionError` is subclass of `SynaptiCoreError`
- `ToolNotFoundError` is subclass of `SynaptiCoreError`
- `DuplicateToolError` is subclass of `SynaptiCoreError`
- All error classes carry `message` attribute
- `ProviderError` carries `provider` and `model_slug`
- `ToolExecutionError` carries `tool_name` and `original_error`
- `ConfigurationError` carries `config_key`
- `details` dict is optional and defaults to None

**Serialization round-trip:**
- `model_dump()` -> `model_validate()` for `LlmConfig`, `ConversationMessage`, `ToolCall`, `ToolResult`, `TokenUsage`

**Edge cases:**
- `ConversationMessage` with `content=None` and `tool_calls` present (valid -- assistant requesting tools)
- `ConversationMessage` with both `content` and `tool_calls` (valid -- some providers include text alongside tool calls)
- `LlmConfig` with `api_base` set (LM Studio / local model scenario)
- `ToolCall.arguments` with deeply nested dict
- Error `details` with nested structure

## ADR References

- None pending. Common types are project-internal with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
