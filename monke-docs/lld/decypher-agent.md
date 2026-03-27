# LLD: decypher_agent

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: agents/
> HLD Reference: S3 C1.4.1
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Conversational agent with tool access. Receives user messages, reasons about whether to use tools or respond directly, executes tool calls if needed, returns responses. Streams `AgUiEvent` when invoked via `agui_server`. Execution framework is ADR-gated (OQ-001) -- this LLD defines the abstract agent loop, not a specific framework binding.

## CoALA Specification

```
Agent: decypher_agent
Pattern: Augmented LLM
Loop: observe(user message) -> retrieve(tool execution, e.g. web search) -> reason(LLM call with tool defs + results) -> [execute(next tool call)] -> respond/loop
Memory:
  working:   context window, budget per LlmConfig
  episodic:  in-memory conversation state, per thread_id (framework ADR determines store)
  semantic:  none (no persistent knowledge base in v1)
  procedural: system prompt template
Actions:
  internal:  reasoning via LLM
  external:  web_search (static-contract), calculator (static-contract), llm_provider (versioned-artifact)
  boundaries: no filesystem access, no arbitrary code execution, no network calls outside registered tools
Stops when: LLM returns response without tool calls, OR max iterations reached (configurable, default 10)
Human-in-loop: none in v1 (future: AG-UI interrupt events)
Version pins: LLM model slug per LlmConfig
Eval thresholds: none v1 (deferred -- llm_provider is versioned-artifact but eval infra not yet built)
```

## Public API

### Configuration

| Class | Fields | Notes |
|-------|--------|-------|
| `DecypherAgentConfig` | `llm_config: LlmConfig`, `system_prompt: str \| None = None`, `tool_names: list[str] \| None = None`, `max_iterations: int = 10` | Agent configuration. `tool_names` selects tools from `tool_registry`; `None` means all registered tools. `system_prompt` overrides the default procedural prompt. `max_iterations` caps the observe-reason-execute loop to prevent runaway tool chains. |

### Agent Executor

| Function / Method | Signature | Notes |
|-------------------|-----------|-------|
| `create_decypher_agent` | `(config: DecypherAgentConfig, tool_registry: ToolRegistry, llm_provider: LlmProvider) -> DecypherAgent` | Factory function. Resolves tool definitions from `tool_registry`, validates `llm_config`, returns a configured agent instance. Framework-agnostic -- the returned object implements the `DecypherAgent` protocol regardless of internal execution strategy. |
| `DecypherAgent.run` | `async (messages: list[ConversationMessage], thread_id: str \| None = None) -> ConversationMessage` | Single-shot execution. Runs the full agent loop (observe -> reason -> execute -> ... -> respond). Returns the final assistant message. `thread_id` keys episodic memory for multi-turn conversations. |
| `DecypherAgent.stream` | `async (messages: list[ConversationMessage], thread_id: str \| None = None) -> AsyncIterator[AgUiEvent]` | Streaming execution. Same agent loop as `run`, but yields `AgUiEvent` objects as the loop progresses. Used by `agui_server` to push events to the frontend via SSE. |

### Agent Protocol (Abstract Interface)

```python
class DecypherAgent(Protocol):
    """Framework-agnostic agent interface.

    Implementations may use LangGraph StateGraph, a plain Python
    async loop, or any other execution strategy. The public contract
    is these two methods plus the config accessor.
    """

    @property
    def config(self) -> DecypherAgentConfig: ...

    async def run(
        self,
        messages: list[ConversationMessage],
        thread_id: str | None = None,
    ) -> ConversationMessage: ...

    async def stream(
        self,
        messages: list[ConversationMessage],
        thread_id: str | None = None,
    ) -> AsyncIterator[AgUiEvent]: ...
```

## Internal Design

### Abstract Agent Loop

The agent loop is described here as a framework-agnostic state machine. The actual implementation (LangGraph, plain Python, etc.) is determined by OQ-001 ADR. Any implementation MUST preserve this loop contract.

