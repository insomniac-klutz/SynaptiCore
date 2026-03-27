# LLD: host_orchestrator

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: agents/
> HLD Reference: S3 C1.4.2
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Multi-agent orchestrator using a plain Python async loop with `a2a_client`, `a2a_card_resolver`, and `llm_provider`. Discovers available remote agents via `a2a_card_resolver`, delegates tasks via `a2a_client.send_task` (versioned-artifact), manages session state via in-memory dict per `session_id`, and escalates human-in-the-loop (`input_required`) through AG-UI. This is the only component that performs cross-agent coordination -- it never executes tools directly, only delegates to remote agents.

## CoALA Specification

```
### Agent: host_orchestrator
Pattern: Orchestrator-Workers
Loop: observe(user request) -> retrieve(list available agents from card registry) -> reason(select agent + formulate task via LLM) -> execute(send_task to remote agent) -> observe(result) -> [reason(need more agents?) -> loop] -> respond
Memory:
  working: context window via llm_provider
  episodic: in-memory dict per session_id (session_id, active_agent, task_id)
  semantic: agent card registry (name -> description -> skills)
  procedural: root_instruction prompt template
Actions:
  internal: agent selection reasoning via LLM
  external:
    - list_remote_agents: static-contract
    - send_task: versioned-artifact (output depends on downstream agent's model version)
    - a2a_card_resolver: static-contract
    - llm_provider: versioned-artifact
  boundaries: cannot execute tools directly (delegates to remote agents only), cannot modify agent cards, cannot discover agents dynamically in v1
Stops when: all delegated tasks complete/fail/cancel, OR user cancels, OR input_required escalation from remote agent
Human-in-loop: input_required state triggers escalation to user via AG-UI
Version pins: LLM model slug per LlmConfig (routed via llm_provider / LiteLLM)
Eval thresholds: none v1 (send_task is versioned-artifact -- eval deferred)
```

## Public API

### Models

| Class | Fields | Notes |
|-------|--------|-------|
| `OrchestratorConfig` | `remote_agent_urls: list[str]`, `llm_config: LlmConfig \| None = None`, `max_iterations: int = 20`, `accepted_output_modes: list[str] = ["text", "text/plain", "image/png"]` | Configuration for the orchestrator. `remote_agent_urls` is the static list of base URLs for remote agents (each must serve `/.well-known/agent.json`). `llm_config` configures the LLM used for agent selection reasoning via `llm_provider`. `max_iterations` caps the observe-reason-execute loop to prevent runaway delegation. `accepted_output_modes` is the list of MIME types the orchestrator accepts from remote agents. |
| `AgentCardEntry` | `name: str`, `description: str`, `skills: list[str]`, `capabilities: AgentCapabilities`, `url: str` | Internal registry entry for a resolved remote agent. Populated from `AgentCard` at discovery time. `skills` is a flattened list of skill names from the card. |

### Functions

| Function | Signature | Notes |
|----------|-----------|-------|
| `create_host_orchestrator` | `(config: OrchestratorConfig, llm_provider: LlmProvider) -> HostOrchestrator` | Factory function. Resolves all agent cards from `config.remote_agent_urls` via `a2a_card_resolver`, builds the internal card registry, constructs tool wrappers for `list_remote_agents` and `send_task`, and returns a configured `HostOrchestrator` instance. This is the sole public entry point. Raises `ConfigurationError` if no remote agents can be resolved. |
| `register_host_orchestrator` | `(config: OrchestratorConfig, llm_provider: LlmProvider, agui_wiring: Callable) -> None` | Startup integration. Calls `create_host_orchestrator`, wraps the returned orchestrator as an AG-UI-compatible executor callable, and registers it with the `agui_server` via the provided wiring callback. Called once at startup from `app_server`. |

## Internal Design

### Key Design Decisions

1. **Plain Python async loop with a2a_client + llm_provider** -- The host orchestrator uses a plain Python async loop for orchestration. LLM reasoning (agent selection, delegation decisions) is performed via `llm_provider.acomplete()`. Session state is an in-memory dict keyed by `session_id`. No external orchestration framework is required.

