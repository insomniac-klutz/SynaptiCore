# LLD: decypher_app

> Container: C3 (synapticore-apps) | Application: DeCypher
> HLD Reference: S3 C3.1
> Status: stub (rewrite -- not yet implemented)

## Responsibility

DeCypher application configuration wrapper. Creates a configured `decypher_agent` instance from C1 by composing system prompt, tool set, and LLM config. Optionally registers the agent with `tool_registry` (MCP exposure) and `a2a_server` (A2A exposure). This module is a traditional consumer of the framework -- it holds configuration, not decision logic.

## Public API

### Factory Function

| Function | Signature | Returns | Notes |
|----------|-----------|---------|-------|
| `create_decypher_agent` | `(config: DecypherConfig) -> AgentInstance` | `AgentInstance` | Composes `decypher_agent` from C1 with the provided config. Resolves tool names against `tool_registry`, builds the system prompt, and returns a callable agent instance. |

### Configuration Model

| Class | Fields | Notes |
|-------|--------|-------|
| `DecypherConfig` | `llm_config: LlmConfig`, `tools: list[str] = ["web_search", "calculator"]`, `system_prompt: str \| None = None`, `max_iterations: int = 10`, `register_mcp: bool = False`, `register_a2a: bool = False` | Pydantic model. `tools` is a list of tool names to resolve from `tool_registry`. `system_prompt` overrides the default DeCypher prompt. `register_mcp` / `register_a2a` control whether the agent is exposed via those protocols. |

### Agent Instance

| Class | Fields | Notes |
|-------|--------|-------|
| `AgentInstance` | `agent_id: str`, `config: DecypherConfig`, `execute: Callable[[list[ConversationMessage]], AsyncIterator[AgUiEvent]]` | Returned by `create_decypher_agent`. `execute` is the callable that `agui_server` invokes. `agent_id` is a stable identifier (default: `"decypher"`). |

### Default System Prompt

```
You are DeCypher, an AI assistant with access to tools for web search
and calculation. Answer user questions accurately. When you need
real-time information, use the web_search tool. When you need to
perform calculations, use the calculator tool. Be concise and helpful.
```

Overridable via `DecypherConfig.system_prompt`.

### Registration

| Function | Signature | Notes |
|----------|-----------|-------|
| `register_decypher` | `(instance: AgentInstance, tool_registry: ToolRegistry, a2a_server: A2AServer \| None = None) -> None` | Registers the agent based on config flags. If `register_mcp` is True, registers `execute` as an MCP tool in `tool_registry` (tool name: `"decypher_chat"`, input: `{"messages": list[dict]}`). If `register_a2a` is True, registers an `AgentCard` and task handler with `a2a_server`. |

## Internal Design

### Key Design Decisions

1. **Config wrapper, not an agent** -- `decypher_app` contains zero decision logic. It is tagged `traditional` in the HLD (C3). All agentic behavior (tool selection, reasoning loops, stop conditions) lives in `decypher_agent` (C1.4.1). This module only composes config and wires dependencies.
2. **Factory function, not a class** -- `create_decypher_agent` is a function, not a class constructor. The returned `AgentInstance` is a data object with a callable. This avoids class hierarchy complexity and aligns with functional composition.
3. **Tool names, not tool objects** -- `DecypherConfig.tools` is `list[str]` (tool names), not tool instances. Resolution happens at factory time via `tool_registry.get_tools(names)`. This decouples app config from tool implementation.
4. **Optional protocol registration** -- Registration with MCP and A2A is opt-in via config flags. Default behavior is a bare agent instance usable only through `agui_server`. This supports both full-stack deployment and isolated testing.
5. **System prompt override** -- The default system prompt is baked into this module, not `decypher_agent`. The agent in C1 is prompt-agnostic -- it receives the system prompt as input. This lets different apps (or test harnesses) compose the same agent with different personas.
6. **Replaces legacy `DeCypher` class** -- The existing `DeCypher` class in `SynaptiCore/Apps/DeCypher.py` uses `langBots`, `smolBots`, LangGraph `StateGraph`, and `MemorySaver` directly. The rewrite delegates all of that to `decypher_agent` (C1) and `llm_provider` (C1). LangGraph dependency is an ADR-gated decision in the agent, not the app.

