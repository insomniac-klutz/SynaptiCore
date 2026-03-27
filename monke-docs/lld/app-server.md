# LLD: app_server

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.7
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Main Starlette/FastAPI application. Single entry point (`uvicorn synapticore.main:app`). Startup sequence: load `.env` -> configure logging -> register tools -> wire agent executors -> mount sub-apps (`/a2a/`, `/mcp/`, `/agui/`). Replaces the current `SynaptiCore.Servers.mcpServer:main` entry point.

## Public API

### Application Factory

| Function | Signature | Returns | Notes |
|----------|-----------|---------|-------|
| `create_app` | `(settings: AppSettings \| None = None) -> Starlette` | `Starlette` | Application factory. Builds and returns the fully configured ASGI app. Accepts optional `AppSettings` override for testing; defaults to loading from environment. |

### Configuration Model

| Class | Fields | Notes |
|-------|--------|-------|
| `AppSettings` | `host: str = "0.0.0.0"`, `port: int = 8000`, `debug: bool = False`, `log_level: str = "INFO"`, `log_format: str = "json"`, `env_file: str = ".env"`, `cors_origins: list[str] = ["*"]` | Server-level settings. Loaded from env vars with `SYNAPTICORE_` prefix (e.g., `SYNAPTICORE_PORT=9000`). Not to be confused with `LlmConfig` (LLM settings) or per-provider secrets (Tavily, AWS, Snowflake). `debug` enables Starlette debug mode and sets log level to DEBUG. |

