# LLD: chat_view

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C2 (synapticore-ui) | Component: chat_view
> HLD Reference: S3 C2.2
> Status: stub (not yet implemented)

## Responsibility

React component rendering the conversational UI. Displays message bubbles (user and agent), tool call cards (name, arguments, result), streaming text indicators, step progress, and error displays. Consumes AG-UI events from `agui_client`. Emits user messages via HTTP POST through `agui_client`.

## Public API

### Component Exports

| Export | Type | Description |
|--------|------|-------------|
| `ChatView` | `React.FC<ChatViewProps>` | Top-level chat component. Renders the full conversation UI including message list, input area, and status indicators. |

### Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `agentId` | `string` | yes | Agent identifier passed to `AgUiRunConfig.agent_id` when initiating a run. |
| `apiBaseUrl` | `string` | yes | Base URL for the AG-UI backend (e.g., `http://localhost:8000`). Passed to `agui_client` for both SSE connection and HTTP POST. |
| `threadId` | `string \| undefined` | no | Existing thread ID for conversation continuity. If omitted, the backend generates one on `RunStartedEvent`. |
| `className` | `string \| undefined` | no | Optional CSS class applied to the root container for external styling. |

### Emitted Actions

| Action | Mechanism | Payload | Description |
|--------|-----------|---------|-------------|
| Send user message | HTTP POST `/agui/runs` via `agui_client` | `AgUiRunConfig` with `agent_id`, `messages` (full conversation history + new user message), `thread_id` | Initiates a new agent run. The `messages` array contains all prior messages (from local state) plus the new user message appended. |

### Rendered Elements

| Element | Trigger | Content |
|---------|---------|---------|
| User message bubble | Local state: user submitted a message | User text content, right-aligned |
| Agent message bubble | `TextMessageStartEvent` through `TextMessageEndEvent` | Streamed text content (assembled from `TextMessageContentEvent.delta` chunks), left-aligned |
| Tool call card | `ToolCallStartEvent` through `ToolCallEndEvent` | Tool name, arguments (streamed from `ToolCallArgsEvent.delta`), result (from `ToolCallEndEvent.result`) |
| Streaming indicator | `TextMessageStartEvent` received, `TextMessageEndEvent` not yet received | Animated typing indicator inside the active agent bubble |
| Tool call spinner | `ToolCallStartEvent` received, `ToolCallEndEvent` not yet received | Loading spinner on the active tool card with tool name |
| Step indicator | `StepStartedEvent` / `StepFinishedEvent` | Step name badge showing current agent processing step |
| Error display | `RunErrorEvent` | Inline error banner with `error_code` and `error_message`, plus a **retry button** that re-sends the last user message (OQ-016) |
| Run status | `RunFinishedEvent` | Visual run state (completed / error / cancelled) -- hidden on `COMPLETED`, shown on `ERROR` or `CANCELLED` |

## Internal Design

### Key Design Decisions

1. **Conversation state is local React state, not external store.** `ChatView` owns a `messages: ChatMessage[]` array in `useState`. No Redux, Zustand, or context provider. The component is self-contained. If state management needs grow beyond a single chat, this is the extraction point -- but v1 has one chat view.

2. **`agui_client` is consumed via `useAgui` hook.** A custom hook wraps `@ag-ui/client` to provide: `startRun(config)`, `cancelRun()`, and typed event callbacks. The hook manages SSE connection lifecycle (connect on `startRun`, disconnect on unmount or `RunFinishedEvent`). `ChatView` calls the hook and wires callbacks to state updates.

3. **Message model is a local union, not the protocol model.** `ChatMessage` (local) differs from `AgUiMessage` (protocol). Local messages carry rendering state (`isStreaming`, `toolCalls` with live argument accumulation). Protocol messages are snapshots. The `useAgui` hook translates incoming events into `ChatMessage` state updates.

4. **Tool call arguments are streamed, then parsed on completion.** `ToolCallArgsEvent.delta` chunks are concatenated into a raw string during streaming. On `ToolCallEndEvent`, the accumulated string is JSON-parsed for display. If parsing fails, the raw string is shown as-is (no crash on malformed JSON).

5. **Optimistic user message insertion.** When the user submits a message, it is immediately appended to local state and rendered. The HTTP POST to `/agui/runs` fires concurrently. If the POST fails, the message is marked with an error state (retry affordance). This avoids UI lag.

6. **Auto-scroll with escape hatch.** The message list auto-scrolls to the bottom on new content. If the user scrolls up (past a threshold), auto-scroll pauses until the user scrolls back to the bottom or clicks a "jump to bottom" affordance.

