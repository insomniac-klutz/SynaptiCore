# LLD: agui_server

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.6
> Status: stub (rewrite -- not yet implemented)

## Responsibility

AG-UI protocol backend. Accepts user messages via HTTP POST, streams agent execution events to the frontend via SSE. Translates agent lifecycle into AG-UI protocol events. Agent executors are injected at startup via dependency injection -- no import-time dependency on `agents/`. Starlette sub-app mounted by `app_server` at `/agui/`.

## Public API

### Class: `AgUiServer`

| Method | Signature | Returns | Raises |
|--------|-----------|---------|--------|
| `__init__` | `(*, executor_registry: AgentExecutorRegistry \| None = None)` | -- | -- |
| `register_executor` | `(self, agent_id: str, executor: AgentExecutor)` | `None` | `DuplicateExecutorError` |
| `get_app` | `(self) -> Starlette` | `Starlette` | -- |

**`__init__`:**
- `executor_registry` -- Optional pre-populated registry of agent executors. When `None`, an empty registry is created and executors are registered via `register_executor` before the app starts serving.

**`register_executor`:**
- Binds an `agent_id` to an `AgentExecutor` callable. Called by `app_server` during startup to wire agents into the AG-UI layer without `agui_server` importing from `agents/`.
- Raises `DuplicateExecutorError` if `agent_id` is already registered.

**`get_app`:**
- Returns the Starlette sub-app with routes configured. Called by `app_server` to mount at `/agui/`.

### Type: `AgentExecutor` (Protocol)

```python
class AgentExecutor(Protocol):
    async def execute(
        self,
        run_config: AgUiRunConfig,
        event_emitter: EventEmitter,
    ) -> None:
        """
        Run the agent. Emit AG-UI events via event_emitter.
        Must emit RunStartedEvent at the beginning and
        RunFinishedEvent or RunErrorEvent at the end.
        Raise SynaptiCoreError subclasses for failures.
        """
        ...
```

- `AgentExecutor` is a `typing.Protocol`. Any object with a matching `execute` method satisfies the contract. This keeps `agui_server` decoupled from `agents/` -- agents implement the protocol, the server consumes it.
- `run_config` -- The validated `AgUiRunConfig` from the HTTP request.
- `event_emitter` -- Callback interface the executor uses to push `AgUiEvent` instances into the SSE stream.

### Type: `AgentExecutorRegistry`

```python
AgentExecutorRegistry = dict[str, AgentExecutor]
```

Simple dict mapping `agent_id` to `AgentExecutor`. No class wrapper needed -- the complexity is in the executor protocol, not the lookup.

### Class: `EventEmitter`

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `__init__` | `(self, *, thread_id: str, run_id: str)` | -- | Binds thread/run context for all emitted events |
| `emit` | `async (self, event: AgUiEvent)` | `None` | Puts event onto the internal `asyncio.Queue` |
| `emit_run_started` | `async (self)` | `None` | Convenience: emits `RunStartedEvent` with bound thread_id/run_id |
| `emit_text_start` | `async (self, message_id: str, role: AgUiRole = AgUiRole.ASSISTANT)` | `None` | Convenience: emits `TextMessageStartEvent` |
| `emit_text_delta` | `async (self, message_id: str, delta: str)` | `None` | Convenience: emits `TextMessageContentEvent` |
| `emit_text_end` | `async (self, message_id: str)` | `None` | Convenience: emits `TextMessageEndEvent` |
| `emit_tool_call_start` | `async (self, tool_call_id: str, tool_call_name: str, parent_message_id: str \| None = None)` | `None` | Convenience: emits `ToolCallStartEvent` |
| `emit_tool_call_args` | `async (self, tool_call_id: str, delta: str)` | `None` | Convenience: emits `ToolCallArgsEvent` |
| `emit_tool_call_end` | `async (self, tool_call_id: str, result: str \| None = None)` | `None` | Convenience: emits `ToolCallEndEvent` |
| `emit_state_snapshot` | `async (self, snapshot: dict[str, Any])` | `None` | Convenience: emits `StateSnapshotEvent` |
| `emit_state_delta` | `async (self, delta: list[dict[str, Any]])` | `None` | Convenience: emits `StateDeltaEvent` (JSON Patch ops) |
| `emit_step_started` | `async (self, step_name: str, step_id: str \| None = None)` | `None` | Convenience: emits `StepStartedEvent` |
| `emit_step_finished` | `async (self, step_name: str, step_id: str \| None = None)` | `None` | Convenience: emits `StepFinishedEvent` |
| `emit_run_finished` | `async (self, status: RunStatus = RunStatus.COMPLETED)` | `None` | Convenience: emits `RunFinishedEvent` with bound thread_id/run_id |
| `emit_run_error` | `async (self, error_code: str, error_message: str)` | `None` | Convenience: emits `RunErrorEvent` with bound thread_id/run_id |
| `close` | `async (self)` | `None` | Puts sentinel `None` on queue to signal SSE generator to stop |

