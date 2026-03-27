# LLD: a2a_card_resolver

> Container: C1 (synapticore-core) | Subpackage: protocols/
> HLD Reference: S3 C1.3.4
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Fetches and validates `AgentCard` from a remote agent's `/.well-known/agent.json` endpoint. Single-purpose HTTP GET + Pydantic validation. Used by `a2a_client` and `host_orchestrator` to discover remote agent capabilities before sending tasks.

## Public API

### Class: `A2ACardResolver`

| Method | Signature | Returns | Raises |
|--------|-----------|---------|--------|
| `__init__` | `(base_url: str, agent_card_path: str = "/.well-known/agent.json", *, httpx_client: httpx.AsyncClient \| None = None)` | -- | -- |
| `get_agent_card` | `async (self) -> AgentCard` | `AgentCard` | `A2AClientHTTPError`, `A2AClientJSONError` |
| `resolve` | `async (base_url: str, agent_card_path: str = "/.well-known/agent.json", *, httpx_client: httpx.AsyncClient \| None = None) -> AgentCard` | `AgentCard` | `A2AClientHTTPError`, `A2AClientJSONError` |

**`__init__`:**
- `base_url` -- The root URL of the remote agent (e.g., `"http://localhost:8000"`, `"https://agent.example.com"`). Trailing slashes are stripped.
- `agent_card_path` -- Override the well-known path. Default: `"/.well-known/agent.json"`. Leading slashes are stripped, then prepended with `/` for normalization.
- `httpx_client` -- Optional injected `httpx.AsyncClient` for connection reuse and testing. When `None`, a new client is created per call and closed afterward.

**`get_agent_card`:**
- Instance method. Performs `GET {base_url}/{agent_card_path}`.
- Validates the response body against `AgentCard` via Pydantic.
- Returns the validated `AgentCard`.

**`resolve`:**
- `@staticmethod` / classmethod convenience. Constructs a resolver and calls `get_agent_card` in one shot.
- Useful for one-off discovery without holding a resolver instance.

## Internal Design

### Rewrite changes from legacy `card_resolver.py`

The existing file at `Core/a2aPro/utils/card_resolver.py` is a minimal synchronous implementation (~12 LOC). The rewrite preserves the core pattern (HTTP GET + Pydantic parse) with these changes:

**Preserved as-is (patterns worth keeping):**
- URL construction: `base_url.rstrip("/") + "/" + agent_card_path.lstrip("/")`
- Pydantic validation via `AgentCard(**response.json())`
- `A2AClientJSONError` wrapping for deserialization failures

