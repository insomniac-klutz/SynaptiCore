# LLD: mcp_types

> Container: C1 (synapticore-core) | Subpackage: types/
> HLD Reference: S3 C1.1.3
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Thin wrapper over MCP SDK types with project-specific extensions (tool metadata tagging).

## Public API

| Class | Fields | Notes |
|-------|--------|-------|
| `McpToolDefinition` | `name: str`, `description: str`, `input_schema: dict[str, Any]`, `tags: list[str] \| None = None`, `category: str \| None = None` | Project-level tool metadata wrapper. `input_schema` is a JSON Schema dict. `tags` and `category` are SynaptiCore extensions for tool discovery and filtering (not part of MCP spec). |
| `McpToolResult` | `content: str \| dict[str, Any]`, `is_error: bool = False`, `error_message: str \| None = None` | Normalized tool execution result. Wraps the MCP SDK's tool result into a consistent shape for internal consumption by `tool_registry` and `mcp_server`. |
| `McpServerConfig` | `name: str`, `version: str`, `tools: list[McpToolDefinition] \| None = None` | Server-level configuration passed to FastMCP at startup. Defines the server identity and optionally pre-registers tools. |

## Internal Design

### Key Design Decisions

1. **Thin wrapper, not a fork** -- MCP SDK (`mcp[cli]`, `FastMCP`) already defines comprehensive types for the MCP protocol. This module does not re-implement MCP types. It provides three models that bridge MCP SDK types to SynaptiCore's internal type system.
2. **`McpToolDefinition` adds project metadata** -- The MCP spec defines tool name, description, and input schema. SynaptiCore adds `tags` (for filtering tools by capability, e.g. `["search", "web"]`) and `category` (for grouping in UI or agent tool selection). These fields are ignored when serializing to MCP wire format.
3. **`McpToolResult` normalizes output** -- MCP tool responses can vary in shape. This model provides a consistent `content` + `is_error` interface used by `tool_registry` and `mcp_server` to handle results uniformly.
4. **No MCP SDK import at type-definition time** -- The models are pure Pydantic. MCP SDK types are used in the `protocols/mcp_server` layer, which maps between `McpToolDefinition`/`McpToolResult` and MCP SDK types at runtime.

### Module structure

```
synapticore/types/mcp_types.py
    McpToolDefinition
    McpToolResult
    McpServerConfig
```

## Dependencies

### Internal
- None. This is a leaf module in `types/`.

### External
- `pydantic` (BaseModel)
- `typing` (Any)

Note: The `mcp` SDK is a dependency of `protocols/mcp_server`, not of this types module. Types are pure Pydantic.

## Error Contracts

### Defined by this module
- None. MCP error handling is the responsibility of `protocols/mcp_server`.

### Signaled via `McpToolResult`
- `is_error=True` with `error_message` set indicates a tool execution failure. This is a data contract, not an exception. The `mcp_server` translates this into an MCP-protocol error response.

### Raised implicitly
- `pydantic.ValidationError` on invalid model construction.

## Test Plan

### Unit tests (`tests/unit/types/test_mcp_types.py`)

**Model construction & validation:**
- `McpToolDefinition` constructs with required fields only (name, description, input_schema)
- `McpToolDefinition` constructs with optional `tags` and `category`
- `McpToolResult` constructs with string content
- `McpToolResult` constructs with dict content
- `McpToolResult` with `is_error=True` requires `error_message` to be meaningful (test convention, not validator)
- `McpServerConfig` constructs with name and version only
- `McpServerConfig` constructs with pre-registered tools list

**Serialization round-trip:**
- `model_dump()` -> `model_validate()` round-trip for all three models
- `McpToolDefinition.input_schema` preserves nested JSON Schema structure

**Edge cases:**
- `McpToolDefinition` with empty `input_schema` (`{}`)
- `McpToolDefinition` with empty `tags` list
- `McpToolResult` with empty string content
- `McpServerConfig` with empty tools list vs. `None` tools

## ADR References

- None pending. MCP types are spec-driven with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