2. **Card resolution happens at construction time, not per-request** -- Remote agent cards are fetched and cached when `create_host_orchestrator` is called. This matches v1 scope (static agent discovery, no dynamic registry). If a remote agent goes down after startup, `send_task` will fail at call time with `A2AClientHTTPError`, which is surfaced to the LLM as a tool error so it can reason about fallbacks.

3. **Two internal tools, not three** -- The legacy `HostAgent` references `check_pending_task_states` in the prompt but never registers it as an actual tool. The rewrite drops this phantom reference. The orchestrator exposes exactly two tools to the LLM:
   - `list_remote_agents` -- synchronous, returns the cached card registry.
   - `send_task` -- async, delegates to a remote agent via `a2a_client`.

4. **`send_task` is a versioned-artifact boundary** -- The output of `send_task` depends on the remote agent's LLM model version. The orchestrator cannot guarantee deterministic responses from remote agents. This is the primary source of non-determinism in the component. The LLM reasons about remote responses via `llm_provider`, so model version changes downstream can alter orchestration behavior.

5. **Session state via in-memory dict per session_id** -- The orchestrator manages `session_id`, `session_active`, and `agent` in a plain `dict[str, OrchestratorSessionState]` keyed by `session_id`. State keys are documented and typed via a `TypedDict` (see `OrchestratorSessionState` below). State is ephemeral -- lost on restart.

6. **HITL via orchestrator escalation + AG-UI** -- When a remote agent returns `TaskState.INPUT_REQUIRED`, the orchestrator returns an escalation signal to the caller, which (via `agui_server`) translates the escalation into AG-UI events that prompt the user for input. The orchestrator breaks out of its async loop and reports the `input_required` state upstream.

7. **Streaming-first with non-streaming fallback** -- `send_task` checks `AgentCard.capabilities.streaming`. If the remote agent supports streaming, it uses `a2a_client.send_task_streaming` and processes `SendTaskStreamingResponse` events incrementally. Otherwise, it falls back to `a2a_client.send_task` (request-response). The orchestrator loop sees the same return type regardless of mode.

8. **FilePart -> decoded artifact** -- When a remote agent returns a `FilePart` (base64-encoded), the orchestrator decodes it and returns a `DataPart` reference (`{"artifact-file-id": file_id}`). File artifacts are stored in the session state dict for retrieval via AG-UI.

9. **Metadata propagation** -- Request metadata (`conversation_id`, `message_id`) is propagated to remote agents and merged back from responses. This supports end-to-end tracing of messages across agent boundaries. The legacy `merge_metadata` logic is preserved but moved into a private helper with explicit null checks.

10. **`RemoteAgentConnections` is eliminated** -- The legacy code wraps each remote agent in a `RemoteAgentConnections` class that holds an `A2AClient` and manages streaming/non-streaming dispatch. The rewrite inlines this logic into the `send_task` tool implementation. The `A2AClient` instances are held directly in a `dict[str, A2AClient]` keyed by agent name. This removes an unnecessary indirection layer.

11. **Max iterations guard** -- `OrchestratorConfig.max_iterations` limits the total number of observe-reason-execute loops. The async loop checks the iteration counter on each pass. This prevents infinite delegation chains (e.g., agent A delegates to agent B, which returns `input_required`, orchestrator re-delegates, etc.).

12. **Replaces legacy `HostAgent` + `RemoteAgentConnections`** -- The existing code in `SynaptiCore/Core/a2aPro/core/orchestrator.py` and `SynaptiCore/Core/a2aPro/utils/remote_agent_connection.py` is the rewrite target. Key changes: typed session state, elimination of `RemoteAgentConnections` wrapper, proper error handling (no bare `ValueError`), metadata propagation as a private helper, and `OrchestratorConfig` instead of constructor args.

### Orchestration Loop

