# LLD: a2a_task_manager

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.3
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Abstract task lifecycle manager defining the 7-method contract that `a2a_server` dispatches to, plus `InMemoryTaskManager` -- the reference implementation backed by Python dicts, asyncio locks, and asyncio.Queue-based SSE subscriber fanout. All task state mutations go through this module. Agent-specific logic (LLM calls, tool execution) is injected by subclasses that override `on_send_task` and `on_send_task_subscribe`.

## Public API

### `TaskManager` (abstract base class)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `on_get_task` | `(request: GetTaskRequest) -> GetTaskResponse` | `GetTaskResponse` | Retrieve a task by ID with optional history truncation. |
| `on_cancel_task` | `(request: CancelTaskRequest) -> CancelTaskResponse` | `CancelTaskResponse` | Cancel a running task. Base implementation returns `TaskNotCancelableError`. |
| `on_send_task` | `(request: SendTaskRequest) -> SendTaskResponse` | `SendTaskResponse` | Submit or continue a task (request-response mode). **Abstract -- must be overridden.** |
| `on_send_task_subscribe` | `(request: SendTaskStreamingRequest) -> AsyncIterable[SendTaskStreamingResponse] \| JSONRPCResponse` | `AsyncIterable` or `JSONRPCResponse` | Submit or continue a task (streaming mode). Returns SSE event stream or error. **Abstract -- must be overridden.** |
| `on_set_task_push_notification` | `(request: SetTaskPushNotificationRequest) -> SetTaskPushNotificationResponse` | `SetTaskPushNotificationResponse` | Register push notification config for a task. |
| `on_get_task_push_notification` | `(request: GetTaskPushNotificationRequest) -> GetTaskPushNotificationResponse` | `GetTaskPushNotificationResponse` | Retrieve push notification config for a task. |
| `on_resubscribe_to_task` | `(request: TaskResubscriptionRequest) -> AsyncIterable[SendTaskStreamingResponse] \| JSONRPCResponse` | `AsyncIterable` or `JSONRPCResponse` | Resubscribe to an existing task's SSE stream. |

### `InMemoryTaskManager` (extends `TaskManager`)

Provides the concrete storage and concurrency layer. Subclasses override `on_send_task` and `on_send_task_subscribe` to inject agent logic, calling the helper methods below to manage state.

#### Constructor

| Attribute | Type | Notes |
|-----------|------|-------|
| `tasks` | `dict[str, Task]` | In-memory task store keyed by task ID. |
| `push_notification_infos` | `dict[str, PushNotificationConfig]` | Push notification config keyed by task ID. |
| `lock` | `asyncio.Lock` | Guards `tasks` and `push_notification_infos` against concurrent mutation. |
| `task_sse_subscribers` | `dict[str, list[asyncio.Queue]]` | SSE subscriber queues keyed by task ID. Multiple subscribers per task. |
| `subscriber_lock` | `asyncio.Lock` | Guards `task_sse_subscribers` against concurrent mutation. Separate from `lock` to avoid blocking task state updates while managing subscribers. |

#### Implemented `TaskManager` Methods

| Method | Behavior |
|--------|----------|
| `on_get_task` | Looks up `task_query_params.id` in `self.tasks` under `self.lock`. Returns `TaskNotFoundError` if missing. Otherwise returns task copy with history truncated per `historyLength`. |
| `on_cancel_task` | Looks up `task_id_params.id` in `self.tasks` under `self.lock`. Returns `TaskNotFoundError` if missing. Returns `TaskNotCancelableError` (cancel is not implemented in the base in-memory manager -- subclasses may override). |
| `on_send_task` | **Abstract** -- subclasses must override. |
| `on_send_task_subscribe` | **Abstract** -- subclasses must override. |
| `on_set_task_push_notification` | Delegates to `set_push_notification_info`. On success, returns the `TaskPushNotificationConfig`. On failure, returns `InternalError`. |
| `on_get_task_push_notification` | Delegates to `get_push_notification_info`. On success, returns `TaskPushNotificationConfig` wrapping the stored config. On failure, returns `InternalError`. |
| `on_resubscribe_to_task` | Returns `UnsupportedOperationError`. Placeholder for future implementation. |

