# LLD: agui_client

> Container: C2 (synapticore-ui) | Component: agui_client
> HLD Reference: S3 C2.1
> Status: stub (rewrite -- not yet implemented)

## Responsibility

AG-UI client layer. Connects to the backend SSE endpoint (`/agui/runs`), sends user messages via HTTP POST, deserializes the `AgUiEvent` SSE stream, and exposes typed event callbacks for React components.

## Public API

### AgUiClientConfig

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `agentId` | `string` | -- (required) | Agent identifier passed in `AgUiRunConfig.agent_id`. Determines which backend agent handles the run. |
| `apiBaseUrl` | `string` | `"http://localhost:8000"` | Base URL of the backend server. Injected from `app_shell`'s `apiBaseUrl`. |
| `threadId` | `string \| undefined` | `undefined` | Optional thread ID for conversation continuity. When omitted, the backend assigns one. |

### Factory Function

| Function | Signature | Notes |
|----------|-----------|-------|
| `createAgUiClient` | `(config: AgUiClientConfig) => AgUiClient` | Creates and returns an `AgUiClient` instance. Constructs the `@ag-ui/client` `HttpAgent` internally with the resolved endpoint URL (`${apiBaseUrl}/agui/runs`). Does not open a connection -- connection starts on `run()`. |

### AgUiClient

| Method | Signature | Notes |
|--------|-----------|-------|
| `run` | `(params: RunParams) => RunHandle` | Initiates a run. Sends `AgUiRunConfig` via the `HttpAgent`, opens the SSE connection, and begins dispatching events to registered callbacks. Returns a `RunHandle` for cancellation. |
| `onRunStarted` | `(cb: (event: RunStartedEvent) => void) => Unsubscribe` | Register callback for `RUN_STARTED` events. Returns an unsubscribe function. |
| `onTextMessageStart` | `(cb: (event: TextMessageStartEvent) => void) => Unsubscribe` | Register callback for `TEXT_MESSAGE_START` events. |
| `onTextMessageContent` | `(cb: (event: TextMessageContentEvent) => void) => Unsubscribe` | Register callback for `TEXT_MESSAGE_CONTENT` events. Called per chunk of streamed text. |
| `onTextMessageEnd` | `(cb: (event: TextMessageEndEvent) => void) => Unsubscribe` | Register callback for `TEXT_MESSAGE_END` events. |
| `onToolCallStart` | `(cb: (event: ToolCallStartEvent) => void) => Unsubscribe` | Register callback for `TOOL_CALL_START` events. |
| `onToolCallArgs` | `(cb: (event: ToolCallArgsEvent) => void) => Unsubscribe` | Register callback for `TOOL_CALL_ARGS` events. Called per chunk of streamed tool arguments. |
| `onToolCallEnd` | `(cb: (event: ToolCallEndEvent) => void) => Unsubscribe` | Register callback for `TOOL_CALL_END` events. |
| `onStateSnapshot` | `(cb: (event: StateSnapshotEvent) => void) => Unsubscribe` | Register callback for `STATE_SNAPSHOT` events. |
| `onStateDelta` | `(cb: (event: StateDeltaEvent) => void) => Unsubscribe` | Register callback for `STATE_DELTA` events. Delta is RFC 6902 JSON Patch format. |
| `onStepStarted` | `(cb: (event: StepStartedEvent) => void) => Unsubscribe` | Register callback for `STEP_STARTED` events. |
| `onStepFinished` | `(cb: (event: StepFinishedEvent) => void) => Unsubscribe` | Register callback for `STEP_FINISHED` events. |
| `onRunFinished` | `(cb: (event: RunFinishedEvent) => void) => Unsubscribe` | Register callback for `RUN_FINISHED` events. Terminal -- no more events after this. |
| `onRunError` | `(cb: (event: RunErrorEvent) => void) => Unsubscribe` | Register callback for `RUN_ERROR` events. Terminal -- no more events after this. |
| `onEvent` | `(cb: (event: AgUiEvent) => void) => Unsubscribe` | Wildcard listener. Called for every event regardless of type. Useful for logging and debugging. |
| `dispose` | `() => void` | Cleans up all subscriptions and closes any active SSE connection. Must be called when the client is no longer needed (e.g., component unmount). |

