# LLD: a2a_types

> Container: C1 (synapticore-core) | Subpackage: types/
> HLD Reference: S3 C1.1.1
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Pydantic models for A2A protocol -- task lifecycle, JSON-RPC messages, agent cards, protocol errors.

## Public API

### Enums

| Name | Base | Values |
|------|------|--------|
| `TaskState` | `str, Enum` | `SUBMITTED`, `WORKING`, `INPUT_REQUIRED`, `COMPLETED`, `CANCELED`, `FAILED`, `UNKNOWN` |

### Part Types (discriminated union on `type` field)

| Class | Discriminator | Fields |
|-------|---------------|--------|
| `TextPart` | `type: Literal["text"]` | `text: str`, `metadata: dict[str, Any] \| None` |
| `FilePart` | `type: Literal["file"]` | `file: FileContent`, `metadata: dict[str, Any] \| None` |
| `DataPart` | `type: Literal["data"]` | `data: dict[str, Any]`, `metadata: dict[str, Any] \| None` |

**Union alias:** `Part = Annotated[Union[TextPart, FilePart, DataPart], Field(discriminator="type")]`

### Supporting Models for Parts

| Class | Fields | Validators |
|-------|--------|------------|
| `FileContent` | `name: str \| None`, `mimeType: str \| None`, `bytes: str \| None`, `uri: str \| None` | `model_validator(mode="after")`: exactly one of `bytes` or `uri` must be present |

### Message & Task Models

| Class | Fields | Notes |
|-------|--------|-------|
| `Message` | `role: Literal["user", "agent"]`, `parts: list[Part]`, `metadata: dict[str, Any] \| None` | Core message envelope |
| `TaskStatus` | `state: TaskState`, `message: Message \| None`, `timestamp: datetime` | `field_serializer` on `timestamp` -> ISO format; `default_factory=datetime.now` |
| `Artifact` | `name: str \| None`, `description: str \| None`, `parts: list[Part]`, `metadata: dict[str, Any] \| None`, `index: int = 0`, `append: bool \| None`, `lastChunk: bool \| None` | Streaming artifact support |
| `Task` | `id: str`, `sessionId: str \| None`, `status: TaskStatus`, `artifacts: list[Artifact] \| None`, `history: list[Message] \| None`, `metadata: dict[str, Any] \| None` | Top-level task model |

### Event Models

| Class | Fields |
|-------|--------|
| `TaskStatusUpdateEvent` | `id: str`, `status: TaskStatus`, `final: bool = False`, `metadata: dict[str, Any] \| None` |
| `TaskArtifactUpdateEvent` | `id: str`, `artifact: Artifact`, `metadata: dict[str, Any] \| None` |

### Authentication & Push Notification

| Class | Fields | Notes |
|-------|--------|-------|
| `AuthenticationInfo` | `schemes: list[str]`, `credentials: str \| None` | `ConfigDict(extra="allow")` |
| `PushNotificationConfig` | `url: str`, `token: str \| None`, `authentication: AuthenticationInfo \| None` | |
| `TaskPushNotificationConfig` | `id: str`, `pushNotificationConfig: PushNotificationConfig` | |

### Request Parameter Models

| Class | Inherits | Fields |
|-------|----------|--------|
| `TaskIdParams` | `BaseModel` | `id: str`, `metadata: dict[str, Any] \| None` |
| `TaskQueryParams` | `TaskIdParams` | `historyLength: int \| None` |
| `TaskSendParams` | `BaseModel` | `id: str`, `sessionId: str` (default: `uuid4().hex`), `message: Message`, `acceptedOutputModes: list[str] \| None`, `pushNotification: PushNotificationConfig \| None`, `historyLength: int \| None`, `metadata: dict[str, Any] \| None` |

### JSON-RPC Base Models

| Class | Inherits | Fields |
|-------|----------|--------|
| `JSONRPCMessage` | `BaseModel` | `jsonrpc: Literal["2.0"]`, `id: int \| str \| None` (default: `uuid4().hex`) |
| `JSONRPCRequest` | `JSONRPCMessage` | `method: str`, `params: dict[str, Any] \| None` |
| `JSONRPCError` | `BaseModel` | `code: int`, `message: str`, `data: Any \| None` |
| `JSONRPCResponse` | `JSONRPCMessage` | `result: Any \| None`, `error: JSONRPCError \| None` |

### JSON-RPC Request/Response Pairs

