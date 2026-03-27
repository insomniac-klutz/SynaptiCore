# LLD: app_shell

> Container: C2 (synapticore-ui) | Component: app_shell
> HLD Reference: S3 C2.3
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Top-level React application shell. Vite entry point. Provides layout structure, error boundary, and configuration. Hosts `chat_view` as the primary content area.

## Public API

### Components

| Component | Props | Notes |
|-----------|-------|-------|
| `AppShell` | None | Root component. Rendered by Vite entry (`main.tsx`). Wraps `ChatView` in layout and error boundary. Reads `VITE_API_BASE_URL` from Vite env for AG-UI backend connection. |
| `ErrorBoundary` | `children: ReactNode`, `fallback?: ReactNode` | React error boundary. Catches render errors in the component tree below it. Displays a fallback UI with error message and retry action. Logs caught errors to `console.error`. |

### Configuration

| Env Var | Type | Default | Notes |
|---------|------|---------|-------|
| `VITE_API_BASE_URL` | `string` | `"http://localhost:8000"` | Base URL for the backend server. Used to construct AG-UI endpoint URLs (e.g., `${VITE_API_BASE_URL}/agui/runs`). Set via `.env` or `.env.local` in the Vite project root. |

### Exports

| Export | Type | Notes |
|--------|------|-------|
| `AppShell` | React component | Default export from `src/App.tsx` |
| `ErrorBoundary` | React component | Named export from `src/components/ErrorBoundary.tsx` |
| `apiBaseUrl` | `string` | Resolved `VITE_API_BASE_URL` -- single source of truth for all components needing the backend URL |

## Internal Design

### Key Design Decisions

1. **Minimal shell** -- `AppShell` is a thin layout wrapper. All conversational UI logic lives in `chat_view`. The shell provides structure (header, main area, potential sidebar slot) but no business logic.
2. **Error boundary at the root** -- A single `ErrorBoundary` wraps the entire `ChatView` subtree. Render errors anywhere in the chat UI are caught and displayed gracefully instead of white-screening. This is a class component (React error boundaries require `componentDidCatch`).
3. **Centralized config resolution** -- `VITE_API_BASE_URL` is read once in a config module (`src/config.ts`) and exported as `apiBaseUrl`. No component reads `import.meta.env` directly. This makes the backend URL injectable for tests and mockable for Storybook.
4. **No routing in v1** -- Single-view app. `ChatView` is the only view. React Router is not needed. If additional views are added post-v1, the shell gains a router at that point.
5. **No global state management** -- No Redux, Zustand, or Context-based state store. `chat_view` manages its own state via `agui_client`. The shell passes only the `apiBaseUrl` config down.

### Module structure

```
src/
    main.tsx              # Vite entry. ReactDOM.createRoot → <AppShell />
    App.tsx               # AppShell component. Layout + ErrorBoundary + ChatView
    config.ts             # Reads VITE_API_BASE_URL, exports apiBaseUrl
    components/
        ErrorBoundary.tsx # Class component error boundary
```

### Layout structure

```
<AppShell>
    <header>              <!-- App title / branding bar -->
    <ErrorBoundary>
        <main>
            <ChatView apiBaseUrl={apiBaseUrl} />
        </main>
    </ErrorBoundary>
</AppShell>
```

## Dependencies

### Internal
- `C2.2 chat_view` -- `ChatView` component rendered as primary content

### External
- `react` (18.x) -- Component rendering, hooks
- `react-dom` (18.x) -- DOM mounting (`createRoot`)
- `vite` -- Build tool, dev server, env variable injection (`import.meta.env`)
- `typescript` -- Type safety

## Error Contracts

### Defined by this module
- `ErrorBoundary` catches render-time exceptions from child components. Displays a fallback UI with the error message and a "Retry" button that calls `window.location.reload()`.

### Not handled here
- Network errors from AG-UI connections are handled by `agui_client` / `chat_view`, not the error boundary (they are async, not render-time errors).
- Backend configuration errors (wrong URL, unreachable server) surface as connection failures in `agui_client`.

## Test Plan

### Unit tests (`tests/unit/ui/test_app_shell.tsx`)

**AppShell rendering:**
- Renders without crashing
- Contains a header element with app title
- Contains a `ChatView` component
- Passes `apiBaseUrl` to `ChatView`

**ErrorBoundary:**
- Renders children when no error occurs
- Displays fallback UI when a child throws during render
- Fallback UI contains the error message text
- Retry button triggers page reload
- `componentDidCatch` is called with error and error info

**Configuration:**
- `apiBaseUrl` defaults to `"http://localhost:8000"` when `VITE_API_BASE_URL` is not set
- `apiBaseUrl` reads from `VITE_API_BASE_URL` when set
- `apiBaseUrl` strips trailing slash if present

**Edge cases:**
- `ErrorBoundary` handles errors thrown during event handlers (these are NOT caught -- verify no false positive)
- Multiple rapid re-renders do not cause layout thrashing

## ADR References

- None pending. Standard React + Vite patterns with no framework choices beyond the committed stack.

## Maturity

All functions: `stub` (rewrite target)