**Internal:** `EventEmitter` holds an `asyncio.Queue[AgUiEvent | None]`. The SSE route reads from this queue. Agent executors write to it. The sentinel `None` signals end-of-stream.

### HTTP Routes

| Method | Path | Handler | Input | Output |
|--------|------|---------|-------|--------|
| `POST` | `/runs` | `_handle_run` | `AgUiRunConfig` (JSON body, max 5MB, max 100 messages) | `EventSourceResponse` (SSE stream of `AgUiEvent`) |
| `GET` | `/health` | `_handle_health` | -- | `JSONResponse` `{"status": "ok"}` |
| `GET` | `/agents` | `_handle_agents` | -- | `JSONResponse` listing registered agent_ids with metadata (OQ-013) |
| `GET` | `/threads/{thread_id}/messages` | `_handle_thread_messages` | `thread_id` path param | `JSONResponse` with conversation messages for the thread (OQ-019) |

**Note:** Routes are relative to the mount point. When `app_server` mounts at `/agui/`, the full paths become `/agui/runs`, `/agui/health`, `/agui/agents`, and `/agui/threads/{thread_id}/messages`.

## Internal Design

### Request-to-SSE flow

```
Client POST /agui/runs
  │  body: AgUiRunConfig (JSON)
  ▼
_handle_run(request)
  ├─ Parse + validate body → AgUiRunConfig
  │    └─ ValidationError → HTTP 400 JSONResponse
  ├─ Look up agent_id in executor_registry
  │    └─ Not found → HTTP 404 JSONResponse
  ├─ Generate run_id (uuid4) if not provided in config
  ├─ Resolve thread_id (from config or generate uuid4)
  ├─ Create EventEmitter(thread_id, run_id)
  ├─ Spawn background task: executor.execute(run_config, emitter)
  │    └─ On unhandled exception → emitter.emit_run_error() + emitter.close()
  └─ Return EventSourceResponse(event_generator(emitter))

event_generator(emitter):
  loop:
    event = await emitter.queue.get()
    if event is None:  # sentinel
      break
    yield {"event": event.type, "data": event.model_dump_json(by_alias=True, exclude_none=True)}
```

### SSE wire format

Each AG-UI event is serialized as an SSE frame:

```
event: TEXT_MESSAGE_CONTENT
data: {"messageId":"msg-1","delta":"Hello","type":"TEXT_MESSAGE_CONTENT"}

event: TOOL_CALL_START
data: {"toolCallId":"tc-1","toolCallName":"web_search","type":"TOOL_CALL_START"}
```

- `event:` is the `AgUiEventType` value (matches the `type` field on the model).
- `data:` is the full JSON-serialized event (camelCase via Pydantic aliases, `by_alias=True`).
- `exclude_none=True` to keep payloads compact.
- One blank line separates frames (SSE spec).

### Background task execution

The agent executor runs in a background `asyncio.Task`, not in the SSE generator coroutine. This decouples event production (agent) from event consumption (SSE response). The flow:

1. `_handle_run` creates the `EventEmitter` and spawns `asyncio.create_task(_run_executor(...))`.
2. `_run_executor` calls `executor.execute(run_config, emitter)` inside a `try/except`.
3. On success: executor is responsible for calling `emitter.emit_run_finished()` and `emitter.close()`.
4. On unhandled exception: `_run_executor` catches it, emits `RunErrorEvent`, and calls `emitter.close()`.
5. The SSE generator reads from the queue until it receives `None` (sentinel), then terminates the response.

### Client disconnect handling

When the client disconnects mid-stream (closes the SSE connection):