### RunParams

| Field | Type | Notes |
|-------|------|-------|
| `messages` | `AgUiMessage[]` | Conversation messages to send. At minimum, the latest user message. |
| `context` | `Record<string, unknown> \| undefined` | Optional context dict forwarded to the backend as `AgUiRunConfig.context`. |
| `runId` | `string \| undefined` | Optional client-generated run ID. When omitted, the backend assigns one. |

### RunHandle

| Field / Method | Type | Notes |
|----------------|------|-------|
| `runId` | `string \| undefined` | The run ID (available after `RUN_STARTED` event). `undefined` until the first event arrives. |
| `abort` | `() => void` | Cancels the active run. Closes the SSE connection. The backend may or may not emit `RUN_FINISHED` with status `CANCELLED` depending on timing. |

### Type Re-exports

The following types are re-exported from `@ag-ui/core` for consumer convenience. Components importing from `agui_client` do not need a direct dependency on `@ag-ui/core`:

| Type | Origin | Notes |
|------|--------|-------|
| `RunStartedEvent` | `@ag-ui/core` | |
| `RunFinishedEvent` | `@ag-ui/core` | |
| `RunErrorEvent` | `@ag-ui/core` | |
| `TextMessageStartEvent` | `@ag-ui/core` | |
| `TextMessageContentEvent` | `@ag-ui/core` | |
| `TextMessageEndEvent` | `@ag-ui/core` | |
| `ToolCallStartEvent` | `@ag-ui/core` | |
| `ToolCallArgsEvent` | `@ag-ui/core` | |
| `ToolCallEndEvent` | `@ag-ui/core` | |
| `StateSnapshotEvent` | `@ag-ui/core` | |
| `StateDeltaEvent` | `@ag-ui/core` | |
| `StepStartedEvent` | `@ag-ui/core` | |
| `StepFinishedEvent` | `@ag-ui/core` | |
| `AgUiMessage` | `@ag-ui/core` | Message model for run config and snapshots |
| `AgUiRunConfig` | `@ag-ui/core` | Full run configuration sent to backend |

## Internal Design

### Key Design Decisions

1. **Thin wrapper over `@ag-ui/client` `HttpAgent`** -- The `agui_client` module does not implement SSE parsing, reconnection, or event deserialization. It delegates all transport concerns to `@ag-ui/client`'s `HttpAgent`. The module's value is: (a) typed callback registration with per-event-type subscriptions, (b) endpoint URL construction from config, (c) `RunParams` → `AgUiRunConfig` mapping, and (d) lifecycle management (`dispose`).

2. **Callback-based, not hook-based** -- The client exposes `on<EventType>` methods that return unsubscribe functions, not React hooks. This keeps the client framework-agnostic at this layer. React integration (hooks like `useAgUiClient`) is `chat_view`'s responsibility. This separation enables testing the client without a React render tree.

3. **Event routing via discriminated union `type` field** -- When the `HttpAgent` emits a raw event, the client inspects the `type` field and dispatches to the matching typed callback set. The `onEvent` wildcard receives every event. This mirrors the `AgUiEvent` discriminated union from `agui_types` but in TypeScript using `@ag-ui/core` types.

4. **Terminal events close the connection** -- `RUN_FINISHED` and `RUN_ERROR` are terminal. After dispatching either, the client automatically closes the SSE connection and prevents further callback invocations. This matches the AG-UI protocol's run lifecycle guarantee: exactly one terminal event per run.

5. **No automatic reconnection** -- If the SSE connection drops unexpectedly (network failure, server crash), the client emits a synthetic `RunErrorEvent` with `error_code: "CONNECTION_ERROR"` and does not reconnect. Reconnection with state recovery is out of scope for v1 (would require `thread_id` + `MessagesSnapshotEvent` replay). The consumer (`chat_view`) can present a "Reconnect" action to the user.

6. **`dispose` is mandatory** -- React components must call `dispose()` on unmount (typically in a `useEffect` cleanup). Failing to dispose leaks the SSE connection and callback references. The `chat_view` LLD enforces this contract.

