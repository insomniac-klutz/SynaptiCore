# LLD: web_search

> Container: C1 (synapticore-core) | Subpackage: tools/
> HLD Reference: S3 C1.2.2
> Status: stub (rewrite -- not yet implemented)

## Responsibility

Web search tools -- Tavily (primary, API key required) and DuckDuckGo (free fallback for local dev without API keys). Provides a unified async interface so callers never need to know which backend executes the search.

## Public API

### Models

| Class | Fields | Notes |
|-------|--------|-------|
| `SearchQuery` | `query: str`, `max_results: int = 5`, `search_depth: str = "basic"` | Input to every search call. `search_depth` accepts `"basic"` or `"advanced"` (Tavily-specific -- DDG ignores it). `max_results` is capped at 10 to bound response size. |
| `SearchResultItem` | `title: str`, `url: str`, `snippet: str`, `raw_content: str \| None = None`, `score: float \| None = None` | Single search hit. `raw_content` is populated only by Tavily when `search_depth="advanced"`. `score` is a relevance score (0.0-1.0) from Tavily; `None` for DDG results. |
| `SearchResult` | `results: list[SearchResultItem]`, `source: str`, `query: str` | Aggregated response. `source` is `"tavily"` or `"duckduckgo"` so callers can log provenance. `query` echoes the original query for traceability. |

### Functions

| Function | Signature | Notes |
|----------|-----------|-------|
| `search` | `async def search(query: SearchQuery) -> SearchResult` | Primary entry point. Tries Tavily first (if `TAVILY_API_KEY` is set), falls back to DuckDuckGo on missing key or Tavily failure. Raises `ToolExecutionError` only when both backends fail. |
| `tavily_search` | `async def tavily_search(query: SearchQuery) -> SearchResult` | Direct Tavily call. Raises `ToolExecutionError` on API errors or missing key. Not intended for external callers -- use `search()`. |
| `duckduckgo_search` | `async def duckduckgo_search(query: SearchQuery) -> SearchResult` | Direct DuckDuckGo call. Raises `ToolExecutionError` on network/API errors. Not intended for external callers -- use `search()`. |

### Tool Registration

| Name | Description | Input Schema | Handler |
|------|-------------|-------------|---------|
| `"web_search"` | `"Search the web for information. Returns titles, URLs, and snippets from search results."` | `SearchQuery.model_json_schema()` | `search` |

Registered with `tool_registry` at startup via `app_server` wiring.

## Internal Design

### Provider Strategy

```
search(query)
  ├─ TAVILY_API_KEY set?
  │   ├─ YES → tavily_search(query)
  │   │         ├─ success → return SearchResult(source="tavily")
  │   │         └─ failure → log WARNING, fall through to DDG
  │   └─ NO  → skip Tavily, go to DDG
  │
  └─ duckduckgo_search(query)
       ├─ success → return SearchResult(source="duckduckgo")
       └─ failure → raise ToolExecutionError(tool_name="web_search", ...)
```

The fallback is **automatic and silent** from the caller's perspective. The `source` field on `SearchResult` tells callers which backend actually served the results. Tavily failures are logged at WARNING level with the original exception in structured details.

### Tavily Integration

- Uses the `tavily-python` async client (`AsyncTavilyClient`).
- API key read from `os.environ["TAVILY_API_KEY"]` at call time (not cached at import time -- supports hot-reload in dev).
- Maps Tavily response fields to `SearchResultItem`:
  - `title` -> `title`
  - `url` -> `url`
  - `content` -> `snippet`
  - `raw_content` -> `raw_content` (present only on `search_depth="advanced"`)
  - `score` -> `score`
- Respects `max_results` and `search_depth` from `SearchQuery`.
- Timeout: 30 seconds (hardcoded v1, configurable post-v1).

### DuckDuckGo Integration

