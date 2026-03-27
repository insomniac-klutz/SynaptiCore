# LLD: agui_types

> Container: C1 (synapticore-core) | Subpackage: types/
> HLD Reference: S3 C1.1.2
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Pydantic models for AG-UI protocol events -- run lifecycle, text streaming, tool calls, state sync, human-in-the-loop.

## Public API

### Enums

| Name | Base | Values |
|------|------|--------|
| `AgUiEventType` | `str, Enum` | `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END`, `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `STATE_SNAPSHOT`, `STATE_DELTA`, `MESSAGES_SNAPSHOT`, `STEP_STARTED`, `STEP_FINISHED`, `CUSTOM`, `RAW` |
| `AgUiRole` | `str, Enum` | `USER`, `ASSISTANT`, `SYSTEM`, `TOOL` |
| `RunStatus` | `str, Enum` | `COMPLETED`, `ERROR`, `CANCELLED` |

### Run Lifecycle Events (3)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `RunStartedEvent` | `type: Literal["RUN_STARTED"]` | `thread_id: str`, `run_id: str` |
| `RunFinishedEvent` | `type: Literal["RUN_FINISHED"]` | `thread_id: str`, `run_id: str`, `status: RunStatus` |
| `RunErrorEvent` | `type: Literal["RUN_ERROR"]` | `thread_id: str`, `run_id: str`, `error_code: str`, `error_message: str` |

### Text Streaming Events (3)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `TextMessageStartEvent` | `type: Literal["TEXT_MESSAGE_START"]` | `message_id: str`, `role: AgUiRole` |
| `TextMessageContentEvent` | `type: Literal["TEXT_MESSAGE_CONTENT"]` | `message_id: str`, `delta: str` |
| `TextMessageEndEvent` | `type: Literal["TEXT_MESSAGE_END"]` | `message_id: str` |

### Tool Call Events (3)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `ToolCallStartEvent` | `type: Literal["TOOL_CALL_START"]` | `tool_call_id: str`, `tool_call_name: str`, `parent_message_id: str \| None` |
| `ToolCallArgsEvent` | `type: Literal["TOOL_CALL_ARGS"]` | `tool_call_id: str`, `delta: str` |
| `ToolCallEndEvent` | `type: Literal["TOOL_CALL_END"]` | `tool_call_id: str`, `result: str \| None` |

### State Synchronization Events (3)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `StateSnapshotEvent` | `type: Literal["STATE_SNAPSHOT"]` | `snapshot: dict[str, Any]` |
| `StateDeltaEvent` | `type: Literal["STATE_DELTA"]` | `delta: list[dict[str, Any]]` |
| `MessagesSnapshotEvent` | `type: Literal["MESSAGES_SNAPSHOT"]` | `messages: list[AgUiMessage]` |

### Step Events (2)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `StepStartedEvent` | `type: Literal["STEP_STARTED"]` | `step_name: str`, `step_id: str \| None` |
| `StepFinishedEvent` | `type: Literal["STEP_FINISHED"]` | `step_name: str`, `step_id: str \| None` |

### Extension Events (2)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `CustomEvent` | `type: Literal["CUSTOM"]` | `name: str`, `value: Any` |
| `RawEvent` | `type: Literal["RAW"]` | `data: str` |

### Discriminated Union

```python
AgUiEvent = Annotated[
    Union[
        RunStartedEvent,
        RunFinishedEvent,
        RunErrorEvent,
        TextMessageStartEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        ToolCallStartEvent,
        ToolCallArgsEvent,
        ToolCallEndEvent,
        StateSnapshotEvent,
        StateDeltaEvent,
        MessagesSnapshotEvent,
        StepStartedEvent,
        StepFinishedEvent,
        CustomEvent,
        RawEvent,
    ],
    Field(discriminator="type"),
]
```

### Supporting Models

| Class | Fields | Notes |
|-------|--------|-------|
| `AgUiMessage` | `id: str`, `role: AgUiRole`, `content: str`, `tool_calls: list[AgUiToolCall] \| None`, `tool_call_id: str \| None` | Message representation for snapshots and run config |
| `AgUiToolCall` | `id: str`, `name: str`, `arguments: str` | JSON-encoded arguments string |
| `AgUiRunConfig` | `agent_id: str`, `messages: list[AgUiMessage]`, `thread_id: str \| None`, `run_id: str \| None`, `context: dict[str, Any] \| None` | Input to POST `/agui/runs` |

## Internal Design

### Key Design Decisions

1. **16 event types** -- Follows the AG-UI protocol specification. Each event is a Pydantic model with a `type` literal discriminator. The `RawEvent` type provides an escape hatch for protocol extensions.
2. **Discriminated union on `type`** -- Same pattern as `a2a_types.Part`. Enables efficient SSE deserialization: parse `type` field first, then validate the correct model.
3. **`StateDeltaEvent` uses JSON Patch format** -- The `delta` field is `list[dict[str, Any]]` representing RFC 6902 JSON Patch operations (op, path, value). This is the AG-UI spec's prescribed format for incremental state updates.
4. **No SSE transport concerns** -- These are pure data models. SSE framing (`event:`, `data:`, `id:`) is handled by `agui_server` in the protocols layer.
5. **snake_case internally, camelCase on wire** -- AG-UI protocol uses camelCase on the wire. Pydantic aliases handle the translation. `model_config = ConfigDict(populate_by_name=True)` on base event class.
6. **All events share a base** -- An `AgUiBaseEvent` with `type: str` and optional `timestamp: datetime` provides a common base. The 16 concrete events narrow `type` to their respective literal.

### Module structure

```
synapticore/types/agui_types.py
    AgUiEventType (enum)
    AgUiRole (enum)
    RunStatus (enum)
    AgUiBaseEvent (base model)
    RunStartedEvent .. RawEvent (16 event models)
    AgUiEvent (discriminated union)
    AgUiMessage, AgUiToolCall, AgUiRunConfig (supporting models)