#### Helper Methods (used by subclasses)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `upsert_task` | `(task_send_params: TaskSendParams) -> Task` | `Task` | Under `self.lock`: if task ID absent, creates new `Task` with state `SUBMITTED`, initial message in `history`. If present, appends message to `history`. Returns the task. |
| `update_store` | `(task_id: str, status: TaskStatus, artifacts: list[Artifact]) -> Task` | `Task` | Under `self.lock`: updates task status, appends `status.message` to history if present, extends `artifacts` list. Raises `ValueError` if task not found. |
| `append_task_history` | `(task: Task, historyLength: int \| None) -> Task` | `Task` | Pure function (no lock). Returns a `model_copy()` of the task with `history` truncated to last `historyLength` entries, or emptied if `historyLength` is `None` or `0`. |
| `set_push_notification_info` | `(task_id: str, notification_config: PushNotificationConfig) -> None` | `None` | Under `self.lock`: validates task exists, stores config. Raises `ValueError` if task not found. |
| `get_push_notification_info` | `(task_id: str) -> PushNotificationConfig` | `PushNotificationConfig` | Under `self.lock`: validates task exists, returns stored config. Raises `ValueError` if task not found. Raises `KeyError` if no config stored for task. |
| `has_push_notification_info` | `(task_id: str) -> bool` | `bool` | Under `self.lock`: checks if push notification config exists for task ID. |
| `setup_sse_consumer` | `(task_id: str, is_resubscribe: bool = False) -> asyncio.Queue` | `asyncio.Queue` | Under `subscriber_lock`: creates a new unlimited `asyncio.Queue`, appends it to `task_sse_subscribers[task_id]`. If `is_resubscribe=True` and task ID has no existing subscribers, raises `ValueError`. |
| `enqueue_events_for_sse` | `(task_id: str, task_update_event: TaskStatusUpdateEvent \| TaskArtifactUpdateEvent \| JSONRPCError) -> None` | `None` | Under `subscriber_lock`: fans out event to all subscriber queues for the task. No-op if no subscribers. |
| `dequeue_events_for_sse` | `(request_id: str \| int, task_id: str, sse_event_queue: asyncio.Queue) -> AsyncIterable[SendTaskStreamingResponse]` | `AsyncIterable` | Async generator. Reads events from queue, wraps each in `SendTaskStreamingResponse`. Terminates on `JSONRPCError` (yielded as error response) or `TaskStatusUpdateEvent` with `final=True`. On termination (including exceptions), removes the queue from `task_sse_subscribers[task_id]` under `subscriber_lock`. |

## Internal Design

### Task State Machine

```
                 ┌────────────────────────────────────────────────┐
                 │                                                │
                 ▼                                                │
          ┌─────────────┐                                         │
  ──────▶ │  SUBMITTED   │                                         │
          └──────┬──────┘                                         │
                 │                                                │
                 ▼                                                │
          ┌─────────────┐      ┌──────────────────┐               │
          │   WORKING    │─────▶│  INPUT_REQUIRED   │──────────────┘
          └──────┬──────┘      └──────────────────┘
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
  ┌──────────┐┌────────┐┌───────────┐
  │COMPLETED ││ FAILED ││ CANCELED  │
  └──────────┘└────────┘└───────────┘
```

States:
- **SUBMITTED** -- task created or message appended, awaiting agent pickup.
- **WORKING** -- agent is actively processing.
- **INPUT_REQUIRED** -- agent needs more input from user. Transitions back to SUBMITTED when user sends follow-up message via `on_send_task` / `on_send_task_subscribe`.
- **COMPLETED** -- agent finished successfully. Terminal.
- **FAILED** -- agent encountered an unrecoverable error. Terminal.
- **CANCELED** -- task was canceled by client request. Terminal.

The task manager does not enforce state transitions -- it stores whatever state the agent subclass sets via `update_store`. State validation is the agent subclass's responsibility.

### Concurrency Model

