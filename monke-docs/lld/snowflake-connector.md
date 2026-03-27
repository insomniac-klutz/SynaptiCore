# LLD: snowflake_connector

> Updated: 2026-03-26 — OQ resolutions applied

> Container: C1 (synapticore-core) | Subpackage: tools/
> HLD Reference: S3 C1.2.4
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Parameterized SQL execution against Snowflake, connection pooling, credential validation, and result serialization. Replaces the legacy `serverSnowflake.py` + `genFuncs.create_connection` combo which used raw SQL injection-vulnerable queries and per-call connection creation.

**OQ-004 resolved: Pandas required for result formatting.** The `pandas` library is a required dependency for result serialization. Results are fetched via `cursor.fetchall()` and converted through `pd.DataFrame(rows).to_dict(orient="records")` for consistent type handling (datetime, Decimal, etc.) and optional downstream DataFrame-based analysis by agents. The serialization seam at step 7 in the execution flow uses the Pandas path.

## Public API

### Configuration Model

| Class | Fields | Notes |
|-------|--------|-------|
| `SnowflakeConfig` | `user: str`, `password: SecretStr`, `account: str`, `warehouse: str`, `database: str`, `role: str`, `host: str`, `port: int = 443`, `schema_name: str = "PUBLIC"`, `login_timeout: int = 30`, `network_timeout: int = 60` | Loaded from env vars at startup. `password` is `pydantic.SecretStr` -- never logged or serialized to plain text. `schema_name` defaults to `PUBLIC` (Snowflake default). `port` defaults to 443 (Snowflake standard HTTPS). Validated on construction -- raises `ConfigurationError` if any required field is empty/missing. |

### Env Var Mapping

| Env Var | Field | Required |
|---------|-------|----------|
| `SNOWFLAKE_DB_USER` | `user` | Yes |
| `SNOWFLAKE_DB_PASSWORD` | `password` | Yes |
| `SNOWFLAKE_DB_ACCOUNT` | `account` | Yes |
| `SNOWFLAKE_DB_WAREHOUSE` | `warehouse` | Yes |
| `SNOWFLAKE_DB_DBNAME` | `database` | Yes |
| `SNOWFLAKE_DB_ROLE` | `role` | Yes |
| `SNOWFLAKE_DB_HOST` | `host` | Yes |
| `SNOWFLAKE_DB_PORT` | `port` | No (default 443) |

Note: `SNOWFLAKE_DB_SCHEMA` is not in `.env.template` today. If needed, add it. Otherwise `schema_name` defaults to `PUBLIC`.

### Input / Output Contracts

| Class | Fields | Notes |
|-------|--------|-------|
| `SnowflakeQuery` | `sql: str`, `params: dict[str, Any] \| None = None`, `timeout_seconds: int = 30` | `sql` is the query string with optional `%(name)s` placeholders for parameterized execution (Snowflake `pyformat` binding style). `params` is the name-value dict for those placeholders. `timeout_seconds` is the per-query statement timeout passed to the cursor. |
| `SnowflakeResult` | `columns: list[str]`, `rows: list[dict[str, Any]]`, `row_count: int`, `execution_time_ms: float` | `columns` is the ordered list of column names from `cursor.description`. `rows` is a list of dicts keyed by column name. `row_count` is `len(rows)`. `execution_time_ms` is wall-clock time for the execute + fetch cycle. |

### Handler Function

| Function | Signature | Notes |
|----------|-----------|-------|
| `execute_query` | `async (query: SnowflakeQuery) -> SnowflakeResult` | The tool handler registered with `tool_registry`. Acquires a connection from the pool, executes the parameterized query, serializes results, returns `SnowflakeResult`. All Snowflake SDK calls are synchronous -- wrapped with `asyncio.to_thread` to avoid blocking the event loop. |

### Lifecycle Functions

| Function | Signature | Notes |
|----------|-----------|-------|
| `load_config` | `() -> SnowflakeConfig` | Reads env vars, constructs and validates `SnowflakeConfig`. Raises `ConfigurationError` on missing/invalid values. Called once at startup. |
| `init_pool` | `(config: SnowflakeConfig) -> None` | Initializes the module-level connection pool. Must be called before `execute_query`. Idempotent -- second call is a no-op if pool already exists. |
| `close_pool` | `() -> None` | Closes all connections in the pool. Called at shutdown. Safe to call multiple times. |