```
User request (via agui_server or a2a_server)
    |
    +-- Orchestrator async loop receives request
    |
    +-- Initialize session:
    |     +-- Initialize session_id in state dict if absent
    |     +-- Set session_active = True
    |
    +-- Build system prompt (dynamic):
    |     +-- Inject agent registry (name + description for each)
    |     +-- Inject current active_agent from session state
    |     +-- System prompt: delegation-focused, tool-reliant
    |
    +-- LLM reasoning via llm_provider.acomplete():
    |     +-- Decides: list_remote_agents? send_task? respond?
    |
    +-- [if list_remote_agents]:
    |     +-- Returns cached AgentCardEntry list (sync, no network)
    |
    +-- [if send_task(agent_name, message)]:
    |     +-- Validate agent_name exists in registry
    |     +-- Build TaskSendParams with session metadata
    |     +-- Check card.capabilities.streaming:
    |     |     +-- [streaming]: a2a_client.send_task_streaming
    |     |     |     +-- Process SSE events, propagate metadata
    |     |     |     +-- Invoke task_callback per event (if provided)
    |     |     |     +-- Break on final=True
    |     |     +-- [non-streaming]: a2a_client.send_task
    |     |           +-- Single response, propagate metadata
    |     |           +-- Invoke task_callback (if provided)
    |     +-- Update session state dict (session_active, agent, task_id)
    |     +-- Handle terminal states:
    |     |     +-- INPUT_REQUIRED: break loop, escalate to caller
    |     |     +-- CANCELED: raise ToolExecutionError
    |     |     +-- FAILED: raise ToolExecutionError
    |     |     +-- COMPLETED: session_active=False
    |     +-- Convert response parts:
    |           +-- TextPart -> str
    |           +-- DataPart -> dict
    |           +-- FilePart -> decode base64, store artifact, return DataPart ref
    |
    +-- LLM observes result (next loop iteration via llm_provider):
    |     +-- Decides: delegate more? respond to user?
    |     +-- [loop back to reasoning if more agents needed]
    |
    +-- Respond to user (or escalate for HITL)
```

### Session State Schema

```python
class OrchestratorSessionState(TypedDict, total=False):
    session_id: str            # UUID, created on first interaction
    session_active: bool       # True while delegation is in progress
    agent: str                 # Name of the currently active remote agent
    task_id: str               # Current A2A task ID
    input_message_metadata: dict[str, Any]  # Propagated from incoming request
```

All keys are optional (`total=False`). The orchestrator loop initializes `session_id` and `session_active` if absent on entry. `agent` and `task_id` are set by `send_task`. `input_message_metadata` is set by the caller (e.g., `agui_server` or `a2a_server`). State is stored in `dict[str, OrchestratorSessionState]` keyed by `session_id`.

### Module Structure

```
synapticore/agents/host_orchestrator.py
    OrchestratorConfig (Pydantic BaseModel)
    AgentCardEntry (Pydantic BaseModel)
    OrchestratorSessionState (TypedDict)

    _DEFAULT_MAX_ITERATIONS = 20
    _DEFAULT_ACCEPTED_OUTPUT_MODES = ["text", "text/plain", "image/png"]

    class _HostOrchestrator:
        __init__(config, card_registry, clients, llm_provider)
        _build_system_prompt(session_state: dict) -> str
        _init_session(session_id: str) -> None
        list_remote_agents() -> list[dict[str, str]]
        send_task(agent_name: str, message: str, session_id: str) -> list[str | dict]
        run(messages: list[ConversationMessage], session_id: str) -> ConversationMessage
        _check_state(session_id: str) -> dict[str, str]
        _build_task_params(agent_name: str, message: str, state: dict) -> TaskSendParams
        _handle_streaming(client: A2AClient, request: TaskSendParams) -> Task
        _handle_request_response(client: A2AClient, request: TaskSendParams) -> Task
        _convert_parts(parts: list[Part]) -> list[str | dict]
        _convert_part(part: Part) -> str | dict
        _merge_metadata(target: Any, source: Any) -> None

    _sessions: dict[str, OrchestratorSessionState]  # module-level in-memory state

    create_host_orchestrator(config: OrchestratorConfig, llm_provider: LlmProvider) -> HostOrchestrator
    register_host_orchestrator(config: OrchestratorConfig, llm_provider: LlmProvider, agui_wiring: Callable) -> None
```

### Class: `_HostOrchestrator`

Private class encapsulating the orchestrator's tools and state. Not exposed publicly -- consumers use `create_host_orchestrator` which returns a `HostOrchestrator` wrapping this instance's methods.