7. **No markdown rendering in v1.** Agent text is rendered as plain text with whitespace preserved (`white-space: pre-wrap`). Markdown rendering (code blocks, links, lists) is a post-v1 enhancement to avoid a library dependency decision now.

8. **Empty state and disabled input during run.** When no messages exist, a centered placeholder prompt is shown. While a run is active (`isRunning`), the input field is disabled to prevent overlapping runs (AG-UI does not support concurrent runs on the same thread).

9. **Retry button on RunErrorEvent (OQ-016).** When a `RunErrorEvent` is received, the error banner includes a "Retry" button. Clicking it re-sends the last user message by calling `useAgui.startRun()` with the same `AgUiRunConfig` (same conversation history, same agent_id). The error banner is removed when the retry run starts. This provides a one-click recovery path for transient errors (LLM timeouts, rate limits, etc.) without requiring the user to retype or copy-paste.

10. **Tabbed conversations -- multiple agui_client instances (OQ-030).** `ChatView` supports tabbed conversations. Each tab is an independent conversation with its own `thread_id`, message state, and `useAgui` hook instance. A `TabBar` component above the message list shows open conversations. Users can create new tabs (new thread), switch between tabs, and close tabs. Each tab's state is isolated -- a `RunErrorEvent` in one tab does not affect others. The tab model is a `Map<string, TabState>` where `TabState` contains the `messages` array, `runState`, `threadId`, and `useAgui` instance. Maximum 10 concurrent tabs to bound memory usage.

### Local Types

```typescript
// --- Local state types (not exported) ---

interface ChatMessage {
  id: string;                        // message_id from AG-UI events, or client-generated UUID for user messages
  role: "user" | "assistant";
  content: string;                   // Accumulated text content
  isStreaming: boolean;              // True while receiving TextMessageContentEvents
  toolCalls: ToolCallState[];        // Tool calls associated with this assistant message
  error?: string;                    // Set if user message POST failed
}

interface ToolCallState {
  id: string;                        // tool_call_id from ToolCallStartEvent
  name: string;                      // tool_call_name from ToolCallStartEvent
  argumentsRaw: string;             // Accumulated delta chunks from ToolCallArgsEvent
  argumentsParsed: Record<string, unknown> | null;  // JSON-parsed on ToolCallEndEvent, null while streaming
  result: string | null;             // From ToolCallEndEvent.result
  isComplete: boolean;               // True after ToolCallEndEvent received
}

type RunState = "idle" | "running" | "error" | "cancelled";
```

### Hook: `useAgui`

```typescript
function useAgui(apiBaseUrl: string): {
  startRun: (config: AgUiRunConfig) => void;
  cancelRun: () => void;
  runState: RunState;
  threadId: string | null;
  // Event callbacks -- ChatView wires these to state dispatch
  onRunStarted: (handler: (e: RunStartedEvent) => void) => void;
  onTextMessageStart: (handler: (e: TextMessageStartEvent) => void) => void;
  onTextMessageContent: (handler: (e: TextMessageContentEvent) => void) => void;
  onTextMessageEnd: (handler: (e: TextMessageEndEvent) => void) => void;
  onToolCallStart: (handler: (e: ToolCallStartEvent) => void) => void;
  onToolCallArgs: (handler: (e: ToolCallArgsEvent) => void) => void;
  onToolCallEnd: (handler: (e: ToolCallEndEvent) => void) => void;
  onStepStarted: (handler: (e: StepStartedEvent) => void) => void;
  onStepFinished: (handler: (e: StepFinishedEvent) => void) => void;
  onRunFinished: (handler: (e: RunFinishedEvent) => void) => void;
  onRunError: (handler: (e: RunErrorEvent) => void) => void;
};
```

### State Reducer Logic

`ChatView` uses `useReducer` for message state to handle the complex event-driven updates cleanly:

