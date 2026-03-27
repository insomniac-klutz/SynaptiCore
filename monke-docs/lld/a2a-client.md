# LLD: a2a_client

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.2
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Async HTTP client for sending tasks to remote A2A agents. Supports request-response (JSON-RPC POST) and SSE streaming modes via `httpx` + `httpx-sse`. All outbound A2A communication flows through this client. 30-second default timeout on request-response calls; no timeout on SSE streams.

## Public API

### Models

| Class | Fields | Notes |
|-------|--------|-------|
| `A2AClientConfig` | `url: str`, `timeout: float = 30.0`, `headers: dict[str, str] \| None = None` | Client configuration. `url` is the remote agent's A2A endpoint (e.g., `http://remote:8000/a2a/`). `timeout` is seconds for request-response calls. `headers` allows custom HTTP headers (auth tokens, tracing IDs). |

### Class: `A2AClient`

| Method | Signature | Notes |
|--------|-----------|-------|
| `__init__` | `(self, *, agent_card: AgentCard \| None = None, url: str \| None = None, timeout: float = 30.0, headers: dict[str, str] \| None = None) -> None` | Must provide either `agent_card` (extracts `agent_card.url`) or `url` directly. Raises `ValueError` if neither provided. Stores resolved URL, timeout, and optional headers. Does NOT create an `httpx.AsyncClient` -- that is created per-call or managed via context manager. |
| `send_task` | `async (self, params: TaskSendParams) -> SendTaskResponse` | Wraps params in `SendTaskRequest`, sends JSON-RPC POST, returns parsed `SendTaskResponse`. Raises `A2AClientHTTPError` on HTTP failures, `A2AClientJSONError` on response parse failures. |
| `send_task_streaming` | `async (self, params: TaskSendParams) -> AsyncIterator[SendTaskStreamingResponse]` | Wraps params in `SendTaskStreamingRequest`, opens SSE connection via `httpx-sse`. Yields `SendTaskStreamingResponse` for each SSE event. No timeout on the SSE stream. Raises `A2AClientHTTPError` on connection failure, `A2AClientJSONError` on event parse failure. |
| `get_task` | `async (self, params: TaskQueryParams) -> GetTaskResponse` | Wraps params in `GetTaskRequest`, sends JSON-RPC POST, returns parsed `GetTaskResponse`. |
| `cancel_task` | `async (self, params: TaskIdParams) -> CancelTaskResponse` | Wraps params in `CancelTaskRequest`, sends JSON-RPC POST, returns parsed `CancelTaskResponse`. |
| `set_push_notification` | `async (self, params: TaskPushNotificationConfig) -> SetTaskPushNotificationResponse` | Wraps params in `SetTaskPushNotificationRequest`, sends JSON-RPC POST, returns parsed `SetTaskPushNotificationResponse`. |
| `get_push_notification` | `async (self, params: TaskIdParams) -> GetTaskPushNotificationResponse` | Wraps params in `GetTaskPushNotificationRequest`, sends JSON-RPC POST, returns parsed `GetTaskPushNotificationResponse`. |

### Async Context Manager

| Method | Signature | Notes |
|--------|-----------|-------|
| `__aenter__` | `async (self) -> Self` | Creates a shared `httpx.AsyncClient` stored on `self._client`. Returns `self`. Enables connection pooling across multiple calls. |
| `__aexit__` | `async (self, *exc) -> None` | Closes the shared `httpx.AsyncClient`. |

When used without the context manager, each method creates and closes its own `httpx.AsyncClient`. When used as a context manager, all methods reuse the shared client for connection pooling.

## Internal Design

### Key Design Decisions

1. **Async-first, sync streaming replaced** -- The legacy client uses synchronous `httpx.Client` + `connect_sse` for streaming inside an `async` generator. The rewrite uses `httpx.AsyncClient` + `httpx_sse.aconnect_sse` for true async streaming. This eliminates the thread-blocking hazard in the legacy code and aligns with the async-everywhere architecture.