Two independent locks:
1. **`self.lock`** (asyncio.Lock) -- protects `self.tasks` and `self.push_notification_infos`. Acquired for every read/write to task state or push config. Fine-grained: held only for the dict operation, released before any I/O.
2. **`self.subscriber_lock`** (asyncio.Lock) -- protects `self.task_sse_subscribers`. Acquired when adding/removing subscribers or fanning out events. Separate from `self.lock` to avoid blocking task updates while broadcasting to SSE subscribers.

Both locks are `asyncio.Lock` (not `threading.Lock`) -- safe only within a single event loop. This aligns with the single-uvicorn-process deployment model.

### SSE Subscriber Lifecycle

```
1. Client calls on_send_task_subscribe (or on_resubscribe_to_task)
2. Subclass calls setup_sse_consumer(task_id) → asyncio.Queue
3. Subclass starts agent processing (may be background task)
4. Agent produces events → subclass calls enqueue_events_for_sse(task_id, event)
5. dequeue_events_for_sse reads from queue, yields SendTaskStreamingResponse
6. a2a_server wraps AsyncIterable in EventSourceResponse
7. Stream ends when:
   a. TaskStatusUpdateEvent with final=True is dequeued
   b. JSONRPCError is dequeued
   c. Client disconnects (EventSourceResponse handles cleanup)
8. finally block in dequeue_events_for_sse removes queue from subscriber list
```

Multiple clients can subscribe to the same task simultaneously. `enqueue_events_for_sse` fans out each event to all subscriber queues. Each subscriber has its own queue -- slow consumers do not block others (queues are unbounded).

### Upsert vs. Update

- **`upsert_task`** -- called at the start of `on_send_task` / `on_send_task_subscribe` by the subclass. Creates the task if new (state: `SUBMITTED`), or appends the user's message to history if existing.
- **`update_store`** -- called during/after agent processing to update state (`WORKING`, `COMPLETED`, `FAILED`, etc.) and add artifacts. Does not create tasks -- raises `ValueError` if the task is missing.

### History Truncation

`append_task_history` returns a shallow copy (`model_copy()`) of the task with history sliced to the last `historyLength` entries. This is applied on read (`on_get_task`) and does not mutate the stored task. When `historyLength` is `None` or `0`, the returned task has an empty history list -- the existing code intentionally omits history by default to reduce response size.

### Key Design Decisions

1. **Two abstract methods, not seven** -- `on_send_task` and `on_send_task_subscribe` are the only methods that need agent-specific logic. The remaining five (`on_get_task`, `on_cancel_task`, `on_set_task_push_notification`, `on_get_task_push_notification`, `on_resubscribe_to_task`) have sensible defaults in `InMemoryTaskManager`. Subclasses override only what they need.
2. **Cancel always returns `TaskNotCancelableError`** -- The in-memory manager has no mechanism to interrupt a running agent. Subclasses that support cancellation (e.g., via `asyncio.Task.cancel()`) override `on_cancel_task`.
3. **Resubscribe returns `UnsupportedOperationError`** -- Reconnecting to an existing SSE stream requires replaying missed events, which the in-memory implementation does not track. Subclasses may implement event journaling and override this method.
4. **Unbounded queues** -- `asyncio.Queue(maxsize=0)` means subscribers never block producers. Acceptable for v1 where the number of concurrent subscribers is small. A production implementation would add backpressure or bounded queues.
5. **`ValueError` for internal errors, `JSONRPCError` for wire errors** -- Helper methods (`set_push_notification_info`, `get_push_notification_info`, `update_store`) raise `ValueError` for "task not found" because they are internal. The `on_*` methods catch these and return `JSONRPCResponse` with `InternalError` or `TaskNotFoundError` for wire serialization.
6. **No state transition enforcement** -- The task manager is a storage layer, not a state machine engine. `update_store` accepts any `TaskStatus`. Agent subclasses are responsible for valid transitions. This keeps the manager generic across different agent behaviors.
7. **Separate locks for tasks vs. subscribers** -- Prevents SSE fanout from blocking task state updates. A slow `enqueue_events_for_sse` call (many subscribers) does not hold up `upsert_task` or `update_store`.
8. **`model_copy()` on read, not write** -- `append_task_history` copies the task before truncating history. The stored task always retains full history. This avoids data loss from concurrent reads with different `historyLength` values.