| Action | Triggered By | State Change |
|--------|-------------|-------------|
| `ADD_USER_MESSAGE` | User submits input | Append new `ChatMessage` with `role: "user"`, `isStreaming: false` |
| `USER_MESSAGE_FAILED` | HTTP POST error | Set `error` on the last user message |
| `START_ASSISTANT_MESSAGE` | `TextMessageStartEvent` | Append new `ChatMessage` with `role: "assistant"`, `isStreaming: true`, `content: ""` |
| `APPEND_TEXT_DELTA` | `TextMessageContentEvent` | Concatenate `delta` to the matching message's `content` |
| `END_ASSISTANT_MESSAGE` | `TextMessageEndEvent` | Set `isStreaming: false` on the matching message |
| `START_TOOL_CALL` | `ToolCallStartEvent` | Append a new `ToolCallState` to the current assistant message's `toolCalls` |
| `APPEND_TOOL_ARGS` | `ToolCallArgsEvent` | Concatenate `delta` to the matching tool call's `argumentsRaw` |
| `END_TOOL_CALL` | `ToolCallEndEvent` | Set `isComplete: true`, `result`, and attempt `argumentsParsed = JSON.parse(argumentsRaw)` |
| `SET_RUN_ERROR` | `RunErrorEvent` | Append an error display to the message list with retry button (OQ-016) |
| `RETRY_LAST_MESSAGE` | User clicks retry button | Remove error display, re-send last user message via `startRun()` (OQ-016) |
| `RESET_FOR_NEW_RUN` | `RunStartedEvent` | Set `runState` to `"running"`, store `thread_id` |
| `CREATE_TAB` | User clicks "new tab" | Create new `TabState` with fresh `thread_id` and empty messages (OQ-030) |
| `SWITCH_TAB` | User clicks a tab | Set active tab, swap visible message state (OQ-030) |
| `CLOSE_TAB` | User closes a tab | Remove `TabState`, cancel any active run in that tab (OQ-030) |

### Module Structure

```
synapticore-ui/src/
  components/
    ChatView/
      ChatView.tsx           -- Main component: layout, input, message list composition, tab management (OQ-030)
      ChatView.css            -- Component styles (plain CSS modules, no CSS-in-JS)
      MessageBubble.tsx       -- Single message bubble (user or assistant)
      ToolCallCard.tsx        -- Tool call card (name, args, result, spinner)
      StreamingIndicator.tsx  -- Animated typing indicator
      ErrorBanner.tsx         -- Inline error display with retry button (OQ-016)
      StepBadge.tsx           -- Step progress indicator
      TabBar.tsx              -- Tabbed conversation switcher (OQ-030)
      index.ts                -- Re-exports ChatView
  hooks/
    useAgui.ts               -- AG-UI client hook (SSE connection, event dispatch)
    useAutoScroll.ts         -- Auto-scroll logic with escape hatch
  types/
    chat.ts                  -- ChatMessage, ToolCallState, RunState, TabState local types
```

### Event Flow

```
User types message
  → ChatView dispatches ADD_USER_MESSAGE
  → ChatView calls useAgui.startRun({ agent_id, messages, thread_id })
    → useAgui POSTs to /agui/runs
    → useAgui opens SSE connection
      → RunStartedEvent         → RESET_FOR_NEW_RUN
      → TextMessageStartEvent   → START_ASSISTANT_MESSAGE
      → TextMessageContentEvent → APPEND_TEXT_DELTA (repeated)
      → ToolCallStartEvent      → START_TOOL_CALL
      → ToolCallArgsEvent       → APPEND_TOOL_ARGS (repeated)
      → ToolCallEndEvent        → END_TOOL_CALL
      → TextMessageContentEvent → APPEND_TEXT_DELTA (continued response)
      → TextMessageEndEvent     → END_ASSISTANT_MESSAGE
      → RunFinishedEvent        → runState = "idle"
```

### Rendering Rules

1. **Message ordering.** Messages render in array order (chronological). User messages right-aligned, assistant messages left-aligned.
2. **Tool calls are nested inside assistant messages.** A `ToolCallStartEvent` with `parent_message_id` attaches the tool call to that assistant message. If `parent_message_id` is null, the tool call attaches to the most recent assistant message.
3. **Multiple tool calls per message.** An assistant message can contain multiple tool calls (parallel tool use). Each renders as a separate card within the message bubble.
4. **Streaming text and tool calls interleave.** The agent may stream text, invoke a tool, then stream more text. All attach to the same assistant message (matched by `message_id`). The UI renders them in event order: text block, tool card, text block.
5. **Error banner placement.** `RunErrorEvent` renders an error banner below the last message in the list, not as a message bubble.

## Dependencies

### Internal
- `useAgui` hook (C2.1 `agui_client` wrapper) -- SSE event stream consumption, HTTP POST for user messages

### External
- `react` (18.x) -- component framework
- `@ag-ui/core` -- AG-UI event type definitions (used by `useAgui` hook)
- `@ag-ui/client` -- AG-UI client SDK (used by `useAgui` hook)

## Error Contracts

### Errors handled by this component