2. **Typed params, not raw dicts** -- The legacy client accepts `payload: dict[str, Any]` for all methods and constructs request objects internally. The rewrite accepts typed Pydantic params (`TaskSendParams`, `TaskQueryParams`, `TaskIdParams`, `TaskPushNotificationConfig`) directly. The caller constructs the domain object; the client wraps it in the JSON-RPC envelope. This moves validation to the call site and eliminates a class of runtime KeyError bugs.

3. **30-second default timeout on request-response** -- Preserved from legacy. Remote agents performing heavy work (e.g., image generation) need generous timeouts. The default is configurable per-client via `timeout` param. SSE streams use `timeout=None` (no timeout) since they are long-lived by design.

4. **Optional context manager for connection pooling** -- Creating a new `httpx.AsyncClient` per call is correct but wasteful for burst scenarios (e.g., sending multiple tasks to the same agent). The `async with A2AClient(...)` form enables connection reuse. Without the context manager, per-call client creation is the safe default -- no leaked connections.

5. **Custom exceptions, not httpx exceptions** -- All httpx exceptions are caught and re-raised as `A2AClientHTTPError` or `A2AClientJSONError`. Callers depend only on `a2a_types` exceptions, never on `httpx` internals. This insulates the rest of the codebase from transport library changes.

6. **No response validation beyond JSON parse** -- The client constructs response Pydantic models from the JSON-RPC response dict. If the remote agent returns malformed JSON-RPC, Pydantic's `ValidationError` will propagate. The client does NOT catch `ValidationError` -- that indicates a protocol violation by the remote agent and should surface to the caller. The client only catches transport-level failures (HTTP errors, JSON decode errors).

7. **No retry logic** -- Retries are the caller's responsibility. The client is a thin transport layer. Retry policies vary by use case (idempotent GETs vs. non-idempotent task sends) and should not be baked into the client.

8. **No agent card fetching** -- Agent card resolution is handled by `a2a_card_resolver` (C1.3.4), a separate component. The client accepts an already-resolved `AgentCard` or a raw URL. Separation of concerns: discovery vs. communication.

### Request Flow

```
caller
  │
  ├─ A2AClient.send_task(params: TaskSendParams)
  │     │
  │     ├─ Construct SendTaskRequest(params=params.model_dump())
  │     │     jsonrpc="2.0", id=uuid4().hex, method="tasks/send"
  │     │
  │     ├─ _send_request(request)
  │     │     │
  │     │     ├─ Get or create httpx.AsyncClient
  │     │     ├─ POST self.url, json=request.model_dump(), timeout=self.timeout
  │     │     ├─ response.raise_for_status()
  │     │     │     └─ HTTPStatusError → A2AClientHTTPError(status_code, message)
  │     │     ├─ response.json()
  │     │     │     └─ JSONDecodeError → A2AClientJSONError(message)
  │     │     └─ return dict
  │     │
  │     └─ SendTaskResponse(**response_dict)
  │           └─ ValidationError propagates (remote protocol violation)
  │
  └─ return SendTaskResponse
```

### SSE Streaming Flow

```
caller
  │
  ├─ async for response in client.send_task_streaming(params):
  │     │
  │     ├─ Construct SendTaskStreamingRequest(params=params.model_dump())
  │     │
  │     ├─ _send_streaming_request(request)
  │     │     │
  │     │     ├─ Get or create httpx.AsyncClient (timeout=None)
  │     │     ├─ aconnect_sse(client, "POST", self.url, json=request.model_dump())
  │     │     │     └─ httpx.RequestError → A2AClientHTTPError(0, message)
  │     │     ├─ response.raise_for_status()
  │     │     │     └─ HTTPStatusError → A2AClientHTTPError(status_code, message)
  │     │     ├─ async for sse in event_source.aiter_sse():
  │     │     │     ├─ json.loads(sse.data)
  │     │     │     │     └─ JSONDecodeError → A2AClientJSONError(message)
  │     │     │     └─ yield SendTaskStreamingResponse(**parsed)
  │     │     │           └─ ValidationError propagates (remote protocol violation)
  │     │     └─ (SSE connection closed on generator exit or exhaustion)
  │     │
  │     └─ yield SendTaskStreamingResponse
```