| Request | Method Literal | Params Type | Response | Result Type |
|---------|---------------|-------------|----------|-------------|
| `SendTaskRequest` | `"tasks/send"` | `TaskSendParams` | `SendTaskResponse` | `Task \| None` |
| `SendTaskStreamingRequest` | `"tasks/sendSubscribe"` | `TaskSendParams` | `SendTaskStreamingResponse` | `TaskStatusUpdateEvent \| TaskArtifactUpdateEvent \| None` |
| `GetTaskRequest` | `"tasks/get"` | `TaskQueryParams` | `GetTaskResponse` | `Task \| None` |
| `CancelTaskRequest` | `"tasks/cancel"` | `TaskIdParams` | `CancelTaskResponse` | `Task \| None` |
| `SetTaskPushNotificationRequest` | `"tasks/pushNotification/set"` | `TaskPushNotificationConfig` | `SetTaskPushNotificationResponse` | `TaskPushNotificationConfig \| None` |
| `GetTaskPushNotificationRequest` | `"tasks/pushNotification/get"` | `TaskIdParams` | `GetTaskPushNotificationResponse` | `TaskPushNotificationConfig \| None` |
| `TaskResubscriptionRequest` | `"tasks/resubscribe"` | `TaskIdParams` | *(uses streaming response)* | -- |

### Discriminated Union

```python
A2ARequest = TypeAdapter(
    Annotated[
        Union[
            SendTaskRequest,
            GetTaskRequest,
            CancelTaskRequest,
            SetTaskPushNotificationRequest,
            GetTaskPushNotificationRequest,
            TaskResubscriptionRequest,
            SendTaskStreamingRequest,
        ],
        Field(discriminator="method"),
    ]
)
```

### JSON-RPC Error Types

| Class | Inherits | `code` | `message` default | `data` |
|-------|----------|--------|-------------------|--------|
| `JSONParseError` | `JSONRPCError` | `-32700` | `"Invalid JSON payload"` | `Any \| None` |
| `InvalidRequestError` | `JSONRPCError` | `-32600` | `"Request payload validation error"` | `Any \| None` |
| `MethodNotFoundError` | `JSONRPCError` | `-32601` | `"Method not found"` | `None` |
| `InvalidParamsError` | `JSONRPCError` | `-32602` | `"Invalid parameters"` | `Any \| None` |
| `InternalError` | `JSONRPCError` | `-32603` | `"Internal error"` | `Any \| None` |
| `TaskNotFoundError` | `JSONRPCError` | `-32001` | `"Task not found"` | `None` |
| `TaskNotCancelableError` | `JSONRPCError` | `-32002` | `"Task cannot be canceled"` | `None` |
| `PushNotificationNotSupportedError` | `JSONRPCError` | `-32003` | `"Push Notification is not supported"` | `None` |
| `UnsupportedOperationError` | `JSONRPCError` | `-32004` | `"This operation is not supported"` | `None` |
| `ContentTypeNotSupportedError` | `JSONRPCError` | `-32005` | `"Incompatible content types"` | `None` |

### Agent Card Models

| Class | Fields |
|-------|--------|
| `AgentProvider` | `organization: str`, `url: str \| None` |
| `AgentCapabilities` | `streaming: bool = False`, `pushNotifications: bool = False`, `stateTransitionHistory: bool = False` |
| `AgentAuthentication` | `schemes: list[str]`, `credentials: str \| None` |
| `AgentSkill` | `id: str`, `name: str`, `description: str \| None`, `tags: list[str] \| None`, `examples: list[str] \| None`, `inputModes: list[str] \| None`, `outputModes: list[str] \| None` |
| `AgentCard` | `name: str`, `description: str \| None`, `url: str`, `provider: AgentProvider \| None`, `version: str`, `documentationUrl: str \| None`, `capabilities: AgentCapabilities`, `authentication: AgentAuthentication \| None`, `defaultInputModes: list[str] = ["text"]`, `defaultOutputModes: list[str] = ["text"]`, `skills: list[AgentSkill]` |

### Exception Classes

| Class | Inherits | Fields |
|-------|----------|--------|
| `A2AClientError` | `Exception` | *(base exception)* |
| `A2AClientHTTPError` | `A2AClientError` | `status_code: int`, `message: str` |
| `A2AClientJSONError` | `A2AClientError` | `message: str` |

## Internal Design

### Preservation from existing `common_types.py`

The existing file at `Core/a2aPro/utils/common_types.py` contains 50+ models that are production-ready and closely follow the Google A2A spec. The rewrite preserves all models listed above with these changes:

**Preserved as-is (patterns worth keeping):**
- Discriminated union on `Part` via `Field(discriminator="type")`
- Discriminated union on `A2ARequest` via `TypeAdapter` + `Field(discriminator="method")`
- `model_validator(mode="after")` on `FileContent` for mutual exclusion of `bytes`/`uri`
- `field_serializer` on `TaskStatus.timestamp` for ISO 8601 output
- `uuid4().hex` defaults on `JSONRPCMessage.id` and `TaskSendParams.sessionId`
- `ConfigDict(extra="allow")` on `AuthenticationInfo`
- JSON-RPC error code hierarchy with sensible defaults
- All request/response pairs matching their method literals

