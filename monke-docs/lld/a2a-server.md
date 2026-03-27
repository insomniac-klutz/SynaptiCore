# LLD: a2a_server

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.1
> Status: stub (rewrite -- not yet implemented)

## Responsibility

A2A JSON-RPC server. Starlette sub-app mounted at `/a2a/` by `app_server`. Accepts POST requests containing JSON-RPC 2.0 payloads, validates them via the `A2ARequest` discriminated union, dispatches to the appropriate `TaskManager` method, and returns JSON or SSE responses. Serves the agent card at `/.well-known/agent.json` via GET.

## Public API

### `A2AServer`

| Method / Attribute | Signature | Notes |
|--------------------|-----------|-------|
| `__init__` | `(agent_card: AgentCard, task_manager: TaskManager)` | Constructs the Starlette sub-app. No host/port -- mounting is `app_server`'s concern. |
| `app` | `Starlette` | The sub-app instance. `app_server` mounts this at `/a2a/`. |

No other public methods. All HTTP handling is internal to the Starlette route handlers.

### HTTP Endpoints (registered on `self.app`)

| Method | Path | Handler | Request Body | Response |
|--------|------|---------|-------------|----------|
| `GET` | `/.well-known/agent.json` | `_get_agent_card` | -- | `JSONResponse` containing `AgentCard` (serialized with `exclude_none=True`) |
| `POST` | `/` | `_process_request` | JSON-RPC 2.0 body (validated as `A2ARequest`) | `JSONResponse` (for non-streaming) or `EventSourceResponse` (for streaming methods) |

## Internal Design

### Request Processing Pipeline

```
HTTP POST /a2a/
    │
    ▼
┌─ Parse JSON body ──────────────────────────────────────┐
│  Failure → JSONParseError (-32700), HTTP 400            │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Validate via A2ARequest.validate_python(body) ────────┐
│  Failure → InvalidRequestError (-32600), HTTP 400       │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Dispatch to TaskManager method (isinstance chain) ────┐
│  GetTaskRequest       → task_manager.on_get_task        │
│  SendTaskRequest      → task_manager.on_send_task       │
│  SendTaskStreamingReq → task_manager.on_send_task_sub   │
│  CancelTaskRequest    → task_manager.on_cancel_task     │
│  SetTaskPushNotifReq  → task_manager.on_set_task_push.. │
│  GetTaskPushNotifReq  → task_manager.on_get_task_push.. │
│  TaskResubscriptionReq→ task_manager.on_resubscribe..   │
│  Unknown type         → MethodNotFoundError (-32601)    │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Create response from TaskManager result ──────────────┐
│  AsyncIterable → EventSourceResponse (SSE stream)       │
│  JSONRPCResponse → JSONResponse (single JSON body)      │
│  Other → InternalError (-32603), HTTP 500               │
└─────────────────────────────────────────────────────────┘
```

### Method Dispatch Table

| `isinstance` Match | TaskManager Method | Returns | Response Format |
|----|-----|---------|-----------------|
| `GetTaskRequest` | `on_get_task(request)` | `GetTaskResponse` | JSON |
| `SendTaskRequest` | `on_send_task(request)` | `SendTaskResponse` | JSON |
| `SendTaskStreamingRequest` | `on_send_task_subscribe(request)` | `AsyncIterable[SendTaskStreamingResponse]` or `JSONRPCResponse` (on error) | SSE or JSON |
| `CancelTaskRequest` | `on_cancel_task(request)` | `CancelTaskResponse` | JSON |
| `SetTaskPushNotificationRequest` | `on_set_task_push_notification(request)` | `SetTaskPushNotificationResponse` | JSON |
| `GetTaskPushNotificationRequest` | `on_get_task_push_notification(request)` | `GetTaskPushNotificationResponse` | JSON |
| `TaskResubscriptionRequest` | `on_resubscribe_to_task(request)` | `AsyncIterable[SendTaskStreamingResponse]` or `JSONRPCResponse` | SSE or JSON |

### SSE Streaming