7. **`AgUiRunConfig` assembly** -- The client constructs `AgUiRunConfig` from `RunParams` + `AgUiClientConfig`: `{ agent_id: config.agentId, messages: params.messages, thread_id: config.threadId, run_id: params.runId, context: params.context }`. This assembly is the only place where the two config surfaces merge.

8. **Re-export event types** -- Consumers (primarily `chat_view`) need event types for callback signatures. Re-exporting from `agui_client` avoids forcing consumers to declare a direct dependency on `@ag-ui/core`. The client module is the sole import surface for AG-UI concerns in the frontend.

### Module structure

```
src/
    agui/
        client.ts             # createAgUiClient factory, AgUiClient class, RunHandle
        types.ts              # AgUiClientConfig, RunParams, Unsubscribe type alias
        index.ts              # Barrel export -- re-exports public API + @ag-ui/core event types
```

### Event dispatch flow

```
HttpAgent (SSE stream from /agui/runs)
    → raw event (JSON parsed by @ag-ui/client)
    → agui_client event router
        → inspect event.type
        → dispatch to typed callback set (e.g., onTextMessageContent subscribers)
        → dispatch to onEvent wildcard subscribers
        → if terminal (RUN_FINISHED | RUN_ERROR): close connection, mark run complete
```

### Connection lifecycle

```
1. createAgUiClient(config)          → AgUiClient instance (idle)
2. client.on<EventType>(callback)    → registers callbacks (can register before or after run)
3. client.run(params)                → constructs AgUiRunConfig, calls HttpAgent.runAgent()
                                       → SSE connection opens
                                       → events stream in, dispatched to callbacks
4a. RUN_FINISHED / RUN_ERROR arrives → connection closes automatically
4b. handle.abort() called            → connection closed by client
5. client.dispose()                  → all subscriptions cleared, connection closed if active
```

## Dependencies

### Internal
- `C2.3 app_shell` -- provides `apiBaseUrl` configuration (passed through to `AgUiClientConfig.apiBaseUrl`)

### External
- `@ag-ui/client` -- `HttpAgent` class for SSE transport to AG-UI backend
- `@ag-ui/core` -- TypeScript types for AG-UI events (`RunStartedEvent`, `TextMessageContentEvent`, etc.), `AgUiMessage`, `AgUiRunConfig`
- `typescript` -- Type safety

## Error Contracts

### Errors surfaced to consumers

| Error Scenario | Surfacing Mechanism | `error_code` | Notes |
|----------------|---------------------|--------------|-------|
| Backend emits `RUN_ERROR` event | `onRunError` callback | Value from backend (e.g., `"PROVIDER_ERROR"`, `"INTERNAL_ERROR"`) | Protocol-level error. The backend's `agui_server` maps internal `SynaptiCoreError` subtypes to `RunErrorEvent`. |
| SSE connection drops unexpectedly | Synthetic `RunErrorEvent` via `onRunError` callback | `"CONNECTION_ERROR"` | Client-generated. Not from the backend. `error_message` includes the underlying network error text. |
| HTTP POST to `/agui/runs` returns 4xx/5xx | Synthetic `RunErrorEvent` via `onRunError` callback | `"HTTP_ERROR"` | Client-generated. `error_message` includes status code and response body if available. The `HttpAgent` may throw; the client catches and translates to a `RunErrorEvent`. |
| Malformed SSE event (JSON parse failure) | Synthetic `RunErrorEvent` via `onRunError` callback | `"PARSE_ERROR"` | Client-generated. Indicates a protocol mismatch between client and server AG-UI versions. |

### Not handled here
- Validation of `RunParams.messages` content (e.g., empty messages array). The backend's `agui_server` validates `AgUiRunConfig` and returns HTTP 400 or a `RunErrorEvent`.
- Authentication / authorization errors. Out of scope for v1 (no auth).
- Retry logic. No automatic retries for any error type. Consumer decides whether to retry.

## Test Plan

### Unit tests (`tests/unit/ui/agui/test_client.ts`)