| Method | Input | Output | Behavior |
|--------|-------|--------|----------|
| `__init__` | `config: OrchestratorConfig`, `card_registry: dict[str, AgentCardEntry]`, `clients: dict[str, A2AClient]`, `llm_provider: LlmProvider` | `None` | Stores config, card registry, client map, and llm_provider reference. Precomputes the `agents` info string (JSON-serialized list of agent name+description) for prompt injection. |
| `_build_system_prompt` | `session_state: dict` | `str` | Dynamic system prompt. Injects the agent registry info and current active agent from session state. Instructs the LLM to delegate via tools, never fabricate responses. |
| `_init_session` | `session_id: str` | `None` | Initializes `session_id` entry in `_sessions` dict with `session_active=True` if not already present. Called at the start of each `run` invocation. |
| `list_remote_agents` | (none) | `list[dict[str, str]]` | Returns `[{"name": ..., "description": ...}, ...]` from the cached card registry. Synchronous, no network call. |
| `send_task` | `agent_name: str`, `message: str`, `session_id: str` | `list[str \| dict]` | Async. Validates agent exists, builds `TaskSendParams`, dispatches streaming or non-streaming, handles terminal states, converts response parts. Updates `_sessions[session_id]`. See orchestration loop above. |
| `run` | `messages: list[ConversationMessage]`, `session_id: str` | `ConversationMessage` | Async. The main orchestration loop. Calls `llm_provider.acomplete()` with tool definitions for `list_remote_agents` and `send_task`, processes tool calls, loops until LLM responds without tool calls or `max_iterations` reached. |
| `_check_state` | `session_id: str` | `dict[str, str]` | Reads `session_active`, `agent` from `_sessions[session_id]`. Returns `{"active_agent": "<name>"}` or `{"active_agent": "None"}`. |
| `_build_task_params` | `agent_name: str`, `message: str`, `state: dict` | `TaskSendParams` | Constructs A2A `TaskSendParams` with session metadata, message metadata propagation, and accepted output modes from config. |
| `_handle_streaming` | `client: A2AClient`, `request: TaskSendParams` | `Task` | Iterates `a2a_client.send_task_streaming`, merges metadata per event, invokes task callback, breaks on `final=True`. Returns the final `Task`. |
| `_handle_request_response` | `client: A2AClient`, `request: TaskSendParams` | `Task` | Calls `a2a_client.send_task`, merges metadata, invokes task callback. Returns the response `Task`. |
| `_convert_parts` | `parts: list[Part]` | `list[str \| dict]` | Maps each `Part` through `_convert_part`. |
| `_convert_part` | `part: Part` | `str \| dict` | `TextPart` -> `str`, `DataPart` -> `dict`, `FilePart` -> decode base64, store in session state, return `DataPart` reference. Unknown types return `"Unknown type: {type}"`. |
| `_merge_metadata` | `target: Any`, `source: Any` | `None` | Merges `source.metadata` into `target.metadata`. If target has metadata, update in-place. If target lacks metadata but source has it, copy. Null-safe. |

### Factory: `create_host_orchestrator`

```
OrchestratorConfig + LlmProvider
    |
    +-- For each url in remote_agent_urls:
    |     +-- a2a_card_resolver.get_agent_card(url) -> AgentCard
    |     +-- Build AgentCardEntry from AgentCard
    |     +-- Build A2AClient from AgentCard
    |     +-- Store in card_registry and clients dicts
    |     +-- [on failure: log warning, skip this agent]
    |
    +-- If card_registry is empty:
    |     +-- Raise ConfigurationError("No remote agents resolved")
    |
    +-- Construct _HostOrchestrator(config, card_registry, clients, llm_provider)
    |
    +-- Return HostOrchestrator wrapping the _HostOrchestrator instance
    |     (exposes run() and stream() methods, uses llm_provider for reasoning)
```

### Prompt Template (root_instruction)

The dynamic prompt follows this structure:

```
You are an expert delegator that routes user requests to the appropriate remote agents.

Discovery:
- Use `list_remote_agents` to see available agents and their capabilities.

Execution:
- Use `send_task` to assign tasks to remote agents by name.
- Include the remote agent name in your response to the user.
- If the active agent is set, send follow-up requests to that agent.

Rules:
- Rely on tools to address requests. Do not fabricate responses.
- If unsure, ask the user for clarification.
- Focus on the most recent parts of the conversation.

Agents:
{json-serialized agent registry}

Current agent: {active_agent from session state}
```

## Dependencies