## Internal Design

### Connection Pooling

The legacy code creates a new `snowflake.connector.connect()` per query and closes it immediately after. This is expensive -- Snowflake connections involve TLS handshake + authentication.

**Rewrite approach:** Module-level connection pool using a bounded `asyncio.Queue[snowflake.connector.SnowflakeConnection]` of pre-authenticated connections.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `pool_size` | 3 | Single-process server with moderate concurrency. 3 connections cover parallel tool invocations without exhausting Snowflake session limits. |
| Acquire timeout | 10 seconds | If all 3 connections are busy for 10s, raise `ToolExecutionError` rather than queue indefinitely. |
| Health check | `cursor.execute("SELECT 1")` before returning from pool | Snowflake connections can go stale. Cheap health check avoids returning dead connections. Reconnect if stale. |

```
Pool lifecycle:
  init_pool(config)
    → create pool_size connections
    → put all into asyncio.Queue

  acquire()
    → Queue.get(timeout=10)
    → health check (SELECT 1)
    → if stale: reconnect, return fresh
    → return connection

  release(conn)
    → Queue.put(conn)

  close_pool()
    → drain queue
    → conn.close() for each
```

### Query Execution Flow

```
execute_query(SnowflakeQuery)
  1. Validate: sql is non-empty, params keys match placeholders (best-effort)
  2. Acquire connection from pool (via asyncio.to_thread for sync acquire)
  3. Create cursor with timeout: cursor = conn.cursor(DictCursor)
  4. cursor.execute(sql, params)  -- parameterized, no string interpolation
  5. Fetch: rows = cursor.fetchall()
  6. Extract columns from cursor.description
  7. Serialize rows to list[dict[str, Any]] via pd.DataFrame(rows).to_dict(orient="records") (OQ-004 resolved)
  8. Compute execution_time_ms
  9. Release connection back to pool
  10. Return SnowflakeResult(columns, rows, row_count, execution_time_ms)

  On error at any step:
    - Release connection back to pool (finally block)
    - Wrap in ToolExecutionError(tool_name="snowflake_connector", original_error=str(e))
```

### Key Design Decisions

1. **Parameterized queries only** -- `cursor.execute(sql, params)` uses Snowflake's server-side binding. No string interpolation, no f-strings, no `.format()`. This eliminates SQL injection. The legacy `pd.read_sql(sql_query, conn)` accepted raw SQL strings with no parameterization.

2. **`asyncio.to_thread` wrapper** -- `snowflake-connector-python` is synchronous. All blocking calls (`connect`, `execute`, `fetchall`) are wrapped in `asyncio.to_thread` so the event loop is never blocked. The tool handler is `async def` to match the `tool_registry` async handler contract.

3. **`DictCursor` for native dict rows** -- Snowflake connector provides `DictCursor` which returns rows as dicts keyed by column name. This avoids manual column-to-value mapping and produces the `list[dict[str, Any]]` contract directly.

4. **Pandas serialization (OQ-004 resolved)** -- Step 7 in the flow uses `pd.DataFrame(cursor.fetchall()).to_dict(orient="records")` for result serialization. Pandas handles type coercion (Decimal to float, datetime to ISO string) and provides a consistent dict structure. The `SnowflakeResult` contract is unchanged -- only the internal serialization uses Pandas. `pandas` is a required external dependency of this module.

5. **`SecretStr` for password** -- Prevents accidental logging of credentials. `SnowflakeConfig.password.get_secret_value()` is called only at connection creation time.

6. **Pool not exposed** -- The pool is module-internal. Callers interact only with `execute_query`, `init_pool`, `close_pool`. No connection leaking to consumers.

7. **Health check on acquire, not on release** -- Checking on acquire catches stale connections before they cause query failures. Checking on release would waste cycles on connections that might sit idle and go stale anyway.

### Module Structure

```
synapticore/tools/snowflake_connector.py
    SnowflakeConfig          (Pydantic BaseModel)
    SnowflakeQuery           (Pydantic BaseModel)
    SnowflakeResult          (Pydantic BaseModel)
    load_config()            -> SnowflakeConfig
    init_pool(config)        -> None
    close_pool()             -> None
    execute_query(query)     -> SnowflakeResult   [async, tool handler]
    _acquire()               -> SnowflakeConnection  [internal]
    _release(conn)           -> None                  [internal]
    _health_check(conn)      -> bool                  [internal]
    _create_connection(config) -> SnowflakeConnection [internal]
```