```
                         ┌──────────────┐
                         │   OBSERVE    │
                         │ (user msg +  │
                         │  history)    │
                         └──────┬───────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │       REASON          │
                    │  LLM call with:       │
                    │  - system prompt      │
                    │  - conversation       │
                    │  - tool definitions   │
                    │  - tool results (if   │
                    │    any from prior      │
                    │    iteration)          │
                    └───────────┬───────────┘
                                │
                        ┌───────┴────────┐
                        │                │
                   has tool_calls?   no tool_calls
                        │                │
                        ▼                ▼
                 ┌─────────────┐  ┌─────────────┐
                 │   EXECUTE   │  │   RESPOND   │
                 │ run tools   │  │ return msg  │
                 │ via registry│  │ (terminal)  │
                 └──────┬──────┘  └─────────────┘
                        │
                        ▼
                 iteration < max?
                   yes │    no
                       │     │
                       ▼     ▼
                   REASON  RESPOND
                   (loop)  (forced: max
                            iterations
                            exceeded)
```

### Phase Details

**1. OBSERVE**

Assembles the full message history for the LLM call:
- System prompt (from `config.system_prompt` or default)
- Episodic memory: prior conversation turns for this `thread_id`
- Current user message(s) from the `messages` argument
- Any tool results from the previous EXECUTE phase (on loop iterations > 0)

The observe phase does NOT call the LLM. It prepares the input.

**2. REASON**

Single LLM call via `llm_provider`:
- Input: assembled `list[ConversationMessage]` + `list[ToolDefinition]` (from resolved tools)
- LLM config: from `DecypherAgentConfig.llm_config`
- Output: `LlmResponse` containing either:
  - `content` (text response, no tool calls) -> terminal, proceed to RESPOND
  - `tool_calls` (one or more `ToolCall` objects) -> proceed to EXECUTE

During streaming (`stream` method), this phase emits:
- `StepStartedEvent` (step_name: `"reason"`, step_id: iteration index)
- `TextMessageStartEvent` / `TextMessageContentEvent` / `TextMessageEndEvent` if the LLM produces text content alongside or instead of tool calls
- `StepFinishedEvent`

**3. EXECUTE**

For each `ToolCall` returned by REASON:
1. Look up the tool handler in `tool_registry` by `ToolCall.name`
2. Invoke the handler with `ToolCall.arguments`
3. Capture the result as a `ToolResult` (content string + is_error flag)
4. If the tool raises `ToolExecutionError`, capture it as `ToolResult(is_error=True)` rather than propagating -- the LLM should see tool errors and reason about them

All tool results are appended to the conversation as `ConversationMessage(role=TOOL, ...)` entries.

During streaming, this phase emits per tool call:
- `ToolCallStartEvent` (tool_call_id, tool_call_name)
- `ToolCallArgsEvent` (JSON-encoded arguments)
- `ToolCallEndEvent` (result string or error)

**4. RESPOND**

Terminal phase. Reached when:
- REASON returns a response with no `tool_calls` (normal termination)
- Iteration count reaches `max_iterations` (forced termination -- the last LLM response is used as-is, or a fallback message is constructed if the last response was only tool calls)

During streaming, this phase emits:
- `TextMessageStartEvent` / `TextMessageContentEvent` / `TextMessageEndEvent` for the final response (if not already emitted during REASON)
- `RunFinishedEvent`

### Episodic Memory (Conversation State)

| Concern | Design |
|---------|--------|
| Keying | `thread_id: str`. Each unique thread_id maintains a separate conversation history. `None` thread_id creates a single-turn ephemeral conversation. |
| Storage | In-memory plain dict: `dict[str, list[ConversationMessage]]` per `thread_id`. Not persisted across restarts (v1 limitation). |
| Scope | Per-agent instance. Each `DecypherAgent` holds its own memory store. |
| Pruning | **Sliding window: max 200 messages per thread (OQ-027).** When the message list exceeds 200, the oldest messages (after the system message) are dropped to stay within the window. The system message is always retained at position 0. This prevents unbounded context growth and `ProviderError` from context window overflow. |
| Framework ADR impact | The memory store abstraction is the primary decision surface for OQ-001. A LangGraph implementation would use `MemorySaver` or `StateGraph` checkpointing. A plain Python loop would use the dict directly. The public API (`run`/`stream` with `thread_id`) is identical in both cases. |

### Streaming Event Sequence

A complete `stream` invocation for a 2-iteration loop (1 tool call, then final response):