### Module Structure

```
synapticore/protocols/a2a_task_manager.py
    TaskManager (ABC)
        on_get_task(request) -> GetTaskResponse              [abstract]
        on_cancel_task(request) -> CancelTaskResponse        [abstract]
        on_send_task(request) -> SendTaskResponse             [abstract]
        on_send_task_subscribe(request) -> AsyncIterable | JSONRPCResponse  [abstract]
        on_set_task_push_notification(request) -> SetTaskPushNotificationResponse  [abstract]
        on_get_task_push_notification(request) -> GetTaskPushNotificationResponse  [abstract]
        on_resubscribe_to_task(request) -> AsyncIterable | JSONRPCResponse  [abstract]

    InMemoryTaskManager(TaskManager)
        __init__()
        on_get_task(request)                                  [concrete]
        on_cancel_task(request)                               [concrete]
        on_send_task(request)                                  [abstract -- subclass must override]
        on_send_task_subscribe(request)                        [abstract -- subclass must override]
        on_set_task_push_notification(request)                [concrete]
        on_get_task_push_notification(request)                [concrete]
        on_resubscribe_to_task(request)                       [concrete -- returns UnsupportedOperationError]
        upsert_task(task_send_params) -> Task                 [helper]
        update_store(task_id, status, artifacts) -> Task      [helper]
        append_task_history(task, historyLength) -> Task      [helper]
        set_push_notification_info(task_id, config) -> None   [helper]
        get_push_notification_info(task_id) -> PushNotificationConfig  [helper]
        has_push_notification_info(task_id) -> bool           [helper]
        setup_sse_consumer(task_id, is_resubscribe) -> Queue  [helper]
        enqueue_events_for_sse(task_id, event) -> None        [helper]
        dequeue_events_for_sse(request_id, task_id, queue) -> AsyncIterable  [helper]
```

### Preservation from Existing `task_manager.py`

The existing file at `Core/a2aPro/utils/task_manager.py` is ~277 lines and implements the full abstract + in-memory pattern. The rewrite preserves:

**Preserved as-is (patterns worth keeping):**
- `TaskManager` ABC with 7 abstract methods -- exact same contract the server dispatches to
- `InMemoryTaskManager` with separate `self.lock` and `self.subscriber_lock`
- `upsert_task` creates with state `SUBMITTED` on first send, appends message on subsequent sends
- `update_store` sets status, appends status message to history, extends artifacts
- `append_task_history` via `model_copy()` + slice for non-destructive history truncation
- `setup_sse_consumer` / `enqueue_events_for_sse` / `dequeue_events_for_sse` three-method SSE pattern
- `dequeue_events_for_sse` as async generator with `finally` cleanup
- Unbounded `asyncio.Queue(maxsize=0)` for subscriber queues
- `on_cancel_task` returns `TaskNotCancelableError` after verifying task exists
- `on_resubscribe_to_task` returns `UnsupportedOperationError` via `new_not_implemented_error`
- Push notification CRUD with task existence validation

**Cleanup in rewrite:**
- Move from `Core/a2aPro/utils/task_manager.py` to `synapticore/protocols/a2a_task_manager.py`
- Import from `synapticore.types.a2a_types` instead of bare `common_types`
- Remove `from server_utils import new_not_implemented_error` -- inline the `UnsupportedOperationError` response construction
- Replace bare `except Exception as e` in push notification handlers with specific `ValueError` / `KeyError` catches
- Add type annotations on all method parameters and return types (existing code has `Union` but missing some annotations)
- Replace `f"Task not found for {task_id}"` `ValueError` with structured logging context
- Add `__all__ = ["TaskManager", "InMemoryTaskManager"]` export
- Use `list[...]` and `dict[...]` lowercase generics consistently (existing code mixes `List` / `list`)
- Add module-level docstring

## Dependencies