- **ADR pending (OQ-007):** Client library choice between `langchain-community.tools.DuckDuckGoSearchRun` wrapper and direct `duckduckgo-search` (`DDGS`) package.
- Until ADR resolution, the LLD defines the contract-level interface. Implementation stubs use `duckduckgo-search` (`DDGS`) as the default assumption, with the understanding that the ADR may change this.
- Maps DDG response fields to `SearchResultItem`:
  - `title` -> `title`
  - `href` / `link` -> `url`
  - `body` / `snippet` -> `snippet`
  - `raw_content` -> `None` (DDG does not provide raw content)
  - `score` -> `None` (DDG does not provide relevance scores)
- `search_depth` is ignored (DDG has no equivalent parameter).
- `max_results` passed as the `max_results` parameter to DDG.
- Timeout: 15 seconds (DDG is a fallback -- shorter timeout to avoid stacking latency).

### Key Design Decisions

1. **Unified `search()` facade** -- Callers never import provider-specific functions. `search()` owns fallback logic. This keeps `decypher_agent` and `tool_registry` decoupled from search backend specifics.
2. **Fallback is automatic, not configured** -- Tavily is always preferred when the API key exists. No config switch to force DDG-only or Tavily-only. If a developer wants Tavily, they set the key. If they don't have one, DDG works out of the box.
3. **Env var read at call time** -- `TAVILY_API_KEY` is read on each `search()` invocation, not cached at module load. This supports development workflows where `.env` is modified and the server is restarted without re-importing.
4. **`raw_content` is optional** -- Only Tavily populates this, and only in `"advanced"` mode. Agents consuming `SearchResult` must handle `None`. This field is useful for RAG-style follow-up but not required for basic tool use.
5. **No result caching in v1** -- Each call hits the external API. Caching is a post-v1 concern (needs TTL strategy, memory bounds, and invalidation policy).
6. **Async throughout** -- Both `tavily_search` and `duckduckgo_search` are async. The Tavily client is natively async. DDG may require `asyncio.to_thread` wrapping depending on the client library chosen (OQ-007).

### Module Structure

```
synapticore/tools/web_search.py
    SearchQuery         (Pydantic model)
    SearchResultItem    (Pydantic model)
    SearchResult        (Pydantic model)
    search              (async facade -- primary entry point)
    tavily_search       (async -- Tavily backend)
    duckduckgo_search   (async -- DuckDuckGo backend)
```

Single file. No subpackage needed -- the module has 3 models and 3 functions.

## Dependencies

### Internal
- `types/common_types` -- `ToolExecutionError` (raised on failure)

### External
- `tavily-python` -- `AsyncTavilyClient` for Tavily API calls
- DuckDuckGo client -- **ADR pending (OQ-007)**. Default assumption: `duckduckgo-search` (`DDGS` class). Alternative: `langchain-community` (`DuckDuckGoSearchRun`).
- `pydantic` -- `BaseModel`, `Field` for `SearchQuery`, `SearchResultItem`, `SearchResult`
- `logging` -- stdlib, structured logging for fallback events
- `os` -- env var access (`TAVILY_API_KEY`)
- `asyncio` -- `to_thread` wrapper if DDG client is synchronous

## Error Contracts

### Raised by this module
- `ToolExecutionError(tool_name="web_search", original_error=<str>)` -- raised when **both** Tavily and DDG fail. The `original_error` contains the DDG exception message (since DDG is the last backend attempted). Tavily's failure is logged separately at WARNING level.
- `ToolExecutionError(tool_name="web_search", original_error=<str>)` -- raised by `tavily_search()` directly when called standalone and the Tavily API returns an error or the key is missing.
- `ToolExecutionError(tool_name="web_search", original_error=<str>)` -- raised by `duckduckgo_search()` directly when called standalone and DDG returns an error.

### Not raised (handled internally)
- Tavily errors when called via `search()` -- caught, logged at WARNING, triggers DDG fallback.
- Missing `TAVILY_API_KEY` when called via `search()` -- not an error, silently skips to DDG.

### Raised implicitly
- `pydantic.ValidationError` on invalid `SearchQuery` construction (e.g., `max_results` < 1).

### Error-to-Protocol Mapping (inherited from common_types)