```
RunStartedEvent(thread_id, run_id)
  StepStartedEvent(step_name="reason", step_id="0")
  StepFinishedEvent(step_name="reason", step_id="0")
  ToolCallStartEvent(tool_call_id, tool_call_name="web_search")
  ToolCallArgsEvent(tool_call_id, delta="{\"query\": \"...\"}")
  ToolCallEndEvent(tool_call_id, result="...")
  StepStartedEvent(step_name="reason", step_id="1")
  TextMessageStartEvent(message_id, role=ASSISTANT)
  TextMessageContentEvent(message_id, delta="Based on the search results...")
  TextMessageEndEvent(message_id)
  StepFinishedEvent(step_name="reason", step_id="1")
RunFinishedEvent(thread_id, run_id, status=COMPLETED)
```

Error during execution:

```
RunStartedEvent(thread_id, run_id)
  StepStartedEvent(step_name="reason", step_id="0")
  StepFinishedEvent(step_name="reason", step_id="0")
  ToolCallStartEvent(tool_call_id, tool_call_name="web_search")
  ToolCallEndEvent(tool_call_id, result="Error: ToolExecutionError: ...")
  StepStartedEvent(step_name="reason", step_id="1")
  TextMessageStartEvent(message_id, role=ASSISTANT)
  TextMessageContentEvent(message_id, delta="I encountered an error searching...")
  TextMessageEndEvent(message_id)
  StepFinishedEvent(step_name="reason", step_id="1")
RunFinishedEvent(thread_id, run_id, status=COMPLETED)
```

Unrecoverable error (LLM provider failure):

```
RunStartedEvent(thread_id, run_id)
  StepStartedEvent(step_name="reason", step_id="0")
RunErrorEvent(thread_id, run_id, error_code="PROVIDER_ERROR", error_message="...")
```

### Max Iterations Guard

When the loop reaches `max_iterations`:
1. The agent does NOT make another LLM call
2. If the last REASON response contained text content, that is used as the final response
3. If the last REASON response contained only tool calls (no text), a fallback response is constructed: `ConversationMessage(role=ASSISTANT, content="I've reached the maximum number of reasoning steps. Here's what I found so far: [summary of last tool results]")`
4. In streaming mode, a `CustomEvent(name="max_iterations_reached", value=max_iterations)` is emitted before the final response events

### System Prompt (Default Procedural Memory)

The default system prompt is a constant string embedded in the module. It can be overridden entirely via `DecypherAgentConfig.system_prompt`. The default prompt:
- Identifies the agent as DeCypher
- Describes available tools generically (populated at runtime from resolved `ToolDefinition` descriptions)
- Instructs the LLM to use tools when the user's question requires external information
- Instructs the LLM to respond directly when the question is conversational or within the LLM's knowledge

The system prompt is NOT a template with format-string placeholders. Tool descriptions are appended programmatically as a structured block after the base prompt text.

### Key Design Decisions

1. **Framework-agnostic protocol** -- `DecypherAgent` is a Python `Protocol`, not an ABC. Any class implementing `run` and `stream` with matching signatures satisfies it. This decouples the public contract from OQ-001's framework decision.
2. **Factory function, not direct construction** -- `create_decypher_agent` is the only way to build an agent. It validates config, resolves tools, and returns the concrete implementation. Callers depend on the protocol, not the implementation class.
3. **Tool errors are LLM-visible, not exceptions** -- When a tool raises `ToolExecutionError`, the agent captures it as a `ToolResult(is_error=True)` and feeds it back to the LLM in the next REASON iteration. The LLM decides whether to retry, try a different tool, or explain the error to the user. Only `ProviderError` (LLM itself failed) terminates the loop as an unrecoverable error.
4. **`run` and `stream` share the same loop** -- The loop logic is implemented once. `run` collects the final `ConversationMessage`. `stream` wraps the same loop with `AgUiEvent` emission at each phase transition. No divergent code paths.
5. **`thread_id` is optional** -- Omitting it creates a single-turn interaction with no memory. This supports both stateless MCP tool invocation and stateful AG-UI conversations.
6. **Max iterations is a hard cap, not a soft suggestion** -- At `max_iterations`, the loop terminates unconditionally. This prevents runaway costs from tool-happy LLM responses. The default of 10 is generous for conversational use; callers can lower it for constrained scenarios.
7. **No direct framework imports in the public API** -- The module's public surface (`DecypherAgentConfig`, `DecypherAgent`, `create_decypher_agent`) uses only `common_types`, `agui_types`, and stdlib. Framework-specific types (LangGraph State, SmolAgents runner, etc.) are confined to the internal implementation chosen by OQ-001 ADR.