| Error Source | Detection | UI Response |
|-------------|-----------|-------------|
| `RunErrorEvent` from SSE | `onRunError` callback | Render `ErrorBanner` with `error_code`, `error_message`, and retry button (OQ-016). Set `runState` to `"error"`. Re-enable input. |
| HTTP POST failure (user message) | `fetch` / `@ag-ui/client` throws | Mark user message with `error` state. Show retry affordance on the message bubble. Do not open SSE connection. |
| SSE connection drop | `useAgui` detects `EventSource` close without `RunFinishedEvent` | Render `ErrorBanner` with connection error. Set `runState` to `"error"`. Re-enable input. |
| Malformed `ToolCallArgsEvent` JSON | `JSON.parse` fails in `END_TOOL_CALL` reducer | Set `argumentsParsed` to `null`. Render raw `argumentsRaw` string in the tool card instead of formatted JSON. No crash. |

### Errors NOT handled here (upstream responsibility)
- `pydantic.ValidationError` on `AgUiRunConfig` -- `agui_server` returns HTTP 400
- Agent execution failures -- `agui_server` emits `RunErrorEvent`
- SSE framing errors -- `@ag-ui/client` SDK handles reconnection / error events

## Test Plan

### Unit tests (`synapticore-ui/src/components/ChatView/__tests__/`)

**ChatView rendering:**
- Renders empty state placeholder when no messages
- Renders user message bubble after submission
- Renders assistant message bubble from TextMessageStart/Content/End sequence
- Renders tool call card from ToolCallStart/Args/End sequence
- Renders multiple messages in chronological order
- Renders error banner on RunErrorEvent
- Input is disabled while `runState` is `"running"`
- Input is re-enabled after `RunFinishedEvent`

**MessageBubble:**
- User message renders right-aligned with user content
- Assistant message renders left-aligned with streamed content
- Streaming assistant message shows StreamingIndicator
- Completed assistant message hides StreamingIndicator

**ToolCallCard:**
- Renders tool name during streaming (before ToolCallEndEvent)
- Shows spinner while tool call is in progress
- Renders parsed arguments as formatted JSON on completion
- Renders raw arguments string when JSON parse fails
- Renders result text after ToolCallEndEvent
- Renders "no result" indicator when `result` is null

**ErrorBanner:**
- Renders error_code and error_message
- Renders retry button alongside error (OQ-016)
- Clicking retry button dispatches RETRY_LAST_MESSAGE (OQ-016)
- Retry button is disabled while `runState` is `"running"` (OQ-016)
- Renders connection error message on SSE drop

**StepBadge:**
- Renders step name on StepStartedEvent
- Hides on StepFinishedEvent

**useAgui hook:**
- `startRun` sends POST to correct URL with AgUiRunConfig payload
- `cancelRun` closes SSE connection
- Event callbacks fire for each AG-UI event type
- `runState` transitions: idle -> running -> idle on RunFinishedEvent
- `runState` transitions: idle -> running -> error on RunErrorEvent
- `threadId` is set from RunStartedEvent
- Cleanup closes SSE connection on unmount

**useAutoScroll hook:**
- Auto-scrolls to bottom on new content
- Pauses auto-scroll when user scrolls up
- Resumes auto-scroll when user scrolls to bottom

**State reducer:**
- ADD_USER_MESSAGE appends user message
- START_ASSISTANT_MESSAGE appends streaming assistant message
- APPEND_TEXT_DELTA concatenates to correct message by id
- END_ASSISTANT_MESSAGE sets isStreaming to false
- START_TOOL_CALL appends tool call to current assistant message
- APPEND_TOOL_ARGS concatenates to correct tool call by id
- END_TOOL_CALL sets isComplete, result, and attempts JSON parse
- SET_RUN_ERROR appends error state with retry capability (OQ-016)
- RETRY_LAST_MESSAGE removes error, re-sends last user message (OQ-016)
- CREATE_TAB creates new isolated tab state (OQ-030)
- SWITCH_TAB swaps active message list (OQ-030)
- CLOSE_TAB removes tab state and cancels active run (OQ-030)
- USER_MESSAGE_FAILED sets error on last user message

**Integration tests:**
- Full event sequence (RunStarted -> TextMessageStart -> TextMessageContent * N -> TextMessageEnd -> RunFinished) produces correct rendered output
- Tool call interleaved with text produces correct message structure
- Multiple sequential user-agent exchanges maintain conversation history
- POST payload contains full message history (not just latest message)

**Edge cases:**
- Rapid TextMessageContentEvent deltas (batched renders via React)
- RunErrorEvent received mid-stream (partial message displayed with error)
- Empty delta string in TextMessageContentEvent (no-op, no crash)
- ToolCallEndEvent with null result
- Multiple concurrent ToolCallStartEvents (parallel tool calls)
- User submits empty string (rejected by input validation, no POST)
- Component unmount during active SSE stream (cleanup, no leak)

## ADR References

- None pending. React 18 and AG-UI SDKs are committed stack per HLD S2. No framework choice gates.

## Maturity

All functions: `stub` (not yet implemented)