### SQL Safety Rules

The handler enforces these constraints before execution:

| Rule | Enforcement | Rationale |
|------|-------------|-----------|
| No empty SQL | Validate `sql.strip()` is non-empty | Prevent sending empty queries to Snowflake |
| Parameterized binding | `cursor.execute(sql, params)` -- never `cursor.execute(sql % params)` | SQL injection prevention |
| Statement timeout | `cursor.execute` with `timeout=query.timeout_seconds` | Prevent runaway queries from holding connections |
| Single-statement only | Not enforced in v1 | Snowflake connector handles multi-statement mode. Consider restricting to single-statement in future if agents generate risky SQL. |

## Dependencies

### Internal
- `types/common_types` -- `ToolExecutionError`, `ConfigurationError`, `SynaptiCoreError`

### External
- `snowflake-connector-python` (3.13.2) -- Snowflake database connector
- `pandas` -- Result formatting via `pd.DataFrame().to_dict(orient="records")` (OQ-004 resolved)
- `pydantic` (BaseModel, Field, SecretStr)
- `asyncio` (to_thread, Queue)
- `os` (getenv for config loading)
- `time` (execution timing)
- `logging` (structured logging)

## Error Contracts

### Raised by this module

| Error | When | Details |
|-------|------|---------|
| `ConfigurationError` | `load_config()` finds missing/empty env vars | `config_key` = the missing env var name (e.g., `"SNOWFLAKE_DB_USER"`). `message` = `"Missing required Snowflake configuration: {key}"` |
| `ConfigurationError` | `init_pool()` fails to establish initial connections (bad credentials, unreachable host) | `config_key` = `"SNOWFLAKE_DB_ACCOUNT"`. `message` = `"Failed to initialize Snowflake connection pool: {error}"`. `details` = `{"original_error": str(e)}` |
| `ToolExecutionError` | Query execution fails (SQL syntax error, permission denied, timeout) | `tool_name` = `"snowflake_connector"`. `original_error` = the Snowflake error message. `message` = `"Snowflake query execution failed: {error}"` |
| `ToolExecutionError` | Pool exhausted (all connections busy, acquire timeout) | `tool_name` = `"snowflake_connector"`. `original_error` = `"Connection pool exhausted (timeout=10s)"`. |
| `ToolExecutionError` | Empty SQL provided | `tool_name` = `"snowflake_connector"`. `original_error` = `"SQL query is empty"` |

### Consumed from other modules
- None. This is a leaf tool module.

### Snowflake SDK errors caught

| SDK Exception | Mapped To | Notes |
|---------------|-----------|-------|
| `snowflake.connector.errors.ProgrammingError` | `ToolExecutionError` | SQL syntax errors, invalid object references |
| `snowflake.connector.errors.DatabaseError` | `ToolExecutionError` | Permission denied, query timeout |
| `snowflake.connector.errors.OperationalError` | `ToolExecutionError` | Network errors, connection failures during query |
| `snowflake.connector.errors.InterfaceError` | `ToolExecutionError` | Connection interface errors (stale connection not caught by health check) |

All Snowflake exceptions are caught as `snowflake.connector.errors.Error` (base class) in the outer handler, with specific logging for known subtypes.

## Test Plan

### Unit tests (`tests/unit/tools/test_snowflake_connector.py`)

All unit tests mock `snowflake.connector.connect` -- no real Snowflake connection.

**SnowflakeConfig:**
- Constructs with all required fields from env vars
- Raises `ConfigurationError` when `SNOWFLAKE_DB_USER` is missing
- Raises `ConfigurationError` when `SNOWFLAKE_DB_PASSWORD` is missing
- Raises `ConfigurationError` when `SNOWFLAKE_DB_ACCOUNT` is missing
- `port` defaults to 443 when `SNOWFLAKE_DB_PORT` is unset
- `schema_name` defaults to `"PUBLIC"`
- `password` is `SecretStr` -- `str(config.password)` does not reveal the value