### Module structure

```
synapticore/apps/decypher_app.py
    DecypherConfig         (Pydantic config model)
    AgentInstance          (dataclass: agent_id, config, execute callable)
    create_decypher_agent  (factory function)
    register_decypher      (protocol registration helper)
    DEFAULT_SYSTEM_PROMPT  (str constant)
```

### Factory flow

```
create_decypher_agent(config: DecypherConfig)
    1. Validate config (Pydantic)
    2. Resolve tools: tool_registry.get_tools(config.tools)
       → raises ToolNotFoundError if any tool name is unknown
    3. Build system prompt: config.system_prompt or DEFAULT_SYSTEM_PROMPT
    4. Create agent executor from decypher_agent(
           llm_config=config.llm_config,
           tools=resolved_tools,
           system_prompt=system_prompt,
           max_iterations=config.max_iterations
       )
    5. Return AgentInstance(
           agent_id="decypher",
           config=config,
           execute=agent_executor
       )
```

## Dependencies

### Internal
- `C1.4.1 agents/decypher_agent` -- Agent logic (reasoning loop, tool calls, LLM interaction)
- `C1.2.1 tools/llm_provider` -- LLM access (indirect, via `decypher_agent`)
- `C1.2.6 tools/tool_registry` -- Tool resolution by name
- `C1.1.4 types/common_types` -- `LlmConfig`, `ConversationMessage`, `SynaptiCoreError`, `ConfigurationError`, `ToolNotFoundError`
- `C1.1.2 types/agui_types` -- `AgUiEvent` (return type of `execute`)
- `C1.3.1 protocols/a2a_server` -- A2A registration (optional)

### External
- `pydantic` (BaseModel, Field) -- Config validation

## Error Contracts

### Raised by this module
- `ConfigurationError` -- Invalid `DecypherConfig` (e.g., empty `tools` list when agent requires at least one tool, invalid `llm_config`)
- `ToolNotFoundError` -- A tool name in `config.tools` does not exist in `tool_registry`

### Propagated from dependencies
- `ProviderError` -- From `llm_provider` during agent execution (not at creation time)
- `ToolExecutionError` -- From individual tools during agent execution
- `pydantic.ValidationError` -- From `DecypherConfig` construction with invalid fields

### Not handled here
- Agent execution errors (tool failures, LLM timeouts) propagate through the `execute` callable to `agui_server`, which translates them to `RunErrorEvent`.

## Test Plan

### Unit tests (`tests/unit/apps/test_decypher_app.py`)

**DecypherConfig validation:**
- Constructs with `llm_config` only (all defaults)
- Constructs with all fields specified
- `tools` defaults to `["web_search", "calculator"]`
- `system_prompt` defaults to None (factory uses `DEFAULT_SYSTEM_PROMPT`)
- `max_iterations` defaults to 10
- `register_mcp` and `register_a2a` default to False
- Invalid `llm_config` raises `ValidationError`

**create_decypher_agent:**
- Returns `AgentInstance` with correct `agent_id`
- `execute` is callable (async generator)
- Tool names resolved via `tool_registry.get_tools` (mock)
- Unknown tool name raises `ToolNotFoundError`
- Custom `system_prompt` is passed to agent (mock verify)
- Default system prompt used when `config.system_prompt` is None

**register_decypher:**
- With `register_mcp=True`, calls `tool_registry.register` with `"decypher_chat"` tool
- With `register_a2a=True`, registers agent card with `a2a_server`
- With both flags False, no registration calls made
- Duplicate registration raises `DuplicateToolError` (from `tool_registry`)

**AgentInstance:**
- `agent_id` is `"decypher"`
- `config` matches the input `DecypherConfig`
- Serialization round-trip of `DecypherConfig` (`model_dump` -> `model_validate`)

**Edge cases:**
- Empty `tools` list -- valid config (agent with no tools, pure LLM conversation)
- `system_prompt` with very long text (no arbitrary length limit)
- `max_iterations` set to 1 (single-turn, no tool loop)

## ADR References

- None pending in the app layer. Agent execution framework choice (OQ-001) is resolved in `decypher_agent` LLD, not here.

## Maturity

All functions: `stub` (rewrite target)