When `TaskManager` returns an `AsyncIterable`, the server wraps it in an `EventSourceResponse`:

```python
async def _event_generator(result: AsyncIterable) -> AsyncIterable[dict[str, str]]:
    async for item in result:
        yield {"data": item.model_dump_json(exclude_none=True)}
```

Each SSE event is a `SendTaskStreamingResponse` serialized to JSON. The stream ends when the `TaskManager` yields a `TaskStatusUpdateEvent` with `final=True` or a `JSONRPCError`.

### Error Handling

Three exception catch points in `_handle_exception`:

| Exception Type | JSON-RPC Error | HTTP Status | Notes |
|---------------|----------------|-------------|-------|
| `json.JSONDecodeError` | `JSONParseError` (code -32700) | 400 | Malformed JSON body |
| `pydantic.ValidationError` | `InvalidRequestError` (code -32600) | 400 | Body doesn't match any `A2ARequest` variant. Pydantic error details attached in `data` field. |
| Any other `Exception` | `InternalError` (code -32603) | 400 | Catch-all. Logged at ERROR level. |

Error responses always use `JSONRPCResponse(id=None, error=<json_rpc_error>)` with `exclude_none=True` serialization.

### Internal Error → JSON-RPC Error Mapping

When `TaskManager` raises internal `SynaptiCoreError` subtypes (from `common_types`), the server maps them to JSON-RPC error codes per the project-wide error mapping table:

| Internal Error | JSON-RPC Error | Code |
|---------------|----------------|------|
| `SynaptiCoreError` (base) | `InternalError` | -32603 |
| `ProviderError` | `InternalError` | -32603 |
| `ConfigurationError` | `InternalError` | -32603 |
| `ToolExecutionError` | `InternalError` | -32603 |
| `ToolNotFoundError` | `InvalidParamsError` | -32602 |
| `pydantic.ValidationError` | `InvalidRequestError` | -32600 |

`TaskManager` may also return domain-specific JSON-RPC errors directly in the response (e.g., `TaskNotFoundError`, `TaskNotCancelableError`, `PushNotificationNotSupportedError`). These are not exceptions -- they're encoded in `JSONRPCResponse.error` and pass through the response pipeline unchanged.

### Key Design Decisions

1. **Sub-app, not standalone server** -- The existing code creates its own `Starlette()` app with `host`/`port` and a `start()` method that calls `uvicorn.run`. The rewrite removes `host`, `port`, and `start()`. The server is a Starlette sub-app; `app_server` (C1.3.7) mounts it and controls the uvicorn lifecycle. This enables all three protocol servers (A2A, MCP, AG-UI) to share a single process and port.
2. **Constructor requires both `agent_card` and `task_manager`** -- No `None` defaults. The existing code allows `None` and checks at `start()` time, which delays failure. The rewrite fails fast at construction. `app_server` is responsible for wiring these dependencies before mounting.
3. **`isinstance` dispatch chain preserved** -- Pydantic discriminated unions guarantee the parsed type matches exactly one request variant. The `isinstance` chain maps each variant to its `TaskManager` handler. An `else` branch returns `MethodNotFoundError` as a safety net (should be unreachable if `A2ARequest` union is exhaustive).
4. **Agent card path** -- Served at `/.well-known/agent.json` relative to the sub-app mount. When mounted at `/a2a/`, the full path becomes `/a2a/.well-known/agent.json` as specified in the HLD.
5. **No CORS handling** -- Cross-origin concerns are handled by `app_server` middleware, not individual sub-apps.
6. **Logging** -- Uses `logging.getLogger(__name__)`. Unhandled exceptions logged at ERROR. Request type mismatches logged at WARNING. No request/response body logging (contains user data).
7. **`exclude_none=True` on all serialization** -- Matches A2A wire protocol convention. Absent optional fields are omitted, not sent as `null`.

### Module Structure