### HTTP Endpoints (direct -- not sub-app)

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/` | `{"name": "SynaptiCore", "version": str, "status": "ok"}` | Root health check. Returns package version from `importlib.metadata`. |
| GET | `/health` | `{"status": "ok", "uptime_seconds": float, "tools_registered": int, "agents_registered": int}` | Readiness probe. Reports tool/agent counts from registries. |

### Mounted Sub-Apps

| Sub-App | Mount Path | Source Component | Notes |
|---------|-----------|-----------------|-------|
| `a2a_server` | `/a2a/` | C1.3.1 | A2A JSON-RPC + agent card endpoint. All `/a2a/*` requests delegated. |
| `mcp_server` | `/mcp/` | C1.3.5 | FastMCP tool server. All `/mcp/*` requests delegated. |
| `agui_server` | `/agui/` | C1.3.6 | AG-UI run endpoint (SSE streaming). All `/agui/*` requests delegated. |

## Internal Design

### Startup Sequence

The startup sequence is implemented as a Starlette `lifespan` async context manager. The ordering is strict -- each phase depends on the previous phase completing.

```
Phase 1: Environment
  load_dotenv(env_file, override=True)
  AppSettings validated from env
  ↓
Phase 2: Logging
  configure_logging(settings.log_level, settings.log_format)
  stdlib logging configured with JSON formatter
  third-party loggers (litellm, httpx) set to WARNING+
  ↓
Phase 3: Tool Registration
  tool_registry.register_all_tools()
  Registers: web_search, calculator, snowflake_connector, pdf_processor
  Each tool registers its name, description, input_schema, handler
  Failures: log WARNING and skip (non-fatal -- missing API keys are OK at startup)
  ↓
Phase 4: Agent Initialization
  Create agent executors (decypher_agent, host_orchestrator)
  Each agent receives: LlmConfig (from env), tool_registry reference
  Failures: log ERROR and skip (non-fatal -- server starts without failing agents)
  ↓
Phase 5: Protocol Wiring
  Inject agent executors into agui_server (dependency injection, not import)
  Build a2a_server with task_manager and agent card config
  Build mcp_server from tool_registry
  ↓
Phase 6: Mount
  app.mount("/a2a/", a2a_app)
  app.mount("/mcp/", mcp_app)
  app.mount("/agui/", agui_app)
  ↓
Phase 7: Ready
  Log: "SynaptiCore ready on {host}:{port} — {n} tools, {m} agents"
  Store startup_time for /health uptime calculation

--- on shutdown ---

Phase 8: Cleanup
  Close httpx clients (a2a_client connections)
  Log: "SynaptiCore shutting down"
```

### Key Design Decisions

1. **Application factory pattern** -- `create_app()` returns a configured `Starlette` instance. This enables test code to create apps with overridden settings without touching environment variables or global state. The `synapticore.main:app` module-level binding calls `create_app()` once for uvicorn.
2. **Starlette, not FastAPI** -- The main app is a plain `Starlette` application. Sub-apps (particularly `mcp_server` via FastMCP) may use FastAPI internally. The main app only needs mount points, middleware, lifespan, and two simple routes -- FastAPI's dependency injection and OpenAPI generation are unnecessary overhead at this level.
3. **Lifespan context manager over on_event** -- Uses the modern `@asynccontextmanager` lifespan pattern instead of deprecated `@app.on_event("startup")`. Lifespan provides a clean shutdown path and can yield shared state to the app.
4. **Non-fatal tool/agent registration** -- The server starts even if individual tools or agents fail to initialize (e.g., missing Snowflake creds). This allows partial functionality during development. The `/health` endpoint reports what actually loaded.
5. **No import-time dependencies on agents/** -- Agent executors are created at startup and injected into `agui_server` as callables. The `app_server` module imports `agents/` only inside the lifespan function, not at module level. This preserves the dependency direction: `protocols/` does not depend on `agents/` at import time.
6. **CORS middleware for local dev** -- `CORSMiddleware` is always added with configurable origins. Defaults to `["*"]` for local development. Production deployments should restrict via `SYNAPTICORE_CORS_ORIGINS`.
7. **`AppSettings` is separate from `LlmConfig`** -- `AppSettings` governs the server process (host, port, logging). `LlmConfig` governs LLM calls. They are loaded from the same `.env` file but are distinct concerns with distinct consumers.
8. **Structured JSON logging** -- All `print()` statements in the legacy codebase are replaced with `logging.getLogger(__name__)` calls. The JSON formatter outputs `{"timestamp", "level", "logger", "message", ...}` for machine parsing. Debug mode falls back to human-readable format.

9. **Separate thread pools for A2A and AG-UI SSE (OQ-012)** -- A2A streaming responses and AG-UI SSE connections use separate `asyncio` task groups / thread pools to prevent one protocol's load from starving the other. The A2A server and AG-UI server each manage their own concurrency limits independently. This isolation ensures that a flood of AG-UI chat requests does not degrade A2A agent-to-agent communication, and vice versa.

10. **Env vars use LiteLLM-compatible names (OQ-032)** -- Provider credentials use standard LiteLLM env var names: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME` (for Bedrock), `GEMINI_API_KEY` (for Gemini), etc. The legacy misspelled `ANTRHOPIC_ACCESS_KEY_ID` / `ANTRHOPIC_SECRET_ACCESS_KEY` vars are dropped. LiteLLM reads these env vars directly -- no manual credential wiring needed in `app_server`. The `.env.template` should be updated to reflect the standard names.

11. **No google-adk / google-genai in startup dependencies** -- The startup sequence does not import or depend on `google-adk` or `google-genai`. The host orchestrator uses `llm_provider` (which wraps LiteLLM) for LLM reasoning, and `a2a_client` for agent communication. All Google-specific SDK dependencies are removed from the dependency chain.

### Module Structure

```
synapticore/main.py
    app = create_app()              # module-level for uvicorn

synapticore/protocols/app_server.py
    AppSettings                     # Pydantic BaseSettings
    create_app(settings?) -> Starlette
    _lifespan(app) -> AsyncContextManager
    _configure_logging(level, format)
    _register_tools(tool_registry)  # Phase 3
    _init_agents(tool_registry, llm_config) -> dict[str, AgentExecutor]  # Phase 4
    _build_health_response(startup_time, tool_registry, agent_map) -> dict
```

### Middleware Stack

Applied in order (outermost first):

| # | Middleware | Purpose |
|---|-----------|---------|
| 1 | `CORSMiddleware` | Cross-origin requests from `synapticore-ui` (C2) |
| 2 | `RequestLoggingMiddleware` (custom) | Log method, path, status, duration for every request. DEBUG level for `/health`, INFO for all others. |
| 3 | `ErrorHandlerMiddleware` (custom) | Catch unhandled exceptions at the top level. Log with traceback, return 500 JSON `{"error": "Internal Server Error"}`. Prevents raw tracebacks leaking to clients. |

### Agent Executor Registry

Agent executors are stored in a `dict[str, Callable]` mapping `agent_id -> executor_callable`. The executor callable signature:

```python
AgentExecutor = Callable[[list[ConversationMessage], str | None], AsyncIterator[AgUiEvent]]
```

- `messages`: conversation history
- `thread_id`: optional thread identifier for stateful agents
- Returns: async iterator of AG-UI events

This dict is passed to `agui_server` at startup. The `agui_server` resolves `agent_id` from `AgUiRunConfig.agent_id` against this registry.

### Logging Configuration Detail

```python
def _configure_logging(level: str, fmt: str) -> None:
    """
    Configure stdlib logging for the entire process.

    - Root logger: level from settings
    - synapticore.*: level from settings
    - litellm: WARNING (extremely verbose at INFO)
    - httpx: WARNING
    - httpcore: WARNING
    - uvicorn.access: WARNING (access logging handled by RequestLoggingMiddleware)
    """
```

JSON format output:
```json
{"timestamp": "2026-03-25T10:30:00.123Z", "level": "INFO", "logger": "synapticore.protocols.app_server", "message": "SynaptiCore ready on 0.0.0.0:8000 -- 4 tools, 2 agents"}
```

## Dependencies

### Internal

| Module | What it provides | Import timing |
|--------|-----------------|---------------|
| `protocols/a2a_server` | A2A Starlette sub-app | Startup (lifespan Phase 5) |
| `protocols/mcp_server` | MCP FastMCP sub-app | Startup (lifespan Phase 5) |
| `protocols/agui_server` | AG-UI Starlette sub-app | Startup (lifespan Phase 5) |
| `tools/tool_registry` | `register_all_tools()`, `get_tools()` | Startup (lifespan Phase 3) |
| `tools/llm_provider` | Used to build `LlmConfig` for agents | Startup (lifespan Phase 4) |
| `types/common_types` | `LlmConfig`, `ConfigurationError`, `ConversationMessage` | Startup (lifespan Phase 4) |
| `types/agui_types` | `AgUiEvent` (for executor type hint) | Type-level only |
| `agents/decypher_agent` | Agent executor factory | Startup (lifespan Phase 4) -- deferred import |
| `agents/host_orchestrator` | Agent executor factory | Startup (lifespan Phase 4) -- deferred import |

### External

| Package | Used for |
|---------|----------|
| `starlette` | ASGI app, routing, `Mount`, middleware, lifespan |
| `uvicorn` | ASGI server (runtime only -- not imported by app_server) |
| `python-dotenv` | `.env` file loading in Phase 1 |
| `pydantic-settings` | `AppSettings` (BaseSettings with env var prefix) |
| `logging` (stdlib) | Structured logging throughout |
| `importlib.metadata` (stdlib) | Package version for `/` endpoint |

## Error Contracts

### Defined by this module

| Error | When | Response |
|-------|------|----------|
| `ConfigurationError` | `AppSettings` validation fails (e.g., invalid `log_level`) | Process exits with error message to stderr. Not an HTTP error -- server does not start. |

### Handled by this module (from sub-apps)

| Error Source | Handling |
|-------------|----------|
| Unhandled exceptions from sub-apps | `ErrorHandlerMiddleware` catches, logs traceback, returns HTTP 500 JSON |
| Tool registration failure | Log WARNING, skip tool, continue startup |
| Agent initialization failure | Log ERROR, skip agent, continue startup |

### Raised implicitly

| Error | Trigger |
|-------|---------|
| `pydantic.ValidationError` | Invalid `AppSettings` construction (malformed env vars) |
| `FileNotFoundError` | `.env` file missing -- `load_dotenv` silently ignores, no error raised |
| `OSError` | Port already in use -- raised by uvicorn, not by `app_server` |

## Test Plan

### Unit tests (`tests/unit/protocols/test_app_server.py`)

**AppSettings:**
- Constructs with all defaults (no env vars set)
- `host` defaults to `"0.0.0.0"`, `port` defaults to `8000`
- `debug=True` is accepted
- `log_level` accepts valid levels: DEBUG, INFO, WARNING, ERROR
- `log_level` rejects invalid string (ValidationError)
- `cors_origins` accepts list of origin strings
- Settings load from env vars with `SYNAPTICORE_` prefix

**create_app:**
- Returns a `Starlette` instance
- Returned app has routes for `/` and `/health`
- Returned app has mount points for `/a2a/`, `/mcp/`, `/agui/`
- Accepts `AppSettings` override (does not read env)

**Health endpoint (`/health`):**
- Returns 200 with JSON body containing `status`, `uptime_seconds`, `tools_registered`, `agents_registered`
- `uptime_seconds` is a positive float
- `tools_registered` reflects actual tool count from registry
- `agents_registered` reflects actual agent count

**Root endpoint (`/`):**
- Returns 200 with JSON body containing `name`, `version`, `status`
- `name` is `"SynaptiCore"`
- `version` is a string (from package metadata)

**Logging configuration:**
- `_configure_logging("INFO", "json")` sets root logger to INFO
- `_configure_logging("DEBUG", "text")` sets root logger to DEBUG
- Third-party loggers (litellm, httpx) are set to WARNING regardless of app log level

**Error handling middleware:**
- Unhandled exception in route handler returns 500 JSON response
- Exception is logged with traceback

### Integration tests (`tests/integration/protocols/test_app_server_integration.py`)

**Full startup sequence (with test settings):**
- App starts with test `AppSettings` (no real `.env` needed)
- `/` returns 200
- `/health` returns 200 with correct tool/agent counts
- `/a2a/` mount responds (delegates to a2a_server)
- `/mcp/` mount responds (delegates to mcp_server)
- `/agui/` mount responds (delegates to agui_server)

**Partial startup (missing credentials):**
- App starts when Snowflake creds are missing (tool skipped, logged)
- App starts when Tavily key is missing (tool skipped, logged)
- `/health` reflects reduced tool count

**CORS:**
- Preflight OPTIONS request returns correct CORS headers
- `cors_origins` setting restricts allowed origins

**Graceful shutdown:**
- Lifespan cleanup runs (httpx clients closed)
- No resource leak warnings in logs

### Edge cases

- `create_app()` called twice returns two independent app instances (no shared global state)
- `AppSettings` with `debug=True` enables Starlette debug mode
- `.env` file does not exist -- app starts with defaults, logs warning
- Tool registration raises unexpected exception -- caught, logged, other tools still register
- Agent initialization raises unexpected exception -- caught, logged, other agents still initialize
- All tools fail to register -- app starts with 0 tools, `/health` reports `tools_registered: 0`
- All agents fail to initialize -- app starts with 0 agents, `/health` reports `agents_registered: 0`

## ADR References

- None pending. `app_server` uses only committed frameworks (Starlette, python-dotenv, Pydantic). No ADR/LATS gate required.

## Maturity

All functions: `stub` (rewrite target)