### Private Methods

| Method | Signature | Notes |
|--------|-----------|-------|
| `_send_request` | `async (self, request: JSONRPCRequest) -> dict[str, Any]` | Core request-response transport. Handles `httpx.AsyncClient` lifecycle, POST, status check, JSON decode. Returns raw response dict. |
| `_send_streaming_request` | `async (self, request: JSONRPCRequest) -> AsyncIterator[dict[str, Any]]` | Core SSE transport. Handles async SSE connection, iterates events, yields parsed JSON dicts. |
| `_get_client` | `(self) -> httpx.AsyncClient` | Returns the shared client if inside a context manager, otherwise creates a new one. Used by `_send_request` and `_send_streaming_request`. |

### Module Structure

```
synapticore/protocols/a2a_client.py
    A2AClientConfig (Pydantic BaseModel)

    class A2AClient:
        __init__(agent_card, url, timeout, headers)
        __aenter__() -> Self
        __aexit__(*exc) -> None

        async send_task(params) -> SendTaskResponse
        async send_task_streaming(params) -> AsyncIterator[SendTaskStreamingResponse]
        async get_task(params) -> GetTaskResponse
        async cancel_task(params) -> CancelTaskResponse
        async set_push_notification(params) -> SetTaskPushNotificationResponse
        async get_push_notification(params) -> GetTaskPushNotificationResponse

        async _send_request(request) -> dict
        async _send_streaming_request(request) -> AsyncIterator[dict]
        _get_client() -> httpx.AsyncClient
```

## Dependencies

### Internal
- `types/a2a_types` -- `AgentCard`, `TaskSendParams`, `TaskQueryParams`, `TaskIdParams`, `TaskPushNotificationConfig`, all JSON-RPC request/response types (`SendTaskRequest`, `SendTaskResponse`, `SendTaskStreamingRequest`, `SendTaskStreamingResponse`, `GetTaskRequest`, `GetTaskResponse`, `CancelTaskRequest`, `CancelTaskResponse`, `SetTaskPushNotificationRequest`, `SetTaskPushNotificationResponse`, `GetTaskPushNotificationRequest`, `GetTaskPushNotificationResponse`, `JSONRPCRequest`), exceptions (`A2AClientHTTPError`, `A2AClientJSONError`)

### External
- `httpx` (AsyncClient -- async HTTP transport)
- `httpx-sse` (aconnect_sse -- async SSE client)
- `json` (stdlib -- SSE event data parsing)
- `pydantic` (BaseModel -- for `A2AClientConfig`)
- `typing` (Any, AsyncIterator)
- `uuid` (uuid4 -- for JSON-RPC request IDs, though typically handled by the request model defaults)

## Error Contracts

### Raised by this module

| Exception | Condition | Details |
|-----------|-----------|---------|
| `ValueError` | Neither `agent_card` nor `url` provided to `__init__` | Standard Python ValueError. Raised at construction time. |
| `A2AClientHTTPError` | Remote agent returns non-2xx HTTP status | `status_code`: the HTTP status code from the response. `message`: stringified error detail from httpx. |
| `A2AClientHTTPError` | HTTP connection failure (DNS, timeout, connection refused) | `status_code`: `0` (no HTTP response received). `message`: stringified `httpx.RequestError`. |
| `A2AClientJSONError` | Response body is not valid JSON (request-response mode) | `message`: stringified `json.JSONDecodeError` detail. |
| `A2AClientJSONError` | SSE event `data` field is not valid JSON (streaming mode) | `message`: stringified `json.JSONDecodeError` detail. |

### Propagated (not caught)
- `pydantic.ValidationError` -- raised when constructing response models from the remote agent's JSON-RPC response. This indicates the remote agent violated the A2A protocol. The client intentionally does not catch this; callers decide how to handle protocol violations.

### Not raised by this module
- `A2AClientError` (base) -- never raised directly; only subclasses are raised.