```
synapticore/protocols/a2a_server.py
    A2AServer
        __init__(agent_card, task_manager)
        app: Starlette
        _get_agent_card(request) -> JSONResponse
        _process_request(request) -> JSONResponse | EventSourceResponse
        _handle_exception(e) -> JSONResponse
        _create_response(result) -> JSONResponse | EventSourceResponse
```

### Preservation from Existing `server.py`

The existing file at `Core/a2aPro/core/server.py` is ~118 lines and implements the full request pipeline. The rewrite preserves:

**Preserved as-is (patterns worth keeping):**
- `A2ARequest.validate_python(body)` for discriminated union parsing
- `isinstance` dispatch chain mapping request types to `TaskManager` methods
- Three-tier exception handling: `JSONDecodeError` → `JSONParseError`, `ValidationError` → `InvalidRequestError`, catch-all → `InternalError`
- `EventSourceResponse` wrapping `AsyncIterable` results with `model_dump_json(exclude_none=True)` per SSE event
- `JSONResponse` with `model_dump(exclude_none=True)` for non-streaming results
- Separation of `_handle_exception`, `_create_response`, and `_process_request`

**Cleanup in rewrite:**
- Remove `host`, `port`, `endpoint` constructor params -- sub-app, not standalone
- Remove `start()` method -- `app_server` owns the uvicorn lifecycle
- Remove `None` defaults for `agent_card` and `task_manager` -- required at construction
- Route paths become `/` (POST) and `/.well-known/agent.json` (GET) relative to mount point, not parameterized via `endpoint`
- Add `MethodNotFoundError` response for the `else` branch (existing code raises `ValueError`, which falls through to `InternalError`)
- Map `SynaptiCoreError` subtypes to JSON-RPC errors (existing code only handles `json.JSONDecodeError`, `ValidationError`, and generic `Exception`)
- Add type hints on all methods
- Import from `synapticore.types.a2a_types` instead of relative `..utils.common_types`
- Import `TaskManager` from `synapticore.protocols.a2a_task_manager` instead of relative `..utils.task_manager`
- Add `__all__ = ["A2AServer"]` export

## Dependencies

### Internal
- `types/a2a_types` -- `A2ARequest` (TypeAdapter), `AgentCard`, `JSONRPCResponse`, all JSON-RPC request types (`GetTaskRequest`, `SendTaskRequest`, `SendTaskStreamingRequest`, `CancelTaskRequest`, `SetTaskPushNotificationRequest`, `GetTaskPushNotificationRequest`, `TaskResubscriptionRequest`), error models (`JSONParseError`, `InvalidRequestError`, `InternalError`, `MethodNotFoundError`, `InvalidParamsError`)
- `types/common_types` -- `SynaptiCoreError`, `ToolNotFoundError` (for error mapping from `TaskManager` exceptions)
- `protocols/a2a_task_manager` -- `TaskManager` (abstract base class, injected at construction)

### External
- `starlette` (`Starlette`, `Request`, `JSONResponse`)
- `sse-starlette` (`EventSourceResponse`)
- `pydantic` (`ValidationError` -- caught in error handler)
- `json` (stdlib -- `JSONDecodeError` caught in error handler)
- `logging` (stdlib)
- `typing` (`AsyncIterable`, `Any`)

## Error Contracts

### Errors produced by this module (JSON-RPC error responses -- serialized, not raised)

| Condition | JSON-RPC Error | Code | HTTP Status |
|-----------|---------------|------|-------------|
| Malformed JSON body | `JSONParseError` | -32700 | 400 |
| Body fails `A2ARequest` validation | `InvalidRequestError` | -32600 | 400 |
| Parsed request type not in dispatch table | `MethodNotFoundError` | -32601 | 400 |
| `ToolNotFoundError` from `TaskManager` | `InvalidParamsError` | -32602 | 400 |
| `SynaptiCoreError` from `TaskManager` | `InternalError` | -32603 | 400 |
| Unexpected `TaskManager` result type | `InternalError` | -32603 | 500 |
| Any unhandled exception | `InternalError` | -32603 | 400 |