**Changes in rewrite:**
- **Async**: `get_agent_card` becomes `async`. Uses `httpx.AsyncClient` instead of `httpx.Client` to align with the async-first architecture (matches `a2a_client`).
- **HTTP error wrapping**: Legacy calls `response.raise_for_status()` but does not catch `httpx.HTTPStatusError`, letting it propagate raw. Rewrite catches `httpx.HTTPStatusError` and wraps it in `A2AClientHTTPError(status_code, message)` -- consistent with `a2a_client._send_request`.
- **Connection error handling**: Catches `httpx.RequestError` (network failures, DNS resolution, timeouts) and wraps in `A2AClientHTTPError(0, str(e))` with status code `0` to signal transport-layer failure vs. HTTP-layer failure.
- **Pydantic `ValidationError` wrapping**: Legacy only catches `json.JSONDecodeError`. Rewrite also catches `pydantic.ValidationError` (malformed but valid JSON that doesn't match `AgentCard` schema) and wraps it in `A2AClientJSONError` -- the caller should not need to distinguish "bad JSON syntax" from "valid JSON, wrong shape."
- **Client injection**: Accepts optional `httpx.AsyncClient` for connection reuse (when resolving multiple cards) and testability (mock transport).
- **Static convenience method**: `resolve()` for one-off lookups.
- **Move location**: From `Core/a2aPro/utils/card_resolver.py` to `synapticore/protocols/a2a_card_resolver.py`.

### Key Design Decisions

1. **Async-only** -- No sync variant. The entire `protocols/` subpackage is async (Starlette, SSE, httpx). A sync card resolver would only serve scripts that could use `asyncio.run()` anyway.
2. **Error unification** -- All failure modes (HTTP error, network error, bad JSON, wrong schema) surface as `A2AClientHTTPError` or `A2AClientJSONError`. Callers never see raw `httpx` or `pydantic` exceptions. This matches the error contract established by `a2a_client`.
3. **No caching** -- `get_agent_card` fetches on every call. Agent cards are small (~1KB) and change infrequently, but caching introduces staleness concerns. Callers that need caching (e.g., `host_orchestrator`) implement it at their layer.
4. **No retry** -- Single attempt. Retry logic (exponential backoff, circuit breakers) is a cross-cutting concern. If needed, callers wrap with `tenacity` or equivalent. Keeping the resolver simple.
5. **Client lifecycle** -- When no `httpx_client` is injected, the resolver creates and closes a client per `get_agent_card` call. This is safe for low-frequency discovery. For bulk resolution, callers inject a shared client.

### Module structure

```
synapticore/protocols/a2a_card_resolver.py
    A2ACardResolver
        __init__(base_url, agent_card_path, *, httpx_client)
        async get_agent_card() -> AgentCard
        @staticmethod
        async resolve(base_url, agent_card_path, *, httpx_client) -> AgentCard
```

### Pseudocode

```python
class A2ACardResolver:
    def __init__(self, base_url: str, agent_card_path: str = "/.well-known/agent.json",
                 *, httpx_client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.agent_card_path = agent_card_path.lstrip("/")
        self._client = httpx_client

    async def get_agent_card(self) -> AgentCard:
        url = f"{self.base_url}/{self.agent_card_path}"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            return AgentCard(**response.json())
        except httpx.HTTPStatusError as e:
            raise A2AClientHTTPError(e.response.status_code, str(e)) from e
        except httpx.RequestError as e:
            raise A2AClientHTTPError(0, str(e)) from e
        except json.JSONDecodeError as e:
            raise A2AClientJSONError(str(e)) from e
        except pydantic.ValidationError as e:
            raise A2AClientJSONError(str(e)) from e
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    async def resolve(base_url: str, agent_card_path: str = "/.well-known/agent.json",
                      *, httpx_client: httpx.AsyncClient | None = None) -> AgentCard:
        resolver = A2ACardResolver(base_url, agent_card_path, httpx_client=httpx_client)
        return await resolver.get_agent_card()
```

## Dependencies

### Internal
- `types/a2a_types` -- `AgentCard`, `A2AClientHTTPError`, `A2AClientJSONError`

### External
- `httpx` (AsyncClient)
- `pydantic` (ValidationError -- caught, not imported for modeling)
- `json` (JSONDecodeError -- caught)

## Error Contracts

### Raised by this module
- `A2AClientHTTPError` -- Remote returned non-2xx status (carries `status_code` and `message`), or network/transport failure (carries `status_code=0`).
- `A2AClientJSONError` -- Response body is not valid JSON, or valid JSON that does not conform to `AgentCard` schema.

### Error flow

```
GET /.well-known/agent.json
    ├─ 2xx + valid AgentCard JSON    → return AgentCard
    ├─ 2xx + invalid JSON syntax     → A2AClientJSONError
    ├─ 2xx + valid JSON, bad schema  → A2AClientJSONError
    ├─ 4xx / 5xx                     → A2AClientHTTPError(status_code, detail)
    └─ network/DNS/timeout           → A2AClientHTTPError(0, detail)
```

### Not raised by this module
- `pydantic.ValidationError` -- caught and wrapped in `A2AClientJSONError`.
- `httpx.HTTPStatusError` -- caught and wrapped in `A2AClientHTTPError`.
- `httpx.RequestError` -- caught and wrapped in `A2AClientHTTPError`.

## Test Plan

### Unit tests (`tests/unit/protocols/test_a2a_card_resolver.py`)

All tests use a mock `httpx.AsyncClient` (via `httpx.MockTransport`) injected into the resolver. No real HTTP calls.

**Happy path:**
- `get_agent_card` returns `AgentCard` when remote returns 200 with valid JSON matching `AgentCard` schema.
- `resolve` static method returns `AgentCard` (same as above, one-liner convenience).
- Custom `agent_card_path` is used in the request URL.
- `base_url` with trailing slash is normalized (no double slash in request URL).
- `agent_card_path` with leading slash is normalized.

**HTTP errors:**
- Remote returns 404 -- raises `A2AClientHTTPError` with `status_code=404`.
- Remote returns 500 -- raises `A2AClientHTTPError` with `status_code=500`.
- Remote returns 401 -- raises `A2AClientHTTPError` with `status_code=401`.

**Network errors:**
- DNS resolution failure (`httpx.ConnectError`) -- raises `A2AClientHTTPError` with `status_code=0`.
- Connection timeout (`httpx.ConnectTimeout`) -- raises `A2AClientHTTPError` with `status_code=0`.
- Read timeout (`httpx.ReadTimeout`) -- raises `A2AClientHTTPError` with `status_code=0`.

**JSON/validation errors:**
- Remote returns 200 with invalid JSON body (not parseable) -- raises `A2AClientJSONError`.
- Remote returns 200 with valid JSON but missing required `AgentCard` fields (e.g., no `name`, no `url`, no `version`, no `capabilities`, no `skills`) -- raises `A2AClientJSONError`.
- Remote returns 200 with valid JSON but wrong types (e.g., `skills` is a string instead of list) -- raises `A2AClientJSONError`.

**Client lifecycle:**
- When no `httpx_client` injected, resolver creates and closes its own client (verify `aclose` is called).
- When `httpx_client` injected, resolver does not close the client.

**Edge cases:**
- `AgentCard` with minimal required fields only (name, url, version, capabilities, skills=[]) -- succeeds.
- `AgentCard` with all optional fields populated -- succeeds.
- Empty response body (200, empty string) -- raises `A2AClientJSONError`.

## ADR References

- None pending. Card resolution is a straightforward HTTP GET + validation with no framework choices.

## Maturity

All functions: `stub` (rewrite target)