8. **Same-tool-same-args loop breaker (OQ-015)** -- The EXECUTE phase tracks recent tool calls as `(tool_name, arguments_hash)` tuples. If the same tool is called with identical arguments more than 2 times consecutively, the agent loop force-terminates with a fallback response indicating a tool loop was detected. This prevents degenerate LLM behavior where the model repeatedly calls the same tool expecting different results. The counter resets when a different tool is called or arguments change.

9. **Sliding window memory cap (OQ-027)** -- Conversation history per `thread_id` is capped at 200 messages. When the limit is exceeded, the oldest non-system messages are dropped from the front of the list. The system message (index 0) is always preserved. This is enforced at the start of the OBSERVE phase before assembling messages for the LLM call.

### Module Structure

```
synapticore/agents/decypher_agent.py
    DecypherAgentConfig         (Pydantic BaseModel)
    DecypherAgent               (Protocol)
    create_decypher_agent       (factory function)
    _DEFAULT_SYSTEM_PROMPT      (module constant)
    _DecypherAgentImpl          (private -- concrete implementation, framework per OQ-001)
    _build_system_message       (private -- assembles system prompt + tool descriptions)
    _run_agent_loop             (private -- abstract loop: observe/reason/execute/respond)
    _emit_stream_events         (private -- wraps loop phases with AgUiEvent yields)
```

## Dependencies

### Internal
- `types/common_types` -- `LlmConfig`, `ConversationMessage`, `ConversationRole`, `ToolCall`, `ToolResult`, `ToolExecutionError`, `ProviderError`, `ToolNotFoundError`
- `types/agui_types` -- `AgUiEvent`, `RunStartedEvent`, `RunFinishedEvent`, `RunErrorEvent`, `TextMessageStartEvent`, `TextMessageContentEvent`, `TextMessageEndEvent`, `ToolCallStartEvent`, `ToolCallArgsEvent`, `ToolCallEndEvent`, `StepStartedEvent`, `StepFinishedEvent`, `CustomEvent`
- `tools/llm_provider` -- `LlmProvider` (the `complete` function / class for LLM calls)
- `tools/tool_registry` -- `ToolRegistry` (for resolving tool definitions and handlers)

### External
- `pydantic` (BaseModel, Field)
- `typing` / `typing_extensions` (Protocol, AsyncIterator, Any)
- `uuid` (run_id, message_id generation)
- `logging` (structured logging per cross-cutting concerns)
- Framework-specific dependencies: **TBD per OQ-001 ADR**. Candidates: `langgraph` (StateGraph, MemorySaver), or none (plain async Python).

## Error Contracts

### Raised by this module
- None directly. `decypher_agent` does not define new exception types. It propagates or wraps existing errors.

### Propagated errors

| Error | Source | Handling |
|-------|--------|----------|
| `ProviderError` | `llm_provider` | **Unrecoverable.** Terminates the agent loop. In `run` mode: re-raised to caller. In `stream` mode: emits `RunErrorEvent` then stops. |
| `ConfigurationError` | `llm_provider`, startup validation | **Unrecoverable.** Raised during `create_decypher_agent` if `llm_config` is invalid, or during loop if provider config is missing. |
| `ToolNotFoundError` | `tool_registry` | **Raised during `create_decypher_agent`** if `config.tool_names` references a tool not in the registry. Caught early, not at execution time. |
| `ToolExecutionError` | Tool handlers via `tool_registry` | **Recovered.** Captured as `ToolResult(is_error=True)` and fed back to the LLM. The agent continues its loop. |

### Emitted as AG-UI events (stream mode only)