### Errors consumed (from `TaskManager` -- passed through in `JSONRPCResponse.error`)
- `TaskNotFoundError` (code -32001)
- `TaskNotCancelableError` (code -32002)
- `PushNotificationNotSupportedError` (code -32003)
- `UnsupportedOperationError` (code -32004)
- `ContentTypeNotSupportedError` (code -32005)

These are not exceptions. They are `JSONRPCError` Pydantic models returned inside `JSONRPCResponse` by `TaskManager` methods. The server serializes them to the client unchanged.

## Test Plan

### Unit tests (`tests/unit/protocols/test_a2a_server.py`)

**Construction:**
- `A2AServer(agent_card, task_manager)` creates a Starlette app with two routes
- `A2AServer` requires both `agent_card` and `task_manager` (no `None` defaults)

**Agent card endpoint:**
- GET `/.well-known/agent.json` returns 200 with `AgentCard` JSON body
- Response body matches `agent_card.model_dump(exclude_none=True)`
- Optional fields absent in `AgentCard` are not present in response (not `null`)

**Request dispatch (using Starlette `TestClient`):**
- POST `/` with `SendTaskRequest` body dispatches to `task_manager.on_send_task`
- POST `/` with `GetTaskRequest` body dispatches to `task_manager.on_get_task`
- POST `/` with `CancelTaskRequest` body dispatches to `task_manager.on_cancel_task`
- POST `/` with `SendTaskStreamingRequest` body dispatches to `task_manager.on_send_task_subscribe`
- POST `/` with `SetTaskPushNotificationRequest` body dispatches to `task_manager.on_set_task_push_notification`
- POST `/` with `GetTaskPushNotificationRequest` body dispatches to `task_manager.on_get_task_push_notification`
- POST `/` with `TaskResubscriptionRequest` body dispatches to `task_manager.on_resubscribe_to_task`
- Each dispatch test verifies the correct `TaskManager` method is called with the parsed request object

**JSON response:**
- `TaskManager` returning `JSONRPCResponse` produces `JSONResponse` with matching body
- Response body uses `exclude_none=True` serialization

**SSE streaming response:**
- `TaskManager` returning `AsyncIterable[SendTaskStreamingResponse]` produces `EventSourceResponse`
- Each yielded item is serialized as SSE `data:` line via `model_dump_json(exclude_none=True)`
- Stream ends after `TaskStatusUpdateEvent` with `final=True`
- Stream ends after `JSONRPCError` in response

**Error handling -- JSON parse:**
- POST `/` with non-JSON body returns 400 with `JSONParseError` (code -32700)
- Response `id` is `None`

**Error handling -- validation:**
- POST `/` with valid JSON but invalid JSON-RPC structure returns 400 with `InvalidRequestError` (code -32600)
- Pydantic error details are included in `error.data`
- Response `id` is `None`

**Error handling -- internal:**
- `TaskManager` method raising generic `Exception` returns `InternalError` (code -32603)
- Exception is logged at ERROR level

**Error mapping -- SynaptiCoreError subtypes:**
- `TaskManager` raising `SynaptiCoreError` maps to `InternalError` (code -32603)
- `TaskManager` raising `ToolNotFoundError` maps to `InvalidParamsError` (code -32602)

**Error passthrough:**
- `TaskManager` returning `JSONRPCResponse` with `TaskNotFoundError` in `error` field passes through unchanged
- `TaskManager` returning `JSONRPCResponse` with `PushNotificationNotSupportedError` passes through unchanged

**Edge cases:**
- POST with empty body (`b""`) returns `JSONParseError`
- POST with `Content-Type: text/plain` and valid JSON -- Starlette parses body regardless of content type
- Concurrent POST requests -- no shared mutable state in server (all state is in `TaskManager`)
- `TaskManager.on_send_task_subscribe` returning `JSONRPCResponse` (error case) instead of `AsyncIterable` -- server returns `JSONResponse`, not `EventSourceResponse`

## ADR References

- None pending. Starlette and sse-starlette are committed frameworks per HLD.

## Maturity

All functions: `stub` (rewrite target)