### Internal
- `types/a2a_types` -- `Task`, `TaskState`, `TaskStatus`, `TaskSendParams`, `TaskQueryParams`, `TaskIdParams`, `Artifact`, `PushNotificationConfig`, `TaskPushNotificationConfig`, `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`, `JSONRPCResponse`, `JSONRPCError`, `GetTaskRequest`, `GetTaskResponse`, `SendTaskRequest`, `SendTaskResponse`, `SendTaskStreamingRequest`, `SendTaskStreamingResponse`, `CancelTaskRequest`, `CancelTaskResponse`, `SetTaskPushNotificationRequest`, `SetTaskPushNotificationResponse`, `GetTaskPushNotificationRequest`, `GetTaskPushNotificationResponse`, `TaskResubscriptionRequest`, `TaskNotFoundError`, `TaskNotCancelableError`, `InternalError`, `UnsupportedOperationError`

### External
- `asyncio` (stdlib -- `Lock`, `Queue`)
- `abc` (stdlib -- `ABC`, `abstractmethod`)
- `logging` (stdlib)
- `typing` (`Union`, `AsyncIterable`)

## Error Contracts

### Errors produced by this module (JSON-RPC error models -- returned in `JSONRPCResponse.error`, not raised)

| Method | Condition | JSON-RPC Error | Code |
|--------|-----------|----------------|------|
| `on_get_task` | Task ID not in store | `TaskNotFoundError` | -32001 |
| `on_cancel_task` | Task ID not in store | `TaskNotFoundError` | -32001 |
| `on_cancel_task` | Task exists but cancel not supported | `TaskNotCancelableError` | -32002 |
| `on_set_task_push_notification` | Internal failure (task not found, storage error) | `InternalError` | -32603 |
| `on_get_task_push_notification` | Internal failure (task not found, no config stored) | `InternalError` | -32603 |
| `on_resubscribe_to_task` | Not implemented | `UnsupportedOperationError` | -32004 |
| `dequeue_events_for_sse` | Error event received from agent | Passes through `JSONRPCError` from queue | varies |

### Errors raised internally (Python exceptions -- caught by `on_*` methods or propagated to `a2a_server`)

| Method | Exception | Condition |
|--------|-----------|-----------|
| `set_push_notification_info` | `ValueError` | Task ID not in store |
| `get_push_notification_info` | `ValueError` | Task ID not in store |
| `get_push_notification_info` | `KeyError` | No push config stored for existing task |
| `update_store` | `ValueError` | Task ID not in store |
| `setup_sse_consumer` | `ValueError` | `is_resubscribe=True` but task has no subscriber list |

## Test Plan

### Unit tests (`tests/unit/protocols/test_a2a_task_manager.py`)

**TaskManager ABC:**
- Cannot instantiate `TaskManager` directly (raises `TypeError`)
- Subclass implementing all 7 methods instantiates successfully
- Subclass missing any one abstract method raises `TypeError`

**InMemoryTaskManager construction:**
- `InMemoryTaskManager()` initializes with empty `tasks`, `push_notification_infos`, `task_sse_subscribers` dicts
- `lock` and `subscriber_lock` are distinct `asyncio.Lock` instances

**`upsert_task` -- new task:**
- Creates `Task` with given ID, state `SUBMITTED`, user message in `history`
- `sessionId` from `TaskSendParams` is preserved on the task
- Task is stored in `self.tasks[task_id]`
- Returns the created task

**`upsert_task` -- existing task:**
- Appends new message to existing task's `history`
- Does not overwrite task status
- Does not overwrite existing artifacts
- Returns the updated task

**`on_get_task` -- task exists:**
- Returns `GetTaskResponse` with `result` containing the task
- `historyLength=2` returns only last 2 history entries
- `historyLength=None` returns empty history
- `historyLength=0` returns empty history
- `historyLength` exceeding actual history returns full history
- Response `id` matches request `id`

**`on_get_task` -- task missing:**
- Returns `GetTaskResponse` with `error=TaskNotFoundError()`
- `result` is `None`

