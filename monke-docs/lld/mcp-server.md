# LLD: mcp_server

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.5
> Status: stub (rewrite -- not yet implemented)

## Responsibility

FastMCP server exposing tools from `tool_registry` as MCP-protocol endpoints. Mounted as a Starlette sub-app on the main server at `/mcp/`. Reads `tool_registry` at startup to register MCP tools. Translates `ToolExecutionError` and `ToolNotFoundError` into MCP error responses.

## Public API

### Factory Function

| Function | Signature | Notes |
|----------|-----------|-------|
| `create_mcp_app` | `(config: McpServerConfig, registry: ToolRegistry) -> Starlette` | Creates and returns a Starlette-mountable MCP sub-app. Reads all tools from `registry` via `to_mcp_definitions()`, registers each as a FastMCP tool, wires handler dispatch through `registry.execute_tool()`. The returned app is mounted by `app_server` at `/mcp/`. |

### Server Configuration

Uses `McpServerConfig` from `types/mcp_types`:

| Field | Source | Notes |
|-------|--------|-------|
| `name` | `McpServerConfig.name` | Server identity for MCP discovery (e.g., `"synapticore"`) |
| `version` | `McpServerConfig.version` | Server version for MCP discovery (e.g., `"1.0.0"`) |
| `tools` | Ignored -- tools come from `tool_registry` | `McpServerConfig.tools` is not used by `create_mcp_app`. All tools are sourced from the live registry. This field exists for static pre-registration in other use cases. |

### MCP Protocol Endpoints (provided by FastMCP)

FastMCP handles the MCP wire protocol. The module does not implement HTTP routes directly -- it configures FastMCP and lets it serve:

| MCP Operation | Description | Backed By |
|---------------|-------------|-----------|
| Tool discovery (`tools/list`) | Returns all registered tool definitions | `registry.to_mcp_definitions()` at registration time |
| Tool invocation (`tools/call`) | Executes a tool by name with arguments | `registry.execute_tool(name, arguments)` |

## Internal Design

### Key Design Decisions

1. **FastMCP does the heavy lifting** -- The MCP SDK (`mcp[cli]`) and FastMCP handle protocol serialization, transport (stdio, SSE, streamable-HTTP), and tool schema validation. This module is a thin bridge that populates FastMCP with tools from `tool_registry` and handles error translation. No custom protocol logic.
2. **Tool registration is a startup-time loop** -- `create_mcp_app` iterates `registry.to_mcp_definitions()` once and registers each tool with FastMCP. Tools are not dynamically added after startup. This matches the HLD constraint that the registry is populated at startup before the server accepts requests.
3. **Handler dispatch through `tool_registry.execute_tool()`** -- Each FastMCP tool handler is a closure that calls `await registry.execute_tool(tool_name, arguments)`. This preserves the registry's error-wrapping guarantee (all handler exceptions become `ToolExecutionError`). The MCP server never calls tool handlers directly.
4. **Error mapping is explicit** -- `ToolNotFoundError` maps to an MCP "tool not found" error. `ToolExecutionError` maps to an MCP "tool error" with the error message preserved. `SynaptiCoreError` (any other subclass) maps to an MCP internal error. Unexpected exceptions map to MCP internal error with a generic message (original error logged, not exposed to client).
5. **`McpToolResult` is the bridge type** -- `execute_tool()` returns `ToolResult` (from `common_types`). The handler wrapper converts this to `McpToolResult` before returning to FastMCP. When `ToolResult.is_error` is `True`, the result is translated to an MCP error response.
6. **No direct HTTP routing** -- Unlike `a2a_server` (which builds Starlette routes for JSON-RPC), `mcp_server` delegates all routing to FastMCP. The module configures FastMCP and returns its ASGI app for mounting.
7. **Starlette sub-app mounting** -- The returned app is a standard ASGI application. `app_server` mounts it at `/mcp/` via `app.mount("/mcp", mcp_app)`. FastMCP's transport layer (SSE or streamable-HTTP) operates under this prefix.

### Module Structure

```
synapticore/protocols/mcp_server.py
    create_mcp_app(config, registry) -> Starlette
    _register_tools(server, registry) -> None  [private]
    _make_tool_handler(registry, tool_name) -> Callable  [private]
    _tool_result_to_mcp(result) -> McpToolResult  [private]
    _handle_tool_error(error) -> McpToolResult  [private]
```