**Cleanup in rewrite:**
- Move from `Core/a2aPro/utils/common_types.py` to `synapticore/types/a2a_types.py` (flat subpackage location per HLD)
- Remove `MissingAPIKeyError` -- this is not an A2A protocol concern; replaced by `ConfigurationError` in `common_types`
- Add `__all__` export list for explicit public API
- Add module-level docstring referencing the A2A protocol spec version
- Add `model_config = ConfigDict(populate_by_name=True)` where camelCase field aliases are needed for wire format compatibility (e.g., `sessionId`, `mimeType`, `lastChunk`, `historyLength`, `pushNotification`, `acceptedOutputModes`)
- Ensure all `datetime` fields use `datetime.now(tz=timezone.utc)` instead of naive `datetime.now()` for timezone safety
- Verify JSON-RPC error codes match latest A2A spec version

### Key Design Decisions

1. **camelCase field names preserved** -- A2A wire protocol uses camelCase (`sessionId`, `mimeType`). Pydantic `alias` or `populate_by_name` keeps Python-side access Pythonic while serializing to spec-compliant JSON.
2. **No runtime logic** -- Pure data models + validators. No HTTP, no I/O.
3. **Discriminated unions** -- Both `Part` (on `type`) and `A2ARequest` (on `method`) use Pydantic discriminated unions for efficient deserialization and clear error messages.
4. **Error hierarchy as Pydantic models** -- JSON-RPC errors are `BaseModel` subclasses (not exceptions) because they serialize to JSON-RPC error responses. Client-side exceptions (`A2AClientError` tree) are Python exceptions for `raise`/`except` flows.

## Dependencies

### Internal
- None. This is a leaf module in `types/`.

### External
- `pydantic` (BaseModel, Field, TypeAdapter, ConfigDict, model_validator, field_serializer)
- `typing` / `typing_extensions` (Literal, Union, Annotated, Optional, List, Any)
- `datetime` (datetime, timezone)
- `uuid` (uuid4)
- `enum` (Enum)

## Error Contracts

### Defined by this module (JSON-RPC error models -- serialized, not raised)
- `JSONParseError` (code -32700)
- `InvalidRequestError` (code -32600)
- `MethodNotFoundError` (code -32601)
- `InvalidParamsError` (code -32602)
- `InternalError` (code -32603)
- `TaskNotFoundError` (code -32001)
- `TaskNotCancelableError` (code -32002)
- `PushNotificationNotSupportedError` (code -32003)
- `UnsupportedOperationError` (code -32004)
- `ContentTypeNotSupportedError` (code -32005)

### Defined by this module (Python exceptions -- raised by client code)
- `A2AClientError` (base)
- `A2AClientHTTPError` (HTTP transport errors)
- `A2AClientJSONError` (JSON deserialization errors)

### Pydantic ValidationError
- Raised automatically by Pydantic on invalid model construction. Callers (protocol layer) must catch and map to `InvalidRequestError` for wire responses.

## Test Plan

### Unit tests (`tests/unit/types/test_a2a_types.py`)

**Model construction & validation:**
- Each model constructs from valid kwargs
- Required fields raise `ValidationError` when missing
- `FileContent` validator rejects both `bytes` and `uri` present, and neither present
- `TaskState` enum covers all 7 values
- `Part` discriminated union resolves `TextPart`, `FilePart`, `DataPart` from dict
- `A2ARequest` discriminated union resolves all 7 request types from dict

**Serialization round-trip:**
- `model_dump()` -> `model_validate()` round-trip for every model
- `model_dump(mode="json")` produces camelCase keys where aliased
- `TaskStatus.timestamp` serializes to ISO 8601 string
- `JSONRPCMessage.id` defaults to a hex UUID string
- `TaskSendParams.sessionId` defaults to a hex UUID string

**Error models:**
- Each JSON-RPC error has correct default `code` and `message`
- Error models serialize to valid JSON-RPC error objects
- `A2AClientHTTPError` formats status code in message
- `A2AClientJSONError` formats error detail in message

**Edge cases:**
- `Message` with empty `parts` list
- `Task` with `None` artifacts and `None` history
- `Artifact` with `append=True` and `lastChunk=True`
- `AgentCard` with minimal required fields only
- `AgentCard` with all optional fields populated

## ADR References

- None pending. A2A types are spec-driven with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