| Condition | Event |
|-----------|-------|
| `ProviderError` during REASON | `RunErrorEvent(error_code="PROVIDER_ERROR", error_message=str(e))` |
| `ConfigurationError` during loop | `RunErrorEvent(error_code="CONFIGURATION_ERROR", error_message=str(e))` |
| Unexpected exception | `RunErrorEvent(error_code="INTERNAL_ERROR", error_message=str(e))` |
| Max iterations reached | `CustomEvent(name="max_iterations_reached", value=max_iterations)` followed by normal `RunFinishedEvent` |

## Test Plan

### Unit tests (`tests/unit/agents/test_decypher_agent.py`)

**DecypherAgentConfig:**
- Constructs with `llm_config` only (all defaults: `max_iterations=10`, `system_prompt=None`, `tool_names=None`)
- Constructs with all fields specified
- Rejects `max_iterations < 1` (validator)
- `tool_names=None` means "all tools" (resolved at factory time)
- `tool_names=[]` means "no tools" (pure conversation, no tool definitions sent to LLM)

**Factory function (`create_decypher_agent`):**
- Returns object satisfying `DecypherAgent` protocol
- Resolves tools from registry when `tool_names` is specified
- Resolves all tools when `tool_names` is `None`
- Raises `ToolNotFoundError` when `tool_names` references unknown tool
- Raises `ConfigurationError` when `llm_config` is invalid (e.g., empty `model_slug`)

**Agent loop (`run` method):**
- Single-turn: user message -> LLM responds without tool calls -> returns response
- Tool loop: user message -> LLM requests tool -> tool executes -> LLM responds -> returns response
- Multi-tool: LLM requests 2 tools in one response -> both execute -> results fed back -> LLM responds
- Max iterations: LLM requests tools every iteration -> loop terminates at `max_iterations` -> returns fallback response
- Tool error recovery: tool raises `ToolExecutionError` -> captured as `ToolResult(is_error=True)` -> LLM reasons about error -> responds
- Provider error: `llm_provider` raises `ProviderError` -> re-raised to caller
- Thread memory: two `run` calls with same `thread_id` -> second call sees first conversation
- No thread: `run` with `thread_id=None` -> no history retained
- System prompt: custom `system_prompt` in config -> appears as first message in LLM call
- Default system prompt: `system_prompt=None` -> default prompt used with tool descriptions appended

**Streaming (`stream` method):**
- Emits `RunStartedEvent` first, `RunFinishedEvent` last
- Single-turn produces: `RunStarted`, `StepStarted(reason)`, `TextMessageStart`, `TextMessageContent`+, `TextMessageEnd`, `StepFinished(reason)`, `RunFinished`
- Tool loop produces `ToolCallStart`, `ToolCallArgs`, `ToolCallEnd` events between step events
- Provider error emits `RunErrorEvent` and stops stream
- Tool error emits `ToolCallEndEvent` with error result, stream continues
- Max iterations emits `CustomEvent(max_iterations_reached)` before final response events
- All events carry consistent `thread_id` and `run_id`

**Edge cases:**
- Empty messages list -> raises `ValueError` (nothing to process)
- Messages with only system role -> raises `ValueError` (no user message)
- `tool_names=[]` (no tools) -> LLM called without tool definitions, always responds directly
- LLM returns both `content` and `tool_calls` -> text content streamed, then tools executed, loop continues
- Thread memory isolation: different `thread_id` values do not share history

### Integration tests (`tests/integration/agents/test_decypher_agent_integration.py`)

- Full loop with mock `llm_provider` and real `tool_registry` (calculator tool) -> calculates expression and responds
- Full loop with mock `llm_provider` and mock web_search tool -> searches and summarizes
- `stream` output consumed by mock `agui_server` SSE serializer -> valid SSE event sequence
- Multi-turn conversation via repeated `run` calls with same `thread_id`

## ADR References

| ID | Status | Summary |
|----|--------|---------|
| OQ-001 | **Open -- blocks implementation** | Agent execution framework: LangGraph StateGraph, plain Python async loop, or other. This LLD is framework-agnostic. The concrete `_DecypherAgentImpl` cannot be written until this ADR is resolved. The public API (`DecypherAgent` protocol, `create_decypher_agent`, `DecypherAgentConfig`) is stable regardless of ADR outcome. |

## Maturity

All functions: `stub` (rewrite target)