**`on_cancel_task` -- task exists:**
- Returns `CancelTaskResponse` with `error=TaskNotCancelableError()`
- Task state is not modified

**`on_cancel_task` -- task missing:**
- Returns `CancelTaskResponse` with `error=TaskNotFoundError()`

**`on_send_task` -- abstract:**
- `InMemoryTaskManager` does not implement `on_send_task` -- direct instantiation raises `TypeError`
- Subclass implementing `on_send_task` and `on_send_task_subscribe` instantiates successfully

**`on_send_task_subscribe` -- abstract:**
- Same verification as `on_send_task`

**`update_store`:**
- Updates task status to `WORKING`
- Updates task status to `COMPLETED`
- Appends `status.message` to history when message is present
- Does not append to history when `status.message` is `None`
- Extends artifacts list with new artifacts
- Creates artifacts list if `task.artifacts` was `None`
- Raises `ValueError` for unknown task ID

**`append_task_history`:**
- Returns a copy, not a reference to the original task
- Original task history is unmodified after call
- `historyLength=3` with 5 entries returns last 3
- `historyLength=None` returns empty list
- `historyLength=0` returns empty list
- `historyLength=10` with 3 entries returns all 3

**Push notification -- `on_set_task_push_notification`:**
- Stores config and returns `SetTaskPushNotificationResponse` with the config
- Returns `InternalError` response when task does not exist

**Push notification -- `on_get_task_push_notification`:**
- Returns stored config wrapped in `TaskPushNotificationConfig`
- Returns `InternalError` response when task does not exist
- Returns `InternalError` response when task exists but no config stored

**Push notification helpers:**
- `set_push_notification_info` raises `ValueError` for missing task
- `get_push_notification_info` raises `ValueError` for missing task
- `get_push_notification_info` raises `KeyError` for task with no config
- `has_push_notification_info` returns `True` / `False` correctly

**`on_resubscribe_to_task`:**
- Returns `JSONRPCResponse` with `UnsupportedOperationError`

**SSE -- `setup_sse_consumer`:**
- Creates new subscriber list for new task ID
- Appends queue to existing subscriber list for known task ID
- Returns an `asyncio.Queue` with `maxsize=0`
- `is_resubscribe=True` with unknown task ID raises `ValueError`
- `is_resubscribe=True` with known task ID appends new queue

**SSE -- `enqueue_events_for_sse`:**
- Enqueues event to all subscriber queues for the task
- No-op (no error) when task has no subscribers
- Multiple subscribers each receive the same event

**SSE -- `dequeue_events_for_sse`:**
- Yields `SendTaskStreamingResponse` with `result` for `TaskStatusUpdateEvent`
- Yields `SendTaskStreamingResponse` with `result` for `TaskArtifactUpdateEvent`
- Terminates after `TaskStatusUpdateEvent` with `final=True`
- Yields `SendTaskStreamingResponse` with `error` for `JSONRPCError`, then terminates
- Removes queue from `task_sse_subscribers` on normal termination
- Removes queue from `task_sse_subscribers` on error termination
- Removes queue from `task_sse_subscribers` on exception (finally block)
- `request_id` is propagated to each yielded `SendTaskStreamingResponse.id`

**Concurrency:**
- Two concurrent `upsert_task` calls for different task IDs both succeed
- Two concurrent `upsert_task` calls for the same task ID both append messages (no lost updates)
- `enqueue_events_for_sse` does not block while `update_store` holds `self.lock` (separate locks)
- `setup_sse_consumer` does not block while `upsert_task` holds `self.lock` (separate locks)

**Edge cases:**
- `upsert_task` with same task ID called 100 times -- history grows to 100 entries
- `update_store` with empty artifacts list does not add empty list to task
- `dequeue_events_for_sse` with queue that never receives an event -- blocks indefinitely (test with `asyncio.wait_for` timeout)
- Multiple subscribers: one consumer finishes (final event), others continue receiving events

## ADR References

- None pending. No framework choices -- pure stdlib asyncio + Pydantic types from `a2a_types`.

## Maturity

All functions: `stub` (rewrite target)