### Startup Flow

```
app_server (startup)
    │
    ├── registry = get_registry()
    ├── # ... register tools into registry ...
    │
    ├── mcp_config = McpServerConfig(name="synapticore", version="1.0.0")
    ├── mcp_app = create_mcp_app(config=mcp_config, registry=registry)
    │
    └── app.mount("/mcp", mcp_app)
```

### Tool Registration Flow (inside `create_mcp_app`)

```
create_mcp_app(config, registry)
    │
    ├── server = FastMCP(name=config.name, version=config.version)
    │
    ├── mcp_defs = registry.to_mcp_definitions()
    │   # Returns list[McpToolDefinition] -- all registered tools
    │
    ├── for tool_def in mcp_defs:
    │   ├── handler = _make_tool_handler(registry, tool_def.name)
    │   │   # Returns async closure: (arguments) -> McpToolResult
    │   │
    │   └── server.tool(
    │           name=tool_def.name,
    │           description=tool_def.description,
    │       )(handler)
    │       # Registers handler with FastMCP using the tool's JSON Schema
    │
    └── return server.sse_app()
        # Returns Starlette ASGI app for SSE transport
```

### Tool Invocation Flow (at request time)

```
External MCP Client
    │
    ├── tools/call { name: "web_search", arguments: { query: "..." } }
    │
    ├── FastMCP (deserialize, validate against input_schema)
    │
    ├── _make_tool_handler closure:
    │   ├── result = await registry.execute_tool("web_search", {"query": "..."})
    │   │   # registry handles: lookup → handler invocation → error wrapping
    │   │
    │   ├── if result.is_error:
    │   │   └── return _handle_tool_error(result)  # MCP error response
    │   │
    │   └── return _tool_result_to_mcp(result)  # MCP success response
    │
    └── FastMCP (serialize MCP response, send to client)
```

### Error Handling Flow

```
_make_tool_handler closure:
    │
    try:
    │   result = await registry.execute_tool(name, arguments)
    │   │
    │   ├── result.is_error == False → McpToolResult(content=result.content, is_error=False)
    │   └── result.is_error == True  → McpToolResult(content=result.content, is_error=True,
    │                                                  error_message=result.content)
    │
    except ToolNotFoundError as e:
    │   → McpToolResult(content="", is_error=True,
    │                    error_message=f"Tool not found: {e.tool_name}")
    │   + log WARNING
    │
    except ToolExecutionError as e:
    │   → McpToolResult(content="", is_error=True,
    │                    error_message=f"Tool execution failed: {e.message}")
    │   + log ERROR with e.details
    │
    except SynaptiCoreError as e:
    │   → McpToolResult(content="", is_error=True,
    │                    error_message="Internal server error")
    │   + log ERROR with full exception
    │
    except Exception as e:
        → McpToolResult(content="", is_error=True,
                         error_message="Internal server error")
        + log CRITICAL with full traceback
```

### Error-to-Protocol Mapping

Per the error mapping guide in `common_types`:

| Internal Error | MCP Response | Log Level |
|---------------|-------------|-----------|
| `ToolNotFoundError` | MCP tool not found error | WARNING |
| `ToolExecutionError` | MCP tool error (message preserved) | ERROR |
| `SynaptiCoreError` (other) | MCP internal error (generic message) | ERROR |
| `ToolResult.is_error == True` | MCP tool error (content as message) | WARNING |
| Unexpected `Exception` | MCP internal error (generic message) | CRITICAL |

### Conversion Functions

**`_tool_result_to_mcp(result: ToolResult) -> McpToolResult`**

```python
McpToolResult(
    content=result.content,
    is_error=result.is_error,
    error_message=result.content if result.is_error else None,
)
```

**`_handle_tool_error(error: Exception) -> McpToolResult`**

Maps caught exceptions to `McpToolResult` with `is_error=True`. See error handling flow above for mapping rules.

## Dependencies

### Internal
- `types/mcp_types` -- `McpToolDefinition`, `McpToolResult`, `McpServerConfig`
- `types/common_types` -- `ToolResult`, `ToolExecutionError`, `ToolNotFoundError`, `SynaptiCoreError`
- `tools/tool_registry` -- `ToolRegistry`, `get_registry`