### Internal
- `types/a2a_types` -- `AgentCard`, `AgentCapabilities`, `AgentSkill`, `Task`, `TaskState`, `TaskStatus`, `TaskSendParams`, `Message`, `TextPart`, `FilePart`, `DataPart`, `Part`, `Artifact`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `SendTaskStreamingResponse`, `A2AClientHTTPError`, `A2AClientJSONError`
- `types/common_types` -- `LlmConfig`, `ConversationMessage`, `ConfigurationError`, `ToolExecutionError`
- `protocols/a2a_client` -- `A2AClient` (async HTTP client for remote task delegation)
- `protocols/a2a_card_resolver` -- `A2ACardResolver` (fetches `AgentCard` from remote endpoints)
- `tools/llm_provider` -- `LlmProvider` / `acomplete()` (LLM reasoning for agent selection and delegation decisions)

### External
- `pydantic` (BaseModel, Field -- for `OrchestratorConfig`, `AgentCardEntry`)
- `typing` (Any, Callable, TypedDict)
- `uuid` (session/task/message ID generation)
- `json` (agent info serialization)
- `base64` (FilePart decoding)
- `logging` (structured logging)

## Error Contracts

### Raised by this module

| Condition | Error Type | Details | Trigger |
|-----------|-----------|---------|---------|
| No remote agents resolved at startup | `ConfigurationError` | `config_key="remote_agent_urls"`, message: `"No remote agents could be resolved from the provided URLs"` | `create_host_orchestrator` -- all `get_agent_card` calls failed |
| Agent name not in registry | `ToolExecutionError` | `tool_name="send_task"`, `original_error="Agent '{name}' not found"` | `send_task` -- `agent_name` not in `card_registry` |
| Remote agent task cancelled | `ToolExecutionError` | `tool_name="send_task"`, `original_error="Agent '{name}' task {task_id} was cancelled"` | `send_task` -- response `TaskState.CANCELED` |
| Remote agent task failed | `ToolExecutionError` | `tool_name="send_task"`, `original_error="Agent '{name}' task {task_id} failed"` | `send_task` -- response `TaskState.FAILED` |

### Propagated from dependencies

| Source | Error Type | When |
|--------|-----------|------|
| `a2a_card_resolver` | `A2AClientHTTPError`, `A2AClientJSONError` | Agent card resolution at startup (caught, logged, agent skipped) |
| `a2a_client` | `A2AClientHTTPError` | Remote agent unreachable during `send_task` (surfaces to orchestrator LLM as tool error) |
| `a2a_client` | `A2AClientJSONError` | Malformed response from remote agent (surfaces to orchestrator LLM as tool error) |

### Escalation (not an error)

| Condition | Orchestrator Action | AG-UI Effect |
|-----------|-----------|--------------|
| Remote agent returns `TaskState.INPUT_REQUIRED` | Orchestrator returns escalation signal to caller | `agui_server` translates escalation into AG-UI events prompting user input |

### Protocol mapping
- `ConfigurationError` and `ToolExecutionError` are mapped to protocol-specific errors by the protocol layers (see `common-types.md` Error-to-Protocol Mapping Guide).

## Test Plan

### Unit tests (`tests/unit/agents/test_host_orchestrator.py`)

All unit tests mock `A2AClient`, `A2ACardResolver`, and `llm_provider`. No network calls.

**OrchestratorConfig:**
- Constructs with `remote_agent_urls` only (all defaults)
- Constructs with all fields specified
- `max_iterations` defaults to 20
- `accepted_output_modes` defaults to `["text", "text/plain", "image/png"]`
- `llm_config` is optional and defaults to None

**AgentCardEntry:**
- Constructs from an `AgentCard` with name, description, skills, capabilities, url
- Serialization round-trip via `model_dump()` -> `model_validate()`

**create_host_orchestrator -- happy path:**
- Resolves all provided URLs to `AgentCard` instances
- Returns a `HostOrchestrator` instance
- Orchestrator exposes exactly 2 internal tools to the LLM: `list_remote_agents` and `send_task`
- LLM config matches `llm_config.model_slug` when provided
- LLM config uses default from `llm_provider` when `llm_config` is None

**create_host_orchestrator -- partial resolution:**
- 3 URLs provided, 1 fails to resolve -> returns Agent with 2 agents in registry, logs warning for failed URL
- Agent card entries match the 2 successful resolutions