## Test Plan

### Unit tests (`tests/unit/protocols/test_a2a_client.py`)

All tests use `httpx`'s built-in mock transport (`httpx.MockTransport`) or `respx` to stub HTTP responses. No real network calls.

**Construction:**
- Constructs with `agent_card` (extracts `.url`)
- Constructs with `url` string directly
- Constructs with both `agent_card` and `url` -- `agent_card.url` takes precedence
- Raises `ValueError` when neither `agent_card` nor `url` provided
- `timeout` defaults to 30.0
- Custom `timeout` is stored and used
- Custom `headers` are stored and sent with requests

**Context manager:**
- `async with A2AClient(url=...)` creates and closes `httpx.AsyncClient`
- Multiple calls within context manager reuse the same client
- Client is properly closed on context manager exit
- Client is properly closed on context manager exit after exception

**send_task -- success:**
- Sends `SendTaskRequest` as JSON-RPC POST to configured URL
- Request body contains `jsonrpc: "2.0"`, `method: "tasks/send"`, `id`, and `params`
- Returns `SendTaskResponse` parsed from response JSON
- Uses configured timeout for the POST request

**send_task -- errors:**
- Remote returns HTTP 400 -> `A2AClientHTTPError(status_code=400, ...)`
- Remote returns HTTP 500 -> `A2AClientHTTPError(status_code=500, ...)`
- Connection refused -> `A2AClientHTTPError(status_code=0, ...)`
- Timeout -> `A2AClientHTTPError(status_code=0, ...)`
- Response body is not JSON -> `A2AClientJSONError`
- Response JSON is valid but not a valid `SendTaskResponse` -> `pydantic.ValidationError` propagates

**send_task_streaming -- success:**
- Sends `SendTaskStreamingRequest` as JSON-RPC POST
- Yields `SendTaskStreamingResponse` for each SSE event
- Handles multiple sequential SSE events
- SSE connection uses no timeout (timeout=None)
- Generator closes cleanly when SSE stream ends

**send_task_streaming -- errors:**
- Connection failure -> `A2AClientHTTPError`
- Remote returns non-2xx before SSE starts -> `A2AClientHTTPError`
- SSE event data is not valid JSON -> `A2AClientJSONError`
- SSE event JSON is valid but not a valid `SendTaskStreamingResponse` -> `pydantic.ValidationError` propagates

**get_task:**
- Sends `GetTaskRequest` with correct method literal `"tasks/get"`
- Returns `GetTaskResponse` parsed from response
- HTTP error -> `A2AClientHTTPError`

**cancel_task:**
- Sends `CancelTaskRequest` with correct method literal `"tasks/cancel"`
- Returns `CancelTaskResponse` parsed from response
- HTTP error -> `A2AClientHTTPError`

**set_push_notification:**
- Sends `SetTaskPushNotificationRequest` with correct method literal `"tasks/pushNotification/set"`
- Returns `SetTaskPushNotificationResponse`
- HTTP error -> `A2AClientHTTPError`

**get_push_notification:**
- Sends `GetTaskPushNotificationRequest` with correct method literal `"tasks/pushNotification/get"`
- Returns `GetTaskPushNotificationResponse`
- HTTP error -> `A2AClientHTTPError`

**Request format verification (all methods):**
- All requests include `Content-Type: application/json` header
- Custom headers from config are included in all requests
- Request body is valid JSON-RPC 2.0 envelope

**Edge cases:**
- URL with trailing slash vs. without trailing slash (both work)
- Empty SSE stream (no events) -- generator exhausts without yielding
- SSE stream with non-data events (comments, heartbeats) -- ignored by httpx-sse
- Very large response body (stress test, not correctness -- just verify no crash)
- Concurrent calls via context manager (verify connection pooling, no races)

**Serialization round-trip:**
- `A2AClientConfig`: `model_dump()` -> `model_validate()` preserves url, timeout, headers

## ADR References

- None pending. Transport layer uses committed dependencies (`httpx`, `httpx-sse`) with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