### External
- `mcp[cli]` -- MCP SDK (protocol implementation)
- `mcp.server.fastmcp.FastMCP` -- High-level MCP server builder
- `starlette` -- ASGI app returned by FastMCP for sub-app mounting
- `logging` (stdlib)

## Error Contracts

### Raised by this module
- None. `mcp_server` does not raise exceptions to callers. All errors are caught internally and translated to MCP error responses (via `McpToolResult` with `is_error=True`).

### Caught and mapped by this module
- `ToolNotFoundError` -- from `registry.execute_tool()` when tool name is not registered. Mapped to MCP tool not found error.
- `ToolExecutionError` -- from `registry.execute_tool()` when the tool handler fails. Mapped to MCP tool error with message preserved.
- `SynaptiCoreError` -- catch-all for framework errors. Mapped to MCP internal error with generic message.
- `Exception` -- catch-all for unexpected errors. Mapped to MCP internal error with generic message. Logged at CRITICAL.

### Propagated from FastMCP
- FastMCP may raise transport-level errors (connection drops, malformed MCP requests). These are handled by FastMCP internally and do not surface to this module's code.

### Raised implicitly
- `pydantic.ValidationError` -- if `McpServerConfig` is constructed with invalid fields. This would occur at startup in `app_server`, not at request time.

## Test Plan

### Unit tests (`tests/unit/protocols/test_mcp_server.py`)

**Factory function -- `create_mcp_app`:**
- Returns a Starlette-compatible ASGI app (has `__call__` or is an ASGIApp)
- Registers all tools from a populated registry
- Handles empty registry (no tools registered) -- returns valid app with zero tools
- Uses `config.name` and `config.version` for FastMCP server identity

**Tool registration:**
- Each tool from registry appears as an MCP tool (verify via FastMCP introspection or tool discovery)
- Tool names match between registry and MCP registration
- Tool descriptions match between registry and MCP registration
- Multiple tools registered without error

**Tool invocation -- success path:**
- Invoke registered tool via MCP handler closure -- returns `McpToolResult` with correct content
- `McpToolResult.is_error` is `False` for successful execution
- `McpToolResult.content` matches the `ToolResult.content` returned by handler
- Handler receives correct `arguments` dict

**Tool invocation -- error paths:**
- `ToolResult.is_error == True` from handler -- `McpToolResult.is_error == True`, `error_message` set
- `ToolNotFoundError` from registry -- `McpToolResult.is_error == True`, error message contains tool name
- `ToolExecutionError` from registry -- `McpToolResult.is_error == True`, error message preserved
- `SynaptiCoreError` (other subclass) -- `McpToolResult.is_error == True`, generic error message
- Unexpected `Exception` -- `McpToolResult.is_error == True`, generic error message (original not leaked)

**Conversion functions:**
- `_tool_result_to_mcp` converts successful `ToolResult` to `McpToolResult` with `is_error=False`
- `_tool_result_to_mcp` converts error `ToolResult` (is_error=True) to `McpToolResult` with `is_error=True`
- `_tool_result_to_mcp` sets `error_message=None` for successful results
- `_tool_result_to_mcp` sets `error_message` from content for error results

**Logging:**
- `ToolNotFoundError` logged at WARNING
- `ToolExecutionError` logged at ERROR
- Unexpected exception logged at CRITICAL with traceback

**Edge cases:**
- Tool with empty `input_schema` (`{}`) registers and invokes successfully
- Tool handler returning `ToolResult` with empty string content
- Tool handler returning `ToolResult` with very large content string
- Multiple concurrent tool invocations (async -- verify no shared mutable state)
- Registry with tools that have `tags` and `category` -- metadata flows to MCP definition but does not affect invocation

### Integration tests (`tests/integration/protocols/test_mcp_server_integration.py`)

**End-to-end with real FastMCP transport:**
- Start MCP app, connect MCP client, discover tools, invoke a tool, verify result
- Tool discovery returns all registered tools with correct schemas
- Tool invocation with valid arguments returns expected result
- Tool invocation with invalid arguments returns MCP validation error (FastMCP handles)
- Tool invocation for non-existent tool returns MCP error

## ADR References

- None pending. MCP server uses the committed MCP SDK (`mcp[cli]`, FastMCP) per HLD framework policy. No framework choices required.

## Maturity

All functions: `stub` (rewrite target)