**create_host_orchestrator -- total failure:**
- All URLs fail to resolve -> raises `ConfigurationError` with `config_key="remote_agent_urls"`

**list_remote_agents:**
- Returns list of `{"name": ..., "description": ...}` dicts for all registered agents
- Returns empty list when no agents registered (should not happen in practice -- guarded by factory)
- Does not make network calls

**send_task -- non-streaming happy path:**
- Mocked remote agent returns `TaskState.COMPLETED` with `TextPart` in status message
- Returns `["response text"]`
- Session state updated: `agent` set, `session_active` set to False (completed)

**send_task -- streaming happy path:**
- Mocked remote agent card has `capabilities.streaming = True`
- Mocked `send_task_streaming` yields 3 events, last with `final=True`
- Returns parts from final task
- Session state updated correctly

**send_task -- input_required:**
- Remote agent returns `TaskState.INPUT_REQUIRED`
- Orchestrator returns escalation signal to caller
- Session state: `session_active` remains True

**send_task -- agent not found:**
- `agent_name` not in registry -> raises `ToolExecutionError` with `tool_name="send_task"`

**send_task -- remote task cancelled:**
- Remote agent returns `TaskState.CANCELED` -> raises `ToolExecutionError`

**send_task -- remote task failed:**
- Remote agent returns `TaskState.FAILED` -> raises `ToolExecutionError`

**send_task -- with artifacts:**
- Remote agent returns task with `artifacts` containing `TextPart` and `DataPart`
- All parts extracted and returned

**send_task -- FilePart conversion:**
- Remote agent returns `FilePart` with base64-encoded bytes
- Decoded bytes stored in session state as artifact
- Returns `DataPart` with `{"artifact-file-id": file_id}`

**send_task -- metadata propagation:**
- `input_message_metadata` in state with `message_id` and custom fields
- `TaskSendParams.message.metadata` contains propagated fields
- Response metadata merged back into task

**_build_system_prompt:**
- Contains all registered agent names and descriptions
- Contains current active agent from session state
- When no active agent, shows `"None"`
- Dynamic -- changes based on session state

**_init_session:**
- First call for a session_id: creates entry in `_sessions` dict with `session_active = True`
- Subsequent calls: does not overwrite existing session state
- Always ensures `session_active` is True

**_check_state:**
- With active session: returns `{"active_agent": "<agent_name>"}`
- Without active session: returns `{"active_agent": "None"}`
- Missing state keys: returns `{"active_agent": "None"}`

**_merge_metadata:**
- Both target and source have metadata -> target metadata updated with source fields
- Target has no metadata, source does -> target gets copy of source metadata
- Source has no metadata -> target unchanged
- Neither has metadata -> no-op
- Target and source both None -> no-op

**_convert_part edge cases:**
- `TextPart` with empty string -> returns `""`
- `DataPart` with nested dict -> returns the dict as-is
- `FilePart` with `name=None` -> uses fallback file_id
- Unknown part type -> returns `"Unknown type: {type}"`

**Serialization round-trip:**
- `OrchestratorConfig`: `model_dump()` -> `model_validate()` preserves all fields
- `AgentCardEntry`: `model_dump()` -> `model_validate()` preserves all fields

**register_host_orchestrator:**
- Calls `create_host_orchestrator` and passes result through `agui_wiring` callback
- `agui_wiring` receives a callable agent executor

### Integration tests (`tests/integration/agents/test_host_orchestrator_integration.py`)

**End-to-end delegation (requires test A2A server):**
- Start a local A2A server with a mock agent that echoes messages
- `create_host_orchestrator` with the local server URL and mock `llm_provider`
- Invoke the orchestrator with a user message
- Verify the message is delegated to the mock agent and the response is returned

**Multi-agent delegation:**
- Start 2 local A2A servers with different agent cards (different skills)
- Orchestrator selects the correct agent based on the user request
- Both agents' responses are aggregated

**HITL escalation round-trip:**
- Mock agent returns `TaskState.INPUT_REQUIRED`
- Verify orchestrator escalation signal is returned to caller
- Simulate user input, verify follow-up delegation to same agent

## ADR References

- None pending. Plain Python async loop with `a2a_client` + `llm_provider` is the committed orchestration approach. No external framework required.

## Maturity

All functions: `stub` (rewrite target)