**SnowflakeQuery:**
- Constructs with `sql` only (params=None, timeout=30)
- Constructs with `sql`, `params`, and custom timeout
- `params` accepts nested dict values (Snowflake supports variant types)

**SnowflakeResult:**
- Constructs with all fields
- `row_count` matches `len(rows)`
- Serialization round-trip: `model_dump()` -> `model_validate()`
- Empty result set: `columns=["id"], rows=[], row_count=0`

**execute_query:**
- Successful SELECT returns correct `SnowflakeResult` structure
- Parameterized query passes `params` to `cursor.execute` (verify mock call args)
- Empty SQL raises `ToolExecutionError` with `original_error="SQL query is empty"`
- SQL error from Snowflake raises `ToolExecutionError` with original message preserved
- Connection timeout raises `ToolExecutionError`
- Connection is always released back to pool (verify in both success and error paths)
- `cursor.execute` receives `timeout` parameter from `query.timeout_seconds`

**Connection pool:**
- `init_pool` creates `pool_size` connections
- `init_pool` is idempotent -- second call is no-op
- `close_pool` closes all connections
- `close_pool` is safe to call when pool is not initialized
- Pool exhaustion (all connections busy) raises `ToolExecutionError` after acquire timeout
- Stale connection detected by health check triggers reconnection

**load_config:**
- Returns `SnowflakeConfig` when all env vars present
- Raises `ConfigurationError` with `config_key` for first missing var

### Integration tests (`tests/integration/tools/test_snowflake_connector_integration.py`)

Run only when Snowflake credentials are available. Skip with `@pytest.mark.skipif` when `SNOWFLAKE_DB_USER` env var is unset.

- `init_pool` → `execute_query("SELECT 1 AS test_col")` → verify result has `columns=["TEST_COL"]`, `rows=[{"TEST_COL": 1}]`, `row_count=1`
- Parameterized query: `execute_query("SELECT %(val)s AS result", params={"val": 42})` → verify `rows=[{"RESULT": 42}]`
- Invalid SQL: `execute_query("SELECT FROM")` → `ToolExecutionError`
- `close_pool` → `execute_query` fails gracefully (no unhandled crash)
- Execution time is reported in `execution_time_ms` and is > 0

### Edge Cases

- `params={}` (empty dict, not None) -- should work, no placeholders to bind
- Very large result set -- `fetchall()` loads into memory. No pagination in v1. Document as known limitation.
- `None` values in result rows -- Snowflake NULLs become Python `None` in dicts. `SnowflakeResult.rows` allows `None` values.
- Unicode in SQL and results -- Snowflake connector handles UTF-8 natively.
- Concurrent `execute_query` calls -- pool handles up to `pool_size` concurrent queries.

## ADR References

- **OQ-004 (Resolved):** Pandas confirmed as required for result formatting. `pandas` is an external dependency. Results are serialized via `pd.DataFrame(rows).to_dict(orient="records")`. The `SnowflakeResult` contract remains unchanged.

## Legacy Code Reference

The rewrite replaces:
- `SynaptiCore/Servers/serverSnowflake.py` -- MCP tool wrapper with raw SQL, per-call connections, Pandas `read_sql`, `print()`-based debugging.
- `SynaptiCore/Core/genFuncs.py:create_connection` -- Direct `snowflake.connector.connect()` per call, no pooling, credentials read from env vars inline.

Key differences from legacy:
| Aspect | Legacy | Rewrite |
|--------|--------|---------|
| SQL injection | Vulnerable (raw SQL string) | Prevented (parameterized binding) |
| Connection management | New connection per query, close after | Connection pool with health checks |
| Result format | `pd.read_sql` → DataFrame → `.to_string` | `DictCursor` → `pd.DataFrame` → `.to_dict(orient="records")` (OQ-004 resolved) |
| Async | Synchronous (blocks event loop) | `asyncio.to_thread` wrapper |
| Error handling | Unhandled exceptions propagate | Mapped to `ToolExecutionError` / `ConfigurationError` |
| Logging | `print()` statements | Structured `logging` |
| Config validation | None (crashes on missing env vars) | `SnowflakeConfig` Pydantic validation at startup |
| Credential safety | Plain string in dict | `SecretStr` for password |

## Maturity

All functions: `stub` (rewrite target)
