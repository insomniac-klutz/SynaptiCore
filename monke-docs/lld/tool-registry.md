# LLD: tool_registry

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: tools/
> HLD Reference: S3 C1.2.6
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Central registry for all tools. Runtime singleton, populated at startup. Agents query it for available tools by name or filter. MCP server reads it to expose tools externally. Register via `ToolRegistration`, query via `get_tools()`, execute via `execute_tool()`.

## Public API

### Registration Types

| Class | Fields | Notes |
|-------|--------|-------|
| `ToolRegistration` | `name: str`, `description: str`, `input_schema: dict[str, Any]`, `handler: Callable[..., Awaitable[ToolResult]]`, `tags: list[str] \| None = None`, `category: str \| None = None`, `timeout_seconds: float \| None = None` | Everything needed to register a tool. `handler` is an async callable accepting a dict of arguments and returning a `ToolResult`. `name` must be unique across the registry. `tags` and `category` flow through to `McpToolDefinition` for MCP exposure and agent-side filtering. `input_schema` is a JSON Schema dict describing the tool's accepted arguments. `timeout_seconds` overrides the global 30s execution timeout for this tool (OQ-025); `None` means use the global default. |
| `ToolDefinition` | `name: str`, `description: str`, `input_schema: dict[str, Any]`, `tags: list[str] \| None = None`, `category: str \| None = None` | Read-only view of a registered tool — everything except the handler. Returned by query methods. Consumers (agents, MCP server) use this to discover tool metadata without accessing the callable directly. |

### Registry Class

| Method | Signature | Notes |
|--------|-----------|-------|
| `register` | `(self, registration: ToolRegistration) -> None` | Adds a tool to the registry. Raises `DuplicateToolError` if `registration.name` already exists. Idempotent-safe: callers should check before registering or catch `DuplicateToolError`. |
| `unregister` | `(self, name: str) -> None` | Removes a tool by name. Raises `ToolNotFoundError` if name is not registered. Used for testing and dynamic tool management. |
| `get_tool` | `(self, name: str) -> ToolDefinition` | Returns a single tool's definition. Raises `ToolNotFoundError` if not found. |
| `get_tools` | `(self, names: list[str] \| None = None, tags: list[str] \| None = None, category: str \| None = None) -> list[ToolDefinition]` | Returns tool definitions matching the filters. If `names` is provided, returns exactly those tools (raises `ToolNotFoundError` for any missing name). If `tags` is provided, returns tools matching any tag (OR semantics). If `category` is provided, returns tools in that category. Filters are AND-combined when multiple are specified. If all filters are `None`, returns all registered tools. |
| `execute_tool` | `(self, name: str, arguments: dict[str, Any]) -> ToolResult` | Looks up the handler for `name` and invokes it with `arguments` wrapped in `asyncio.wait_for` with a timeout (global 30s default, per-tool override via `ToolRegistration.timeout_seconds`, OQ-025). Raises `ToolNotFoundError` if the tool is not registered. Catches handler exceptions (including `asyncio.TimeoutError`) and wraps them in `ToolExecutionError`. Returns `ToolResult`. This is an async method. |
| `list_names` | `(self) -> list[str]` | Returns sorted list of all registered tool names. Cheap metadata query for logging and diagnostics. |
| `has_tool` | `(self, name: str) -> bool` | Returns `True` if the named tool is registered. Non-throwing check for conditional registration flows. |
| `clear` | `(self) -> None` | Removes all registered tools. Used in testing only. |
| `to_mcp_definitions` | `(self, names: list[str] \| None = None) -> list[McpToolDefinition]` | Converts registered tools to `McpToolDefinition` models for the MCP server. Calls `get_tools(names=names)` internally, then maps each `ToolDefinition` to an `McpToolDefinition` (carrying `tags` and `category` through). |

### Module-Level Singleton Access

| Function | Signature | Notes |
|----------|-----------|-------|
| `get_registry` | `() -> ToolRegistry` | Returns the module-level singleton `ToolRegistry` instance. Lazily created on first call. All consumers (agents, protocol servers, startup code) use this to access the same registry. |
| `reset_registry` | `() -> None` | Replaces the singleton with a fresh instance. Testing only — never call in production. |

## Internal Design

### Key Design Decisions