**Factory and configuration:**
- `createAgUiClient` returns an `AgUiClient` instance
- Constructs endpoint URL as `${apiBaseUrl}/agui/runs`
- Strips trailing slash from `apiBaseUrl` before constructing endpoint
- Defaults `apiBaseUrl` to `"http://localhost:8000"` when not provided
- Passes `agentId` through to `AgUiRunConfig.agent_id`
- Passes `threadId` through to `AgUiRunConfig.thread_id` when provided
- Omits `thread_id` from `AgUiRunConfig` when `threadId` is undefined

**Callback registration:**
- `on<EventType>` returns an unsubscribe function
- Calling unsubscribe prevents future callback invocations for that listener
- Multiple callbacks for the same event type all fire
- `onEvent` wildcard fires for every event type
- Registering callbacks after `run()` still receives subsequent events
- Registering callbacks before `run()` receives events once the run starts

**Run lifecycle:**
- `run()` calls `HttpAgent.runAgent` with correctly assembled `AgUiRunConfig`
- `run()` returns a `RunHandle` with `abort` method
- `RunHandle.runId` is `undefined` before `RUN_STARTED` arrives
- `RunHandle.runId` is populated after `RUN_STARTED` event
- `abort()` closes the SSE connection

**Event dispatch (mock HttpAgent emitting events):**
- `RUN_STARTED` event dispatches to `onRunStarted` callbacks
- `TEXT_MESSAGE_START` event dispatches to `onTextMessageStart` callbacks
- `TEXT_MESSAGE_CONTENT` event dispatches to `onTextMessageContent` callbacks
- `TEXT_MESSAGE_END` event dispatches to `onTextMessageEnd` callbacks
- `TOOL_CALL_START` event dispatches to `onToolCallStart` callbacks
- `TOOL_CALL_ARGS` event dispatches to `onToolCallArgs` callbacks
- `TOOL_CALL_END` event dispatches to `onToolCallEnd` callbacks
- `STATE_SNAPSHOT` event dispatches to `onStateSnapshot` callbacks
- `STATE_DELTA` event dispatches to `onStateDelta` callbacks
- `STEP_STARTED` event dispatches to `onStepStarted` callbacks
- `STEP_FINISHED` event dispatches to `onStepFinished` callbacks
- `RUN_FINISHED` event dispatches to `onRunFinished` callbacks
- `RUN_ERROR` event dispatches to `onRunError` callbacks
- Each dispatched event also fires `onEvent` wildcard

**Terminal event behavior:**
- After `RUN_FINISHED`, no further callbacks are invoked
- After `RUN_ERROR`, no further callbacks are invoked
- After terminal event, SSE connection is closed

**Error scenarios (mock HttpAgent failures):**
- SSE connection drop emits synthetic `RunErrorEvent` with `error_code: "CONNECTION_ERROR"`
- HTTP 400 response emits synthetic `RunErrorEvent` with `error_code: "HTTP_ERROR"`
- HTTP 500 response emits synthetic `RunErrorEvent` with `error_code: "HTTP_ERROR"`
- Malformed SSE JSON emits synthetic `RunErrorEvent` with `error_code: "PARSE_ERROR"`

**Dispose:**
- `dispose()` clears all registered callbacks
- `dispose()` closes active SSE connection
- After `dispose()`, `on<EventType>` registrations are no-ops (or throw)
- After `dispose()`, `run()` throws or returns an inert handle

**Edge cases:**
- Multiple sequential `run()` calls (second run starts after first completes)
- `run()` called while a run is already active (should throw or queue -- design decision: throw with descriptive error)
- `abort()` called after run already finished (no-op)
- `dispose()` called while a run is active (closes connection, clears callbacks)
- Empty `messages` array in `RunParams` (passed through -- backend validates)
- `TEXT_MESSAGE_CONTENT` events with empty `delta` string
- Rapid succession of `TEXT_MESSAGE_CONTENT` events (all dispatched in order)

## ADR References

- None pending. Uses the committed `@ag-ui/client` and `@ag-ui/core` SDKs with no framework choices beyond the committed stack.

## Maturity

All functions: `stub` (rewrite target)