| Internal Error | A2A (JSON-RPC) | MCP | AG-UI (SSE) |
|---------------|----------------|-----|-------------|
| `ToolExecutionError` | `InternalError` (-32603) | MCP tool error | `RunErrorEvent` |

## Test Plan

### Unit tests (`tests/unit/tools/test_web_search.py`)

**SearchQuery model:**
- Constructs with `query` only (defaults: `max_results=5`, `search_depth="basic"`)
- Constructs with all fields specified
- Rejects empty `query` (validator -- empty string is not a valid search query)
- `max_results` clamped/validated to 1-10 range
- `search_depth` accepts `"basic"` and `"advanced"` only

**SearchResultItem model:**
- Constructs with required fields (`title`, `url`, `snippet`)
- `raw_content` defaults to `None`
- `score` defaults to `None`
- `score` accepts float 0.0-1.0

**SearchResult model:**
- Constructs with `results` list, `source`, and `query`
- Empty `results` list is valid (query returned no hits)
- `source` is `"tavily"` or `"duckduckgo"`

**tavily_search (mocked):**
- Returns `SearchResult` with `source="tavily"` on success
- Maps Tavily response fields correctly to `SearchResultItem`
- Passes `max_results` and `search_depth` to Tavily client
- Raises `ToolExecutionError` when API key is missing
- Raises `ToolExecutionError` when Tavily API returns error
- Raises `ToolExecutionError` on timeout (30s)
- `raw_content` populated when `search_depth="advanced"`
- `raw_content` is `None` when `search_depth="basic"`

**duckduckgo_search (mocked):**
- Returns `SearchResult` with `source="duckduckgo"` on success
- Maps DDG response fields correctly to `SearchResultItem`
- `raw_content` is always `None`
- `score` is always `None`
- Ignores `search_depth` parameter
- Passes `max_results` to DDG client
- Raises `ToolExecutionError` on network error
- Raises `ToolExecutionError` on timeout (15s)

**search facade (mocked):**
- Uses Tavily when `TAVILY_API_KEY` is set and Tavily succeeds
- Falls back to DDG when `TAVILY_API_KEY` is not set
- Falls back to DDG when Tavily raises an exception
- Logs WARNING on Tavily failure before falling back
- Raises `ToolExecutionError` when both Tavily and DDG fail
- `ToolExecutionError.original_error` contains DDG error message (last failure)
- Returns DDG `SearchResult` (not Tavily) when Tavily fails and DDG succeeds

**Serialization round-trip:**
- `model_dump()` -> `model_validate()` for `SearchQuery`, `SearchResultItem`, `SearchResult`

**Edge cases:**
- `max_results=1` returns single-element `results` list
- Very long query string (>500 chars) -- passed through, no truncation
- Tavily returns fewer results than `max_results` -- no padding, return as-is
- DDG returns zero results -- return `SearchResult(results=[], source="duckduckgo", query=...)`
- Concurrent `search()` calls -- no shared mutable state, safe by design
- `TAVILY_API_KEY` set to empty string -- treated as missing (skip to DDG)

### Integration tests (`tests/integration/tools/test_web_search_integration.py`)

**Tavily (requires `TAVILY_API_KEY` env var -- skip if not set):**
- Real Tavily search returns non-empty results for a known query
- `source` is `"tavily"`
- All `SearchResultItem` fields populated (title, url, snippet non-empty)
- `search_depth="advanced"` populates `raw_content`

**DuckDuckGo (no API key required):**
- Real DDG search returns non-empty results for a known query
- `source` is `"duckduckgo"`
- `raw_content` is `None` for all results
- `score` is `None` for all results

**Facade fallback (remove `TAVILY_API_KEY` from env for this test):**
- `search()` returns DDG results when Tavily key is absent

## ADR References

| ADR | Topic | Status |
|-----|-------|--------|
| TBD | DuckDuckGo client choice: `duckduckgo-search` vs. `langchain-community` wrapper (OQ-007) | Pending |

## Maturity

All functions: `stub` (rewrite target)