```

## Dependencies

### Internal
- None. This is a leaf module in `types/`.

### External
- `pydantic` (BaseModel, Field, ConfigDict)
- `typing` / `typing_extensions` (Literal, Union, Annotated, Any)
- `enum` (Enum)
- `datetime` (datetime, timezone) -- for optional event timestamps

## Error Contracts

### Defined by this module
- `RunErrorEvent` -- not a Python exception but an SSE event model. Carries `error_code` and `error_message` for protocol-level error signaling to the frontend.

### Raised implicitly
- `pydantic.ValidationError` on invalid event construction. The `agui_server` must catch these and emit a `RunErrorEvent` on the SSE stream.

### Not defined here
- HTTP 400/500 errors for malformed `AgUiRunConfig` requests are the responsibility of `agui_server`, not the types module.

## Test Plan

### Unit tests (`tests/unit/types/test_agui_types.py`)

**Model construction & validation:**
- Each of the 16 event types constructs from valid kwargs
- Required fields raise `ValidationError` when missing
- `AgUiEventType` enum covers all 16 values
- `AgUiRole` enum covers all 4 values
- `RunStatus` enum covers all 3 values
- `AgUiEvent` discriminated union resolves each event type from dict

**Serialization round-trip:**
- `model_dump()` -> `model_validate()` round-trip for every event type
- `model_dump(mode="json")` produces correct camelCase keys
- `StateDeltaEvent.delta` preserves JSON Patch operation structure
- `TextMessageContentEvent.delta` preserves arbitrary text content (including newlines, unicode)

**Supporting models:**
- `AgUiMessage` with and without tool calls
- `AgUiToolCall` with JSON-encoded arguments string
- `AgUiRunConfig` with minimal fields (agent_id + messages only)
- `AgUiRunConfig` with all optional fields populated

**Edge cases:**
- `CustomEvent` with various `value` types (str, dict, list, None)
- `RawEvent` with raw SSE data string
- `StateSnapshotEvent` with empty snapshot dict
- `MessagesSnapshotEvent` with empty messages list
- `ToolCallEndEvent` with None result (tool produced no output)

## ADR References

- None pending. AG-UI types are spec-driven with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