1. **Runtime singleton, not a service** -- The registry is a plain Python object, not a framework-managed dependency. A module-level singleton accessed via `get_registry()`. This avoids framework coupling and makes it testable (swap via `reset_registry()` in test fixtures).
2. **`ToolRegistration` vs. `ToolDefinition` split** -- Registration carries the handler callable; definition does not. Agents and MCP server receive `ToolDefinition` (metadata only). Only `execute_tool()` touches the handler. This prevents callers from bypassing the registry's error-wrapping and logging.
3. **Sync registration, async execution** -- `register()`, `unregister()`, `get_tools()` are synchronous (startup is synchronous, queries are fast dict lookups). `execute_tool()` is async because tool handlers (web search, Snowflake, PDF) are I/O-bound.
4. **Handler signature is `Callable[..., Awaitable[ToolResult]]`** -- All tool handlers must be async and return `ToolResult` from `common_types`. This ensures uniform error handling and result serialization across all tools, regardless of implementation.
5. **`to_mcp_definitions()` bridges tools/ and protocols/** -- MCP server should not depend on `ToolRegistration` internals. It calls `to_mcp_definitions()` which returns pure `McpToolDefinition` models. This keeps the dependency direction clean: `mcp_server → tool_registry → mcp_types`.
6. **`execute_tool` wraps handler exceptions** -- Any exception raised by a handler is caught and re-raised as `ToolExecutionError` with the original error message preserved. This guarantees that consumers (agents, protocol servers) only need to handle `ToolNotFoundError` and `ToolExecutionError`, never raw handler exceptions.
7. **Tag/category filtering uses OR within a filter, AND across filters** -- `get_tools(tags=["search", "web"])` returns tools tagged with "search" OR "web". `get_tools(tags=["search"], category="external")` returns tools tagged "search" AND in category "external". This matches typical agent tool selection patterns.
8. **No thread safety in v1** -- The registry is populated at startup before the server accepts requests. Concurrent reads are safe (dict lookups). Dynamic registration during request handling is not a v1 requirement. If needed later, a `threading.Lock` on `register`/`unregister` is sufficient.

9. **Global 30s timeout in `execute_tool` via `asyncio.wait_for`, per-tool override (OQ-025)** -- `execute_tool` wraps every handler invocation in `asyncio.wait_for(handler(arguments), timeout=timeout)`. The default timeout is 30 seconds. Individual tools can override this via an optional `timeout_seconds: float | None` field on `ToolRegistration`. When `timeout_seconds` is set on the registration, it takes precedence over the global default. On timeout, `asyncio.TimeoutError` is caught and wrapped in `ToolExecutionError` with `original_error="Tool '{name}' timed out after {timeout}s"`. This prevents runaway tool executions from blocking the agent loop indefinitely.

10. **Agents query registry per-request, no snapshot (OQ-031)** -- Agents call `get_tools()` on every request, not once at construction time. This means the tool set is always fresh -- if a tool is registered or unregistered after agent construction (e.g., during hot reload in development), the agent sees the change on the next request. No cached snapshot of tool definitions is held by agents. This is a conscious design choice: the registry is the single source of truth for available tools at all times.

### Module structure

```
synapticore/tools/tool_registry.py
    ToolRegistration (Pydantic model)
    ToolDefinition (Pydantic model)
    ToolRegistry (class)
        register(registration) -> None
        unregister(name) -> None
        get_tool(name) -> ToolDefinition
        get_tools(names?, tags?, category?) -> list[ToolDefinition]
        execute_tool(name, arguments) -> ToolResult  [async]
        list_names() -> list[str]
        has_tool(name) -> bool
        clear() -> None
        to_mcp_definitions(names?) -> list[McpToolDefinition]
    get_registry() -> ToolRegistry  [module-level]
    reset_registry() -> None  [module-level, testing only]
```

### Internal Storage

```python
class ToolRegistry:
    _tools: dict[str, _RegisteredTool]

@dataclass
class _RegisteredTool:
    definition: ToolDefinition
    handler: Callable[..., Awaitable[ToolResult]]
```

`_RegisteredTool` is a private dataclass pairing the public `ToolDefinition` with the internal handler. The `_tools` dict is keyed by tool name for O(1) lookup.

### Registration Flow

```
Startup code (app_server)
    │
    ├── from tool_registry import get_registry
    ├── registry = get_registry()
    │
    ├── registry.register(ToolRegistration(
    │       name="web_search",
    │       description="Search the web via Tavily or DuckDuckGo",
    │       input_schema={...},
    │       handler=web_search_handler,
    │       tags=["search", "web"],
    │       category="external"
    │   ))
    │
    ├── registry.register(ToolRegistration(...))  # calculator
    ├── registry.register(ToolRegistration(...))  # snowflake
    └── registry.register(ToolRegistration(...))  # pdf_processor
```

### Query & Execution Flow

```
Agent (decypher_agent)                    MCP Server (mcp_server)
    │                                         │
    ├── defs = registry.get_tools()           ├── mcp_defs = registry.to_mcp_definitions()
    │   (all tools for LLM tool defs)         │   (expose all as MCP tools)
    │                                         │
    ├── result = await registry               ├── (MCP client invokes tool)
    │       .execute_tool("web_search",       │
    │           {"query": "...", ...})         ├── result = await registry
    │                                         │       .execute_tool(tool_name, args)
    └── (use result in conversation)          └── (return McpToolResult)
```

## Dependencies

### Internal
- `types/common_types` -- `ToolResult`, `ToolNotFoundError`, `DuplicateToolError`, `ToolExecutionError`, `SynaptiCoreError`
- `types/mcp_types` -- `McpToolDefinition` (for `to_mcp_definitions()`)

### External
- `pydantic` (BaseModel, Field)
- `typing` (Any, Awaitable, Callable)
- `dataclasses` (dataclass -- for internal `_RegisteredTool`)
- `asyncio` (wait_for, TimeoutError -- for OQ-025 tool execution timeout)
- `logging` (stdlib)

## Error Contracts

### Raised by this module
- `DuplicateToolError` -- raised by `register()` when a tool name already exists. Contains `tool_name`.
- `ToolNotFoundError` -- raised by `get_tool()`, `get_tools(names=[...])`, `unregister()`, and `execute_tool()` when a requested tool name is not registered. Contains `tool_name`.
- `ToolExecutionError` -- raised by `execute_tool()` when the handler raises any exception or times out (OQ-025). Contains `tool_name` and `original_error` (stringified original exception message, or timeout description).

### Error wrapping in `execute_tool`

```
timeout = registered_tool.timeout_seconds or _DEFAULT_TIMEOUT  # 30s global default (OQ-025)
try:
    result = await asyncio.wait_for(handler(arguments), timeout=timeout)
except asyncio.TimeoutError:
    raise ToolExecutionError(
        tool_name=name,
        message=f"Tool '{name}' timed out after {timeout}s",
        original_error=f"Tool '{name}' timed out after {timeout}s"
    )
except SynaptiCoreError:
    raise  # ToolExecutionError from handler passes through unwrapped
except Exception as e:
    raise ToolExecutionError(
        tool_name=name,
        message=f"Tool '{name}' execution failed: {e}",
        original_error=str(e)
    ) from e
```

`SynaptiCoreError` subclasses (including `ToolExecutionError` raised by the handler itself) pass through without re-wrapping. All other exceptions are wrapped in `ToolExecutionError`.

### Raised implicitly
- `pydantic.ValidationError` on invalid `ToolRegistration` or `ToolDefinition` construction.

## Test Plan

### Unit tests (`tests/unit/tools/test_tool_registry.py`)

**Registration:**
- Register a tool successfully — `has_tool()` returns `True`, `list_names()` includes it
- Register with all fields (name, description, input_schema, handler, tags, category)
- Register with minimal fields (name, description, input_schema, handler only — tags/category default to `None`)
- `DuplicateToolError` raised on registering same name twice
- `DuplicateToolError` contains the duplicate `tool_name`

**Unregistration:**
- Unregister an existing tool — `has_tool()` returns `False`
- `ToolNotFoundError` raised when unregistering non-existent tool

**Query — get_tool:**
- Returns `ToolDefinition` for a registered tool
- `ToolDefinition` contains correct name, description, input_schema, tags, category
- `ToolNotFoundError` raised for non-existent tool name

**Query — get_tools:**
- Returns all tools when no filters provided
- Returns specific tools when `names` list provided
- `ToolNotFoundError` raised when any name in `names` list is missing
- Filters by single tag — returns tools with matching tag
- Filters by multiple tags (OR within tags) — returns tools matching any tag
- Filters by category — returns only tools in that category
- Combines tag and category filters (AND) — intersection of both
- Returns empty list when no tools match filter (but all names resolve)
- Returns empty list from empty registry (no filters)

**Query — to_mcp_definitions:**
- Returns `list[McpToolDefinition]` for all tools
- Each `McpToolDefinition` has correct name, description, input_schema, tags, category
- Accepts optional `names` filter — same semantics as `get_tools(names=...)`
- Raises `ToolNotFoundError` for missing name in filter

**Execution — execute_tool:**
- Successfully executes handler and returns `ToolResult`
- `ToolNotFoundError` raised for non-existent tool
- Handler returning `ToolResult(is_error=True)` passes through without exception
- Handler raising `ToolExecutionError` passes through unwrapped
- Handler raising generic `Exception` wrapped in `ToolExecutionError` with original message preserved
- Handler raising `ValueError` wrapped in `ToolExecutionError`
- `ToolExecutionError` contains correct `tool_name` and `original_error`
- Handler exceeding global 30s timeout raises `ToolExecutionError` with timeout message (OQ-025)
- Handler with per-tool `timeout_seconds=5` times out after 5s, not 30s (OQ-025)
- Handler with `timeout_seconds=None` uses global 30s default (OQ-025)

**Singleton:**
- `get_registry()` returns same instance on repeated calls
- `reset_registry()` produces a fresh instance
- Fresh instance has no registered tools

**Utility:**
- `list_names()` returns sorted list
- `list_names()` returns empty list from empty registry
- `has_tool()` returns `False` for non-existent tool
- `clear()` removes all tools — `list_names()` returns empty

**Serialization:**
- `ToolRegistration` round-trips via `model_dump()` / `model_validate()` (excluding handler — handler is `Callable`, not serializable; test that other fields survive)
- `ToolDefinition` round-trips via `model_dump()` / `model_validate()`

**Edge cases:**
- Register tool with empty `input_schema` (`{}`)
- Register tool with empty `tags` list (`[]`) vs. `None`
- Register tool with deeply nested `input_schema`
- `get_tools(names=[])` returns empty list (no names requested)
- `get_tools(tags=[])` returns all tools (empty tag filter = no filter)
- Handler that returns synchronously (should fail or be caught — handler must be async)
- Tool name with special characters (convention: lowercase, underscores)

## ADR References

- None pending. Tool registry is project-internal infrastructure with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