1. Starlette's `EventSourceResponse` detects the disconnect.
2. The SSE generator breaks out of the loop.
3. The background executor task may still be running. It will call `emitter.emit()`, which writes to the queue. Since nobody is reading, the queue fills up to `maxsize` (default 256) and then `emit()` blocks.
4. A `_disconnect_watchdog` checks `request.is_disconnected()` periodically and calls the background task's `cancel()` if the client is gone. The executor receives `asyncio.CancelledError`, which `_run_executor` catches, emits `RunErrorEvent(error_code="CANCELLED")` (best-effort, may fail if queue is full), and calls `emitter.close()`.

### Rewrite changes from legacy

There is no existing AG-UI server in the codebase. This is a new component. The existing A2A server (`Core/a2aPro/core/server.py`) informs the Starlette sub-app pattern:

**Patterns adopted from A2A server:**
- Starlette `app.add_route()` for route registration in `__init__`.
- `EventSourceResponse` from `sse-starlette` for SSE streaming.
- Error handling wrapper returning `JSONResponse` for pre-stream failures.

**Differences from A2A server:**
- **Unidirectional SSE** -- A2A uses SSE for streaming task results back (server→client). AG-UI is the same direction but with a richer event vocabulary (16 event types vs. A2A's single-type task updates).
- **No JSON-RPC** -- AG-UI uses plain HTTP POST + SSE. No JSON-RPC envelope, no `id` field, no method dispatch.
- **Dependency injection** -- A2A server receives a `TaskManager` instance. AG-UI server receives an `AgentExecutorRegistry` (dict of callables). The injection pattern is similar but the contract differs: `TaskManager` is a single abstract class, `AgentExecutorRegistry` is a dict of protocol-typed callables keyed by agent_id.
- **Background task model** -- A2A's `on_send_task_subscribe` returns an `AsyncIterable` that the server wraps in `EventSourceResponse`. AG-UI spawns the executor as a background `asyncio.Task` and bridges it via a queue. This is necessary because AG-UI executors are long-running (multi-step agent loops) and need to push events asynchronously rather than yielding from an iterable.

### Key Design Decisions

1. **`AgentExecutor` is a Protocol, not an ABC** -- Structural typing. Any class with `async def execute(self, run_config, event_emitter)` satisfies it. No base class import needed in `agents/`. This is the mechanism that breaks the import-time dependency from `protocols/` to `agents/`.
2. **Queue-based event bridge** -- The `asyncio.Queue` in `EventEmitter` decouples event production (agent executor) from consumption (SSE generator). Alternatives considered: (a) `AsyncIterable` yield from executor -- rejected because executors need to emit events from nested async calls, which doesn't compose well with `yield`; (b) callback functions -- rejected because SSE needs backpressure and ordered delivery, which a queue provides naturally.
3. **Background task, not inline execution** -- The executor runs in `asyncio.create_task()`, not inside the SSE generator. This prevents the SSE response from hanging if the executor blocks on an LLM call. The generator only reads from the queue and yields frames.
4. **Sentinel-based termination** -- `None` on the queue signals end-of-stream. Cleaner than a boolean flag polled in a loop. The generator's `async for` naturally terminates.
5. **No authentication in v1** -- Matches the "OUT v1: Multi-tenant auth / user management" scope from the HLD. The server accepts all requests. Auth middleware is a post-v1 concern.
6. **No thread persistence** -- `thread_id` is carried through the request and events but not stored. Conversation history comes from the client (in `AgUiRunConfig.messages`). In-memory state is the agent executor's responsibility (e.g., LangGraph MemorySaver). This matches the HLD's "in-memory state, lost on restart" stance.
7. **`run_id` generation** -- If `AgUiRunConfig.run_id` is `None`, the server generates a `uuid4`. The client may provide a `run_id` for idempotency tracking, but the server does not enforce uniqueness (no persistent store to check against).
8. **Health endpoint** -- Minimal `/health` for load balancer and frontend connectivity checks. Returns `{"status": "ok"}`. No dependency checks (no persistent store to ping).
9. **Error-to-protocol mapping** -- Pre-stream errors (bad JSON, unknown agent_id) return HTTP status codes. In-stream errors (agent failures, LLM timeouts) emit `RunErrorEvent` on the SSE stream. This split matches the AG-UI protocol: the SSE connection is established first, then errors flow as events.

10. **ConversationMessage to AgUiMessage translation (OQ-009)** -- `agui_server` owns the bidirectional translation between internal `ConversationMessage` (used by agents) and `AgUiMessage` (used by the AG-UI protocol). Incoming `AgUiRunConfig.messages` are converted to `list[ConversationMessage]` before passing to executors. Outgoing agent responses are translated back into AG-UI events. This translation layer is the single boundary between internal and protocol message formats.

11. **Error sanitization (OQ-014)** -- In-stream errors are sanitized before emission. Internal error types (`ProviderError`, `ConfigurationError`, `ToolExecutionError`, etc.) are mapped to user-friendly messages. The raw error details (stack traces, provider-specific messages) are logged server-side at ERROR level but never exposed to the client. The `RunErrorEvent.error_message` contains a sanitized, user-safe description. `RunErrorEvent.error_code` uses a stable enum-like string (e.g., `"PROVIDER_ERROR"`, `"INTERNAL_ERROR"`).

12. **Server-generated thread_id (OQ-018)** -- `thread_id` is always generated server-side as a `uuid4`. Client-provided `thread_id` in `AgUiRunConfig` is ignored. This prevents thread_id collisions, spoofing, and ensures the server is the authoritative source of thread identity. The generated `thread_id` is communicated to the client via `RunStartedEvent.thread_id`.

13. **SSE comment heartbeat every 15 seconds (OQ-011)** -- The SSE event generator emits an SSE comment (`: heartbeat\n\n`) every 15 seconds when no events are being produced. This keeps the connection alive through proxies, load balancers, and CDNs that may timeout idle connections. The heartbeat is implemented as a parallel `asyncio.Task` that writes to the event queue. SSE comments are ignored by compliant clients.

14. **Max 50 concurrent SSE connections via semaphore (OQ-024)** -- An `asyncio.Semaphore(50)` guards `_handle_run`. When 50 SSE connections are active, additional requests receive HTTP 503 `{"error": "Too many concurrent connections"}`. This prevents resource exhaustion from client storms or leaked connections.

15. **Max 5 concurrent agent runs via semaphore with queue (OQ-028)** -- An `asyncio.Semaphore(5)` guards `_run_executor`. When 5 agents are actively running, additional runs queue (up to the SSE connection limit). This prevents LLM API rate limit exhaustion and controls server-side compute. The semaphore is acquired before calling `executor.execute()` and released on completion/error.

16. **5MB body size limit + 100 message limit (OQ-023)** -- `_handle_run` rejects request bodies larger than 5MB with HTTP 413. After parsing, `AgUiRunConfig.messages` is validated to contain at most 100 messages; excess returns HTTP 400. These limits prevent abuse and bound memory consumption per request.

17. **GET /agui/agents discovery endpoint (OQ-013)** -- Returns a JSON array of registered agent entries, each with `agent_id`, `name`, and `description`. Enables the frontend to dynamically discover available agents without hardcoding agent_ids. The response is built from the `AgentExecutorRegistry` plus optional metadata registered alongside each executor.

18. **GET /agui/threads/{thread_id}/messages recovery endpoint (OQ-019)** -- Returns the conversation history for a given `thread_id` as a JSON array of messages. Enables the frontend to recover conversation state after an SSE disconnect or page reload. Messages are sourced from the agent executor's in-memory state. Returns 404 if the thread_id is unknown.

### Module structure

```
synapticore/protocols/agui_server.py
    AgentExecutor (Protocol)
    AgentExecutorRegistry (type alias)
    DuplicateExecutorError (exception)
    EventEmitter
        __init__(thread_id, run_id)
        async emit(event)
        async emit_run_started()
        async emit_text_start(message_id, role)
        async emit_text_delta(message_id, delta)
        async emit_text_end(message_id)
        async emit_tool_call_start(tool_call_id, tool_call_name, parent_message_id)
        async emit_tool_call_args(tool_call_id, delta)
        async emit_tool_call_end(tool_call_id, result)
        async emit_state_snapshot(snapshot)
        async emit_state_delta(delta)
        async emit_step_started(step_name, step_id)
        async emit_step_finished(step_name, step_id)
        async emit_run_finished(status)
        async emit_run_error(error_code, error_message)
        async close()
    AgUiServer
        __init__(executor_registry)
        _sse_semaphore: asyncio.Semaphore(50)       # OQ-024
        _run_semaphore: asyncio.Semaphore(5)         # OQ-028
        register_executor(agent_id, executor)
        get_app() -> Starlette
        async _handle_run(request) -> EventSourceResponse | JSONResponse
        async _handle_health(request) -> JSONResponse
        async _handle_agents(request) -> JSONResponse           # OQ-013
        async _handle_thread_messages(request) -> JSONResponse  # OQ-019
        async _run_executor(executor, run_config, emitter)
        async _event_generator(emitter) -> AsyncIterable[dict[str, str]]
        async _heartbeat(emitter) -> None                       # OQ-011
        async _disconnect_watchdog(request, task, emitter)
        _sanitize_error(error: Exception) -> tuple[str, str]    # OQ-014
        _translate_messages(messages: list[AgUiMessage]) -> list[ConversationMessage]  # OQ-009
```

### Pseudocode

```python
class EventEmitter:
    def __init__(self, *, thread_id: str, run_id: str):
        self.thread_id = thread_id
        self.run_id = run_id
        self._queue: asyncio.Queue[AgUiEvent | None] = asyncio.Queue(maxsize=256)

    async def emit(self, event: AgUiEvent) -> None:
        await self._queue.put(event)

    async def emit_run_started(self) -> None:
        await self.emit(RunStartedEvent(
            type="RUN_STARTED", thread_id=self.thread_id, run_id=self.run_id,
        ))

    # ... convenience methods construct the event and call self.emit() ...

    async def emit_run_error(self, error_code: str, error_message: str) -> None:
        await self.emit(RunErrorEvent(
            type="RUN_ERROR", thread_id=self.thread_id, run_id=self.run_id,
            error_code=error_code, error_message=error_message,
        ))

    async def close(self) -> None:
        await self._queue.put(None)


class AgUiServer:
    def __init__(self, *, executor_registry: AgentExecutorRegistry | None = None):
        self._registry: AgentExecutorRegistry = executor_registry or {}
        self._sse_semaphore = asyncio.Semaphore(50)   # OQ-024: max concurrent SSE connections
        self._run_semaphore = asyncio.Semaphore(5)     # OQ-028: max concurrent agent runs
        self._app = Starlette()
        self._app.add_route("/runs", self._handle_run, methods=["POST"])
        self._app.add_route("/health", self._handle_health, methods=["GET"])
        self._app.add_route("/agents", self._handle_agents, methods=["GET"])  # OQ-013
        self._app.add_route("/threads/{thread_id}/messages", self._handle_thread_messages, methods=["GET"])  # OQ-019

    def register_executor(self, agent_id: str, executor: AgentExecutor) -> None:
        if agent_id in self._registry:
            raise DuplicateExecutorError(agent_id)
        self._registry[agent_id] = executor

    def get_app(self) -> Starlette:
        return self._app

    async def _handle_run(self, request: Request) -> EventSourceResponse | JSONResponse:
        # OQ-023: 5MB body size limit
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 5 * 1024 * 1024:
            return JSONResponse({"error": "Request body too large (max 5MB)"}, status_code=413)

        # OQ-024: SSE connection limit
        if not self._sse_semaphore._value:  # all slots taken
            return JSONResponse({"error": "Too many concurrent connections"}, status_code=503)

        # Parse body
        try:
            body = await request.json()
            run_config = AgUiRunConfig.model_validate(body)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        except ValidationError as e:
            return JSONResponse({"error": "Validation failed", "details": e.errors()}, status_code=400)

        # OQ-023: 100 message limit
        if run_config.messages and len(run_config.messages) > 100:
            return JSONResponse({"error": "Too many messages (max 100)"}, status_code=400)

        # Resolve executor
        executor = self._registry.get(run_config.agent_id)
        if executor is None:
            return JSONResponse(
                {"error": f"Unknown agent_id: {run_config.agent_id}"},
                status_code=404,
            )

        # Generate IDs -- OQ-018: server-generated thread_id (ignore client-provided)
        run_id = run_config.run_id or str(uuid.uuid4())
        thread_id = str(uuid.uuid4())  # always server-generated
        run_config_resolved = run_config.model_copy(
            update={"run_id": run_id, "thread_id": thread_id},
        )

        # OQ-009: translate AgUiMessages to ConversationMessages
        # (translation happens inside executor or via _translate_messages helper)

        # Create emitter and spawn executor
        await self._sse_semaphore.acquire()  # OQ-024
        emitter = EventEmitter(thread_id=thread_id, run_id=run_id)
        task = asyncio.create_task(self._run_executor(executor, run_config_resolved, emitter))

        # OQ-011: spawn heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat(emitter))

        # Spawn disconnect watchdog
        asyncio.create_task(self._disconnect_watchdog(request, task, emitter, heartbeat_task))

        return EventSourceResponse(self._event_generator(emitter))

    async def _run_executor(
        self, executor: AgentExecutor, run_config: AgUiRunConfig, emitter: EventEmitter,
    ) -> None:
        try:
            await self._run_semaphore.acquire()  # OQ-028: limit concurrent agent runs
            try:
                await executor.execute(run_config, emitter)
            finally:
                self._run_semaphore.release()
        except asyncio.CancelledError:
            await emitter.emit_run_error("CANCELLED", "Run cancelled by client disconnect")
            await emitter.close()
        except SynaptiCoreError as e:
            # OQ-014: log raw error server-side, sanitize for client
            logger.error("Agent executor failed: %s", e.message, exc_info=True)
            error_code, safe_message = self._sanitize_error(e)
            await emitter.emit_run_error(error_code, safe_message)
            await emitter.close()
        except Exception as e:
            # OQ-014: never expose raw exception details to client
            logger.error("Unexpected error in agent executor: %s", e, exc_info=True)
            await emitter.emit_run_error("INTERNAL_ERROR", "An unexpected error occurred. Please try again.")
            await emitter.close()
        finally:
            self._sse_semaphore.release()  # OQ-024: release SSE slot

    async def _event_generator(self, emitter: EventEmitter) -> AsyncIterable[dict[str, str]]:
        while True:
            event = await emitter._queue.get()
            if event is None:
                break
            yield {
                "event": event.type,
                "data": event.model_dump_json(by_alias=True, exclude_none=True),
            }

    async def _disconnect_watchdog(
        self, request: Request, task: asyncio.Task, emitter: EventEmitter,
        heartbeat_task: asyncio.Task | None = None,
    ) -> None:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                if heartbeat_task:
                    heartbeat_task.cancel()
                return
            await asyncio.sleep(1)
        # Clean up heartbeat when executor finishes normally
        if heartbeat_task and not heartbeat_task.done():
            heartbeat_task.cancel()

    async def _heartbeat(self, emitter: EventEmitter) -> None:
        """OQ-011: SSE comment heartbeat every 15 seconds to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(15)
                # SSE comment format: ": heartbeat\n\n" -- ignored by compliant clients
                await emitter._queue.put({"comment": "heartbeat"})
        except asyncio.CancelledError:
            pass

    def _sanitize_error(self, error: Exception) -> tuple[str, str]:
        """OQ-014: Map internal errors to user-friendly messages, log raw server-side."""
        from types import common_types  # noqa -- illustrative
        error_map = {
            "ProviderError": ("PROVIDER_ERROR", "The AI service is temporarily unavailable. Please try again."),
            "ConfigurationError": ("CONFIGURATION_ERROR", "The service is misconfigured. Please contact support."),
            "ToolExecutionError": ("TOOL_ERROR", "A tool encountered an error while processing your request."),
            "ToolNotFoundError": ("TOOL_ERROR", "The requested tool is not available."),
        }
        class_name = type(error).__name__
        return error_map.get(class_name, ("INTERNAL_ERROR", "An unexpected error occurred."))

    async def _handle_health(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})
```

## Dependencies

### Internal
- `types/agui_types` -- `AgUiRunConfig`, `AgUiEvent`, `AgUiMessage`, `RunStartedEvent`, `RunFinishedEvent`, `RunErrorEvent`, `TextMessageStartEvent`, `TextMessageContentEvent`, `TextMessageEndEvent`, `ToolCallStartEvent`, `ToolCallArgsEvent`, `ToolCallEndEvent`, `StateSnapshotEvent`, `StateDeltaEvent`, `StepStartedEvent`, `StepFinishedEvent`, `AgUiRole`, `RunStatus`
- `types/common_types` -- `SynaptiCoreError`, `ConversationMessage` (for OQ-009 message translation), `ProviderError`, `ConfigurationError`, `ToolExecutionError`, `ToolNotFoundError` (for OQ-014 error sanitization)

### External
- `starlette` (Starlette, Request, JSONResponse)
- `sse-starlette` (EventSourceResponse)
- `pydantic` (ValidationError -- caught, not used for modeling in this module)
- `asyncio` (Queue, create_task, CancelledError)
- `uuid` (uuid4)
- `json` (JSONDecodeError -- caught)
- `logging`
- `typing` (Protocol, AsyncIterable, Any)

### NOT dependencies (by design)
- `agents/*` -- Agent executors are injected at runtime. `agui_server` has zero import-time dependency on any agent module.
- `tools/*` -- Tools are accessed by agents, not by the server. The server only sees `AgUiEvent` events emitted by executors.

## Error Contracts

### Pre-stream errors (HTTP responses, before SSE connection is established)

| Condition | HTTP Status | Response Body |
|-----------|-------------|---------------|
| Request body exceeds 5MB (OQ-023) | 413 | `{"error": "Request body too large (max 5MB)"}` |
| Request body is not valid JSON | 400 | `{"error": "Invalid JSON"}` |
| Request body fails `AgUiRunConfig` validation | 400 | `{"error": "Validation failed", "details": [...]}` |
| Messages array exceeds 100 entries (OQ-023) | 400 | `{"error": "Too many messages (max 100)"}` |
| `agent_id` not found in executor registry | 404 | `{"error": "Unknown agent_id: {agent_id}"}` |
| 50 concurrent SSE connections already active (OQ-024) | 503 | `{"error": "Too many concurrent connections"}` |
| Thread ID not found (GET /threads/{thread_id}/messages) | 404 | `{"error": "Unknown thread_id: {thread_id}"}` |

### In-stream errors (SSE events, after SSE connection is established)

| Condition | Event | Fields |
|-----------|-------|--------|
| Agent executor raises `SynaptiCoreError` subclass | `RunErrorEvent` | `error_code`: sanitized code (OQ-014), `error_message`: user-friendly message (raw logged server-side) |
| Agent executor raises unexpected `Exception` | `RunErrorEvent` | `error_code`: `"INTERNAL_ERROR"`, `error_message`: `"An unexpected error occurred. Please try again."` (raw logged server-side, OQ-014) |
| Client disconnects, executor cancelled | `RunErrorEvent` | `error_code`: `"CANCELLED"`, `error_message`: description (best-effort, may not be delivered) |
| `pydantic.ValidationError` during event construction | `RunErrorEvent` | `error_code`: `"INTERNAL_ERROR"`, `error_message`: sanitized (raw logged server-side) |

### Error mapping from `common_types` hierarchy

| Internal Error | AG-UI Mapping |
|---------------|---------------|
| `SynaptiCoreError` | `RunErrorEvent` (error_code = class name) |
| `ProviderError` | `RunErrorEvent` (error_code = `"ProviderError"`) |
| `ConfigurationError` | `RunErrorEvent` (error_code = `"ConfigurationError"`) |
| `ToolExecutionError` | `RunErrorEvent` (error_code = `"ToolExecutionError"`) |
| `ToolNotFoundError` | `RunErrorEvent` (error_code = `"ToolNotFoundError"`) |

### Defined by this module
- `DuplicateExecutorError` -- Raised when `register_executor` is called with an `agent_id` that already exists. Inherits from `SynaptiCoreError`. This is a startup-time configuration error, not a request-time error.

### Error flow

```
POST /agui/runs
  ├─ Invalid JSON body          → HTTP 400 (JSONResponse)
  ├─ AgUiRunConfig validation   → HTTP 400 (JSONResponse)
  ├─ Unknown agent_id           → HTTP 404 (JSONResponse)
  └─ Valid request
       ├─ SSE connection established
       ├─ Executor runs...
       │    ├─ Success           → RunFinishedEvent (emitted by executor)
       │    ├─ SynaptiCoreError  → RunErrorEvent (emitted by _run_executor wrapper)
       │    ├─ Unexpected error  → RunErrorEvent (emitted by _run_executor wrapper)
       │    └─ Client disconnect → CancelledError → RunErrorEvent (best-effort)
       └─ Sentinel None on queue → SSE stream ends
```

## Test Plan

### Unit tests (`tests/unit/protocols/test_agui_server.py`)

All tests use an in-process Starlette `TestClient` (from `starlette.testclient`) or `httpx.AsyncClient` with `ASGITransport`. No real network calls. Mock `AgentExecutor` implementations satisfy the protocol.

**EventEmitter:**
- `emit()` puts event on queue; reading from queue returns the same event.
- `emit_run_started()` produces `RunStartedEvent` with correct `thread_id` and `run_id`.
- `emit_text_start()` / `emit_text_delta()` / `emit_text_end()` produce correct event types with provided args.
- `emit_tool_call_start()` / `emit_tool_call_args()` / `emit_tool_call_end()` produce correct event types.
- `emit_state_snapshot()` produces `StateSnapshotEvent` with the provided dict.
- `emit_state_delta()` produces `StateDeltaEvent` with the provided JSON Patch list.
- `emit_step_started()` / `emit_step_finished()` produce correct event types.
- `emit_run_finished()` produces `RunFinishedEvent` with default `COMPLETED` status.
- `emit_run_finished(status=RunStatus.ERROR)` produces `RunFinishedEvent` with `ERROR` status.
- `emit_run_error()` produces `RunErrorEvent` with provided error_code and error_message.
- `close()` puts `None` sentinel on queue.
- Multiple `emit()` calls preserve FIFO order.

**AgUiServer registration:**
- `register_executor` stores executor; subsequent request with that `agent_id` routes to it.
- `register_executor` with duplicate `agent_id` raises `DuplicateExecutorError`.
- Constructor with pre-populated `executor_registry` dict makes those executors available.

**Happy path -- POST /runs:**
- Valid `AgUiRunConfig` with registered `agent_id` returns `EventSourceResponse` (status 200, content-type `text/event-stream`).
- SSE stream contains `RunStartedEvent` as first event (emitted by mock executor).
- SSE stream contains `RunFinishedEvent` as last event before stream ends.
- `run_id` is auto-generated (uuid4 format) when not provided in config.
- `thread_id` is auto-generated when not provided in config.
- `run_id` from config is used when provided.
- `thread_id` from config is used when provided.

**SSE wire format:**
- Each SSE frame has `event:` matching the event type string.
- Each SSE frame has `data:` containing valid JSON with camelCase keys.
- Events are delivered in the order the executor emits them.
- Stream terminates after executor calls `emitter.close()`.

**Text streaming flow:**
- Mock executor emits `RunStartedEvent` → `TextMessageStartEvent` → multiple `TextMessageContentEvent` → `TextMessageEndEvent` → `RunFinishedEvent`. SSE stream contains all events in order.

**Tool call flow:**
- Mock executor emits `ToolCallStartEvent` → `ToolCallArgsEvent` (one or more) → `ToolCallEndEvent`. SSE stream contains all events in order with correct `tool_call_id` linkage.

**State sync flow:**
- Mock executor emits `StateSnapshotEvent` with a dict → SSE stream contains the snapshot.
- Mock executor emits `StateDeltaEvent` with JSON Patch operations → SSE stream contains the delta.

**Pre-stream errors:**
- Request body is not JSON → HTTP 400, response contains `"error"` key.
- Request body is valid JSON but fails `AgUiRunConfig` validation (e.g., missing `agent_id`) → HTTP 400 with `"details"`.
- Request body is valid `AgUiRunConfig` but `agent_id` is not registered → HTTP 404.

**In-stream errors:**
- Mock executor raises `SynaptiCoreError("fail")` → SSE stream contains `RunErrorEvent` with `error_code` = `"SynaptiCoreError"` and `error_message` = `"fail"`, then stream ends.
- Mock executor raises `ProviderError("timeout", provider="bedrock")` → SSE stream contains `RunErrorEvent` with `error_code` = `"ProviderError"`.
- Mock executor raises `ToolExecutionError("crash", tool_name="web_search")` → SSE stream contains `RunErrorEvent` with `error_code` = `"ToolExecutionError"`.
- Mock executor raises unexpected `RuntimeError("bug")` → SSE stream contains `RunErrorEvent` with `error_code` = `"INTERNAL_ERROR"`, `error_message` = `"bug"`.
- Mock executor raises `ValueError` (non-SynaptiCore exception) → same INTERNAL_ERROR handling.

**GET /health:**
- Returns 200 with `{"status": "ok"}`.

**Edge cases:**
- `AgUiRunConfig` with empty `messages` list -- valid, executor receives it.
- `AgUiRunConfig` with `context` dict populated -- passed through to executor.
- Mock executor emits zero events then calls `close()` -- SSE stream ends immediately (no events).
- Mock executor emits events very slowly (simulated with `asyncio.sleep`) -- SSE stream delivers events as they arrive (no batching).
- Multiple concurrent POST /runs requests -- each gets its own `EventEmitter` and executor task (no shared state between runs).
- `register_executor` called after `get_app()` -- executor is still available (registry is shared by reference).

## ADR References

- None pending. AG-UI server uses committed frameworks only (Starlette, sse-starlette, Pydantic). The `AgentExecutor` Protocol pattern is a standard Python typing construct, not a framework choice.

## Maturity

All functions: `stub` (rewrite target)
