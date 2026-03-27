# Production Roadmap — SynaptiCore

> Generated: 2026-03-26 by `/monke-recon:orchestra` Phase 5
> Sources: recon-survey.md, hld.md (S3/S7/S8), recon-gaps.md, open-questions.md (32 OQs resolved)
> Scope: Full rewrite from legacy SynaptiCore/ to synapticore/ + new React+Vite UI

---

## Context

- **Single developer.** All estimates assume one person, sequential focus with no context-switching tax.
- **~2,800 LOC rewrite** of existing Python code, but scope expands significantly: AG-UI protocol layer, React+Vite UI, test infrastructure, and two new protocol servers (AG-UI, MCP rewrite) are net-new work.
- **24 components** across 3 containers (C1: synapticore-core, C2: synapticore-ui, C3: synapticore-apps).
- **All agent/ML frameworks ADR-gated** except LiteLLM and Pydantic. Google ADK dropped (OQ-017). Plain Python async loop for agents (OQ-001). SmolAgents optional only (OQ-002).
- **Legacy code** lives in `SynaptiCore/` (PascalCase). New code goes in `synapticore/` (lowercase). Legacy is reference only — not incrementally improved.
- **Zero existing test infrastructure.** No conftest.py, no fixtures, no CI/CD. Must be created from scratch.
- **React+Vite UI has zero scaffolding.** No package.json, no source files, no node_modules.
- **All 32 OQs resolved.** Architecture decisions are final. No blocking ADRs remain.

---

## R1: Unblock

> Remove every blocker that prevents writing the first line of production code.
> Maps to: recon-gaps.md "Top 5 Actions Before Implementation" + HLD S8 pre-phase scaffolding.

### What & Why

R1 exists because 24 LLDs reference a package structure (`synapticore/`), test fixtures (`conftest.py`), and a `pyproject.toml` that do not exist. No component can be implemented until this scaffolding is in place.

### Components

None — R1 produces infrastructure, not components.

### Prerequisites

- HLD finalized (done)
- All blocking ADRs resolved (done — OQ-001 through OQ-007)
- recon-gaps.md written (done)

### Deliverables

| # | Deliverable | Maps to Gap | Details |
|---|-------------|-------------|---------|
| R1.1 | **Package skeleton** | D8-08 | Create `synapticore/` with `__init__.py` at every level: `synapticore/{types,tools,protocols,agents}/__init__.py`. Create `synapticore/apps/` for C3. Empty modules — just the directory tree. |
| R1.2 | **pyproject.toml rewrite** | D8-07 | New `[project]` section targeting `synapticore` package. Entry point: `synapticore = "synapticore.main:app"`. Core deps: `litellm`, `pydantic`, `starlette`, `sse-starlette`, `uvicorn`, `httpx`, `httpx-sse`, `python-dotenv`, `mcp[cli]`. ADR-gated deps in `[project.optional-dependencies]`: `langchain`, `langchain-community`, `smolagents`, `pandas`, `snowflake-connector-python`, `pymupdf`, `tavily-python`. Dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `httpx` (test client), `ruff`. |
| R1.3 | **Test infrastructure** | T-01 | Create `tests/conftest.py` with shared fixtures: `mock_llm_provider` (returns canned `LlmResponse`), `mock_tool_registry` (pre-populated with calculator), `sample_llm_config` (bedrock/claude-3 defaults), `sample_conversation` (2-message exchange). Create `tests/{types,tools,protocols,agents,apps}/` directories with `__init__.py`. Add `pytest.ini` or `[tool.pytest.ini_options]` in pyproject.toml with `asyncio_mode = "auto"`. |
| R1.4 | **UI scaffold** | D8-06 | Run `npm create vite@latest ui -- --template react-ts` (or equivalent manual scaffold). Add `@ag-ui/client`, `@ag-ui/core` to package.json. Create `ui/src/` with placeholder App.tsx. Vite config with proxy to Python backend. |
| R1.5 | **Error hierarchy** | EH-01 (partial) | Create `synapticore/types/errors.py` with `SynaptiCoreError` base class and subclasses: `ProviderError`, `ToolExecutionError`, `ConfigurationError`, `ToolNotFoundError`, `DuplicateToolError`. This is deliverable zero for common_types (C1.1.4) but pulled into R1 because every other module imports it. |
| R1.6 | **Logging skeleton** | O-01 | Create `synapticore/logging.py` with `get_logger(name)` returning a stdlib logger with JSON formatter. All modules import from here. Replaces every `print()` in the codebase. |
| R1.7 | **.env.template update** | D7-05 | New template using LiteLLM-compatible env var names (OQ-032): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `GEMINI_API_KEY`, `TAVILY_API_KEY`, `SNOWFLAKE_*`, `LM_STUDIO_BASE_URL`. Drop legacy `ANTRHOPIC` typo and `USE_MODEL_INFERENCE` toggle. |

### Test Gates

- `pytest` runs with zero errors (no tests yet, but infrastructure loads)
- `uv sync` installs all core deps without errors
- `python -c "from synapticore import __version__"` succeeds
- `ui/` directory contains a working Vite dev server (`npm run dev` starts)
- `ruff check synapticore/` passes on the skeleton

### Key Risks

| Risk | Mitigation |
|------|------------|
| UV resolution conflicts between core and optional deps | Pin core deps first. Optional deps tested in isolation via `uv sync --extra snowflake` etc. |
| AG-UI SDK version incompatibility with React 18 | Check `@ag-ui/client` peer deps before scaffolding. If React 19 required, evaluate upgrade. |
| pyproject.toml entry point breaks legacy imports | Legacy `SynaptiCore/` is untouched. New entry point is `synapticore.main:app`. No conflict. |

### Exit Criteria

R1 is done when a developer can run `uv sync && uv run pytest && cd ui && npm install && npm run dev` and get green across the board with zero test failures and both dev servers starting.

---

## R2: Foundation

> Types, core tools, server shell, logging, error hierarchy — the leaf layer everything else depends on.
> Maps to: HLD S8 Phase 1 (8 components).

### Components

| # | Component | HLD Ref | Effort | What It Does |
|---|-----------|---------|--------|--------------|
| 1 | common_types | C1.1.4 | S | `LlmConfig`, `ConversationMessage`, `ToolCall`, `ToolResult`, `TokenUsage`, error hierarchy |
| 2 | a2a_types | C1.1.1 | M | 50+ Pydantic models for A2A protocol: `Task`, `TaskState`, `Message`, `Part`, `AgentCard`, JSON-RPC pairs, discriminated union `A2ARequest` |
| 3 | agui_types | C1.1.2 | M | AG-UI event models: run lifecycle, text streaming, tool calls, state sync, `AgUiEvent` discriminated union |
| 4 | mcp_types | C1.1.3 | S | Thin wrapper over MCP SDK types: `McpToolDefinition`, `McpToolResult`, `McpServerConfig` |
| 5 | llm_provider | C1.2.1 | M | LiteLLM gateway: `acomplete()` with retry policy (exponential backoff + jitter for EH-01), config routing, token usage tracking |
| 6 | calculator | C1.2.3 | S | Safe math expression evaluator, no external deps |
| 7 | tool_registry | C1.2.6 | M | Singleton registry: register, query, duplicate check, MCP exposure interface. Agents query per-request (OQ-031). |
| 8 | app_server | C1.3.7 | M | Main Starlette app, sub-app mount points (empty initially), env loading, logging config, startup wiring |

### Prerequisites

- R1 complete (package skeleton, pyproject.toml, test infra, error hierarchy, logging)

### Deliverables

- All 4 type modules with full Pydantic models, serialization round-trips verified
- `llm_provider` with retry policy, mock-tested and integration-tested with 1 real provider
- `calculator` with expression eval and error handling
- `tool_registry` populated with calculator at startup
- `app_server` that starts, loads env, mounts empty sub-app slots, exposes `/health`
- Logging wired through all modules (no `print()` anywhere)

### Test Gates

| Test | Type | What It Proves |
|------|------|----------------|
| `test_common_types.py` | Unit | Model validation, error hierarchy, serialization |
| `test_a2a_types.py` | Unit | All 50+ models validate, discriminated union dispatches correctly |
| `test_agui_types.py` | Unit | Event models validate, union dispatches correctly |
| `test_mcp_types.py` | Unit | Wrapper types validate |
| `test_llm_provider.py` | Unit | Mock LiteLLM: config routing, retry on rate limit, timeout handling |
| `test_llm_provider_integration.py` | Integration | Real LLM call to 1 provider (Bedrock or Gemini), verify `LlmResponse` shape |
| `test_calculator.py` | Unit | Expression eval, division by zero, invalid input, injection attempts |
| `test_tool_registry.py` | Unit | Register, query, duplicate error, not-found error, get_tools filtering |
| `test_app_server.py` | Integration | Server starts, `/health` returns 200, env loaded, tool_registry populated |
| **System test** | System | `app_server` starts, tool_registry has calculator, `llm_provider.acomplete()` returns mock response |

### Key Risks

| Risk | Mitigation |
|------|------------|
| A2A type models are 50+ classes — high surface area for bugs | Port from existing `a2aPro/types.py` (production-ready in survey). Rewrite naming to PEP 8 but preserve structure. |
| LiteLLM retry policy complexity (EH-01) | Start with `tenacity` or manual retry. 3 retries, exponential backoff, jitter. Only retry `RateLimitError`, `Timeout`, `APIConnectionError`. |
| `app_server` startup wiring touches everything | Keep R2 app_server minimal — mount points only. Full wiring in R4. |

---

## R3: Harden

> Protocol servers — A2A, MCP, AG-UI. Per-component hardening with boundary contracts.
> Maps to: HLD S8 Phase 2 (6 components).

### Components

| # | Component | HLD Ref | Effort | What It Does |
|---|-----------|---------|--------|--------------|
| 9 | a2a_task_manager | C1.3.3 | L | Abstract + InMemoryTaskManager: task lifecycle (submitted/working/completed/failed/cancelled/input-required), SSE subscriber queues, push notification config, asyncio locks. Bounded queues (OQ-024/028). |
| 10 | a2a_server | C1.3.1 | M | Starlette sub-app: JSON-RPC routing, request validation via discriminated union, dispatch to task_manager, SSE streaming, `/.well-known/agent.json` serving |
| 11 | a2a_client | C1.3.2 | M | Async httpx client: `send_task`, `get_task`, `cancel_task`, SSE streaming mode, custom exceptions |
| 12 | a2a_card_resolver | C1.3.4 | S | Fetch + validate `AgentCard` from remote `/.well-known/agent.json` |
| 13 | mcp_server | C1.3.5 | M | FastMCP server reading from tool_registry, tool discovery + invocation, error mapping to MCP codes |
| 14 | agui_server | C1.3.6 | XL | AG-UI backend: HTTP POST `/agui/runs`, SSE event stream, agent executor injection, `AgUiEvent` translation, heartbeat (OQ-011), thread management (OQ-018/019), concurrency limits (OQ-024/028), body size limits (OQ-023), agent discovery endpoint (OQ-013), error sanitization (OQ-014) |

### Prerequisites

- R2 complete (all types, llm_provider, tool_registry, app_server shell)
- All type contracts frozen (boundary matrix from S7 verified)

### Deliverables

- A2A server accepting JSON-RPC requests, dispatching to task_manager, streaming SSE responses
- A2A client sending tasks to any A2A endpoint (local or remote)
- A2A card resolver fetching and validating agent cards
- MCP server exposing all registered tools via MCP protocol
- AG-UI server accepting user messages, streaming events, managing threads, enforcing limits
- All protocol servers mounted on app_server at their respective paths (`/a2a/`, `/mcp/`, `/agui/`)
- Boundary contracts from S7 verified with integration tests at every crossing point

### Test Gates

| Test | Type | What It Proves |
|------|------|----------------|
| `test_a2a_task_manager.py` | Unit | Task lifecycle transitions, SSE queue management, bounded queues, concurrent access |
| `test_a2a_server.py` | Unit | Request validation, dispatch, error codes |
| `test_a2a_server_integration.py` | Integration | JSON-RPC round-trip: send_task → get_task → task_status |
| `test_a2a_client.py` | Unit | Mock HTTP responses, SSE event parsing |
| `test_a2a_client_server.py` | Integration | Client → server round-trip, streaming mode |
| `test_a2a_card_resolver.py` | Unit | Mock HTTP, card validation |
| `test_mcp_server.py` | Unit | Tool exposure from registry, invocation routing |
| `test_mcp_server_integration.py` | Integration | MCP client → server: discover tools, invoke calculator |
| `test_agui_server.py` | Unit | Event translation, request validation, thread management |
| `test_agui_server_integration.py` | Integration | HTTP POST → SSE stream with mock agent executor |
| `test_agui_limits.py` | Unit | Body size limit (5MB), message count limit (100), SSE concurrency limit (50), agent run limit (5) |
| **System test** | System | A2A client → local A2A server round-trip. MCP client discovers and invokes tool. AG-UI POST → SSE event stream with mock agent. |

### Key Risks

| Risk | Mitigation |
|------|------------|
| AG-UI server is the most complex component (XL) — SSE, threads, concurrency, limits, heartbeat | Implement in layers: (1) basic POST→SSE, (2) thread management, (3) concurrency limits, (4) heartbeat + disconnect detection. Test each layer independently. |
| Two SSE implementations (A2A + AG-UI) sharing one event loop (OQ-012) | Separate thread pools per OQ-012 resolution. Load test with concurrent A2A and AG-UI streams post-implementation. |
| MCP SDK version compatibility with FastMCP | Pin `mcp[cli]` version in pyproject.toml. Test tool registration + invocation before building more tools. |
| CORS defaults to `["*"]` (SEC-03) | Restrict to `localhost` in dev, configurable via env var for production. |

---

## R4: Integrate

> Agents, remaining tools, cross-boundary contract tests, agent-protocol integration.
> Maps to: HLD S8 Phase 3 (5 components).

### Components

| # | Component | HLD Ref | Effort | What It Does |
|---|-----------|---------|--------|--------------|
| 15 | web_search | C1.2.2 | M | Tavily (primary) + DuckDuckGo (fallback). ADR during implementation for DDG client (OQ-007). |
| 16 | snowflake_connector | C1.2.4 | M | Parameterized queries (no SQL injection), connection pooling, Pandas result formatting (OQ-004). Timeout per query. |
| 17 | pdf_processor | C1.2.5 | M | PDF text extraction + chunking. ADR during implementation for library choice (OQ-006). |
| 18 | decypher_agent | C1.4.1 | L | Plain Python async loop (OQ-001). Augmented LLM pattern: observe → retrieve → reason → respond. Tool selection via tool_registry (live query per OQ-031). Conversation memory with sliding window (OQ-027, max 200 messages). Tool loop breaker (OQ-015, max 2 identical calls). Max iterations configurable (default 10). |
| 19 | host_orchestrator | C1.4.2 | L | Plain Python + a2a_client (OQ-017, ADK dropped). Agent card registry at startup. LLM-driven agent selection. A2A delegation with streaming. Session state dict-based. Max 5 concurrent agent runs (OQ-028). |

### Prerequisites

- R3 complete (all protocol servers operational, mounted on app_server)
- tool_registry accepting new tool registrations
- agui_server accepting agent executor injection

### Deliverables

- 3 new tools (web_search, snowflake_connector, pdf_processor) registered in tool_registry and exposed via MCP
- decypher_agent handling multi-turn conversations with tool use, wired into agui_server
- host_orchestrator delegating to remote A2A agents, wired into a2a_server
- Full agent-to-protocol integration: user message → agui_server → decypher_agent → tools → LLM → SSE response
- Cross-boundary contract tests verifying every boundary in S7 matrix
- All OQ resolutions affecting agents verified in integration tests

### Test Gates

| Test | Type | What It Proves |
|------|------|----------------|
| `test_web_search.py` | Unit | Mock Tavily + DDG APIs, result formatting, fallback logic |
| `test_web_search_integration.py` | Integration | Real Tavily call (if API key available) |
| `test_snowflake_connector.py` | Unit | Parameterized queries, connection pool mock, Pandas formatting, timeout |
| `test_snowflake_connector_integration.py` | Integration | Real Snowflake query (if creds available) |
| `test_pdf_processor.py` | Unit | Extract text from test PDF, chunking, page selection |
| `test_decypher_agent.py` | Unit | Mock llm_provider: no-tool response, tool selection, tool execution, loop breaker, sliding window, max iterations |
| `test_decypher_agent_integration.py` | Integration | Real LLM + calculator tool, multi-turn conversation |
| `test_host_orchestrator.py` | Unit | Mock a2a_client: agent selection, task delegation, result aggregation |
| `test_host_orchestrator_integration.py` | Integration | Real A2A delegation to local decypher_agent |
| `test_boundary_contracts.py` | Contract | Every boundary in S7 matrix: correct types cross each boundary, errors map correctly to protocol codes |
| **System test** | System | decypher_agent multi-turn with web_search tool. host_orchestrator delegates to local A2A decypher and returns results. |

### Key Risks

| Risk | Mitigation |
|------|------------|
| decypher_agent (L) is the core product — bugs here are user-visible | Extensive unit tests with mock LLM. Test every branch: no-tool, single-tool, multi-tool, tool failure, loop breaker, max iterations, sliding window eviction. |
| host_orchestrator depends on a working A2A stack | A2A stack proven in R3. Integration test uses local A2A server with a stub agent. |
| Snowflake connector requires real creds for integration tests | Mark integration tests with `@pytest.mark.snowflake`, skip if creds unavailable. Unit tests cover all logic with mocked connector. |
| ADR decisions for DDG client and PDF lib made during implementation | Both are isolated tools with clear contracts. Decision affects internals only — no contract changes. |

---

## R5: Ship

> Frontend (React+Vite), apps (DeCypher, RoutesHQ), system tests, polish.
> Maps to: HLD S8 Phase 4 (5 components).

### Components

| # | Component | HLD Ref | Effort | What It Does |
|---|-----------|---------|--------|--------------|
| 20 | agui_client | C2.1 | M | TypeScript AG-UI client: SSE connection, event deserialization, typed callbacks (`onRunStarted`, `onTextMessage*`, `onToolCall*`, `onState*`, `onRunFinished`, `onRunError`) |
| 21 | chat_view | C2.2 | L | React component: message list, user input, typing indicators, tool call visualizations, streaming text, error display, tabbed conversations (OQ-030) |
| 22 | app_shell | C2.3 | M | Top-level React app: layout, error boundary, Vite entry point, agent discovery via GET `/agui/agents` (OQ-013), API base URL config |
| 23 | decypher_app | C3.1 | S | App configuration: system prompt, tool set, LLM config. `create_decypher_agent()` factory. Registers with agui_server and optionally a2a_server. |
| 24 | routeshq_app | C3.2 | S | Intent classification: `classify_intent()` using llm_provider. 3 intent types, single LLM call per classification. |

### Prerequisites

- R4 complete (agents operational, protocol servers wired, tools registered)
- UI scaffold from R1 (Vite + React + AG-UI SDK installed)

### Deliverables

- Working React+Vite UI that connects to the Python backend via AG-UI protocol
- Chat interface with streaming text, tool call visualization, and error handling
- Tabbed multi-conversation support
- Agent discovery from UI
- DeCypher app configured and accessible from UI
- RoutesHQ intent classifier accessible as a tool/API
- End-to-end system test: browser → UI → AG-UI → agent → tools → LLM → response → UI
- `.env.template` finalized with all required env vars
- Developer guide for building new agents/tools (D7-02)

### Test Gates

| Test | Type | What It Proves |
|------|------|----------------|
| `test_agui_client.spec.ts` | Unit | Mock SSE stream, event deserialization, all callback types fire |
| `test_chat_view.spec.tsx` | Unit | Component renders messages, handles streaming, shows tool calls, error states |
| `test_app_shell.spec.tsx` | Unit | Layout renders, error boundary catches, agent discovery populates |
| `test_decypher_app.py` | Integration | Create agent via factory, run conversation via agui_server, verify event stream |
| `test_routeshq_app.py` | Unit | Mock LLM, classify all 3 intent types correctly |
| `test_routeshq_app_integration.py` | Integration | Real LLM classification |
| **System test (E2E)** | System | User sends message in UI → decypher_agent processes → web_search tool executes → response streams back to UI via AG-UI SSE. Full round-trip verified. |
| **System test (multi-agent)** | System | host_orchestrator receives task → delegates to decypher_agent via A2A → result returns through AG-UI to UI. |

### Key Risks

| Risk | Mitigation |
|------|------------|
| React+Vite UI is net-new — no existing code to port | AG-UI SDK provides the protocol layer. chat_view is a standard chat UI pattern. Start with minimal viable UI, iterate. |
| AG-UI SDK may have undocumented quirks | Read @ag-ui/client source before implementation. Write a minimal SSE test first. |
| E2E tests require full stack running | Use `pytest` subprocess to start app_server, Playwright or similar for browser automation. Or: test UI components in isolation, test backend E2E via httpx, accept manual E2E verification for alpha. |
| Tabbed conversations (OQ-030) adds UI complexity | Implement single conversation first. Tabs are state management — add after core chat works. |

---

## Component Priority Table

All 24 components ranked by implementation order with phase assignment and effort estimate.

| Priority | Component | Container | Phase | Effort | Depends On | Critical Path? |
|----------|-----------|-----------|-------|--------|------------|---------------|
| 1 | common_types | C1.1.4 | R2 | S | R1 (skeleton, errors) | Yes |
| 2 | a2a_types | C1.1.1 | R2 | M | R1 | Yes |
| 3 | agui_types | C1.1.2 | R2 | M | R1 | Yes |
| 4 | mcp_types | C1.1.3 | R2 | S | R1 | No |
| 5 | llm_provider | C1.2.1 | R2 | M | common_types | Yes |
| 6 | calculator | C1.2.3 | R2 | S | common_types | No |
| 7 | tool_registry | C1.2.6 | R2 | M | common_types, mcp_types | Yes |
| 8 | app_server | C1.3.7 | R2 | M | tool_registry, all type modules | Yes |
| 9 | a2a_task_manager | C1.3.3 | R3 | L | a2a_types | Yes |
| 10 | a2a_server | C1.3.1 | R3 | M | a2a_types, a2a_task_manager | Yes |
| 11 | a2a_client | C1.3.2 | R3 | M | a2a_types | Yes |
| 12 | a2a_card_resolver | C1.3.4 | R3 | S | a2a_types | No |
| 13 | mcp_server | C1.3.5 | R3 | M | mcp_types, tool_registry | No |
| 14 | agui_server | C1.3.6 | R3 | XL | agui_types, common_types, app_server | Yes |
| 15 | web_search | C1.2.2 | R4 | M | common_types, tool_registry | No |
| 16 | snowflake_connector | C1.2.4 | R4 | M | common_types, tool_registry | No |
| 17 | pdf_processor | C1.2.5 | R4 | M | common_types, tool_registry | No |
| 18 | decypher_agent | C1.4.1 | R4 | L | llm_provider, tool_registry, agui_types, common_types | Yes |
| 19 | host_orchestrator | C1.4.2 | R4 | L | a2a_client, a2a_card_resolver, llm_provider, common_types | No |
| 20 | agui_client | C2.1 | R5 | M | agui_server (backend running) | Yes |
| 21 | chat_view | C2.2 | R5 | L | agui_client | Yes |
| 22 | app_shell | C2.3 | R5 | M | chat_view | Yes |
| 23 | decypher_app | C3.1 | R5 | S | decypher_agent, tool_registry | No |
| 24 | routeshq_app | C3.2 | R5 | S | llm_provider, common_types | No |

### Effort Legend

| Size | Meaning | Approximate Scope |
|------|---------|-------------------|
| S | Small | < 150 LOC, < 10 tests, well-defined contract, no external deps |
| M | Medium | 150-400 LOC, 10-25 tests, 1-2 external deps, some integration complexity |
| L | Large | 400-800 LOC, 25-50 tests, multiple internal deps, complex async behavior, state management |
| XL | Extra Large | 800+ LOC, 50+ tests, multiple protocols, concurrency limits, hardening concerns, highest integration surface |

### Effort Summary

| Phase | S | M | L | XL | Total Components |
|-------|---|---|---|----|-|
| R1 | — | — | — | — | 0 (infrastructure only) |
| R2 | 3 | 4 | 0 | 0 | 7 (+1 app_server shell) |
| R3 | 1 | 3 | 1 | 1 | 6 |
| R4 | 0 | 3 | 2 | 0 | 5 |
| R5 | 2 | 2 | 1 | 0 | 5 |
| **Total** | **6** | **12** | **4** | **1** | **24** (including app_server counted in R2) |

---

## Critical Path

The longest chain of dependent components that determines minimum project duration.

```
R1: scaffold
  |
  v
R2: common_types (S)
  |
  v
R2: llm_provider (M)
  |
  +---> R2: tool_registry (M) ---> R2: app_server (M)
  |                                       |
  |                                       v
  |                              R3: agui_server (XL)
  |                                       |
  |                                       v
  |                              R4: decypher_agent (L)
  |                                       |
  |                                       v
  |                              R5: agui_client (M)
  |                                       |
  |                                       v
  |                              R5: chat_view (L)
  |                                       |
  |                                       v
  |                              R5: app_shell (M)
  |
  +---> R2: a2a_types (M) ---> R3: a2a_task_manager (L) ---> R3: a2a_server (M)
```

**Critical chain:** R1 scaffold → common_types (S) → llm_provider (M) → tool_registry (M) → app_server (M) → agui_server (XL) → decypher_agent (L) → agui_client (M) → chat_view (L) → app_shell (M)

**Chain length:** 10 steps (1 infra + 9 components)
**Chain effort:** S + M + M + M + XL + L + M + L + M = heavy-weighted

**Parallelizable work off the critical path:**
- a2a_types, agui_types, mcp_types (R2) — can be built in parallel with common_types
- calculator (R2) — independent after common_types
- a2a_task_manager, a2a_server, a2a_client, a2a_card_resolver (R3) — parallel with agui_server
- mcp_server (R3) — parallel with agui_server
- web_search, snowflake_connector, pdf_processor (R4) — parallel with decypher_agent
- host_orchestrator (R4) — parallel with decypher_agent (needs a2a_client from R3)
- decypher_app, routeshq_app (R5) — parallel with UI components

For a single developer, the critical path IS the project timeline. Off-path components fill gaps when the developer is blocked on reviews, API keys, or LLM access for integration tests.

---

## Gap Coverage Matrix

How each roadmap phase addresses the gaps from recon-gaps.md.

| Gap ID | Severity | Addressed In | How |
|--------|----------|-------------|-----|
| **EH-01** | Critical | R2 (llm_provider) | Retry policy with exponential backoff + jitter |
| **SEC-01** | Critical | R4 (snowflake_connector) | Parameterized queries in rewrite; legacy not importable |
| **T-01** | Critical | R1 (test infra) | conftest.py, shared fixtures, pytest config |
| **D8-01** | Critical | Pre-R1 (done) | All 5 ADRs resolved via OQ-001 through OQ-007 |
| **D8-06** | Critical | R1 (UI scaffold) | Vite + React + AG-UI SDK |
| **D8-04** | Critical | R2 (app_server) | `/health` as liveness+readiness for alpha |
| **D8-07** | High | R1 (pyproject.toml) | Full rewrite with new structure |
| **D8-08** | High | R1 (package skeleton) | `synapticore/` directory tree |
| **O-01** | High | R1 (logging) + R2 (all modules) | Structured JSON logging, no print() |
| **EH-02** | High | R4 (decypher_agent) | Sliding window, max 200 messages (OQ-027) |
| **EH-03** | High | R3 (agui_server) | Bounded emit queue, watchdog with timeout |
| **EH-04** | High | R4 (host_orchestrator) | Error mapping: A2A errors → structured response to LLM |
| **EH-08** | High | R4 (agents) | 30s tool timeout (OQ-025), max 5 concurrent runs (OQ-028) |
| **SEC-02** | High | R4 (snowflake_connector) | Parameterized queries, no multi-statement |
| **SEC-03** | High | R3 (app_server mounting) | CORS restricted to localhost in dev |
| **SEC-04** | High | Deferred (post-alpha) | Rate limiting requires infrastructure not in scope |
| **SEC-05** | High | R3 (agui_server) | Server-generated UUID4 for thread_id (OQ-018) |
| **PERF-01** | High | R4 (decypher_agent) | Sliding window eviction (OQ-027) |
| **PERF-02** | High | R3 (agui_server) | SSE semaphore, max 50 concurrent (OQ-024) |
| **PERF-03** | High | R4 (host_orchestrator) | Parallel card resolution at startup |
| **O-02** | High | R2 (llm_provider) | LiteLLM callback registration for tracing |
| **O-05** | High | R4 (decypher_agent) | Log tool selection reasoning with agent decision context |
| **T-02** | High | R1 (conftest.py) + R2 (mock fixtures) | `mock_llm_provider` fixture |
| **T-03** | High | R4 (tool tests) | Mock Tavily, Snowflake, DDG in unit tests |
| **T-04** | High | R3 (agui_server tests) | SSE streaming test via httpx async client |
| **D-01** | High | R3 (a2a_task_manager) | Acknowledged: in-memory only for v1 |
| **D-02** | High | R3 (agui_server) | Server-generated UUID4 (OQ-018) |
| **D-04** | High | R3 (a2a_task_manager) | Bounded subscriber queues |
| **D7-01** | High | R3 (protocol servers) | OpenAPI auto-generated from Starlette routes |
| **D7-02** | High | R5 (polish) | Developer guide for building agents/tools |
| **D7-04** | High | R1 (scaffold) | Legacy code untouched; new package is the migration |
| **D8-03** | High | Deferred (OQ-026) | Single-process accepted for v1, benchmark post-impl |

---

## Phase Transition Checklist

### R1 → R2
- [ ] `synapticore/` package tree exists with `__init__.py` at every level
- [ ] `pyproject.toml` updated, `uv sync` succeeds
- [ ] `tests/conftest.py` exists with shared fixtures
- [ ] `ui/` scaffolded, `npm install && npm run dev` starts
- [ ] `synapticore/types/errors.py` has full error hierarchy
- [ ] `synapticore/logging.py` has `get_logger()`
- [ ] `.env.template` updated with LiteLLM-compatible vars
- [ ] `ruff check synapticore/` passes

### R2 → R3
- [ ] All 4 type modules pass unit tests (model validation, serialization round-trip)
- [ ] `llm_provider.acomplete()` works with mock and 1 real provider
- [ ] `calculator` passes all expression eval tests
- [ ] `tool_registry` passes register/query/error tests
- [ ] `app_server` starts, `/health` returns 200
- [ ] Phase 1 system test passes: server starts, registry populated, llm_provider responds
- [ ] `monke-docs/checkpoints/phase-1-checkpoint.md` written

### R3 → R4
- [ ] A2A: client → server round-trip works (send_task, get_task)
- [ ] A2A: SSE streaming mode works
- [ ] A2A: card resolver fetches valid agent card
- [ ] MCP: client discovers and invokes calculator tool
- [ ] AG-UI: HTTP POST → SSE event stream with mock agent executor
- [ ] AG-UI: thread management (server-generated UUID4)
- [ ] AG-UI: concurrency limits enforced (50 SSE, 5 agent runs)
- [ ] AG-UI: heartbeat every 15s on idle connections
- [ ] All protocol servers mounted on app_server
- [ ] Phase 2 system test passes
- [ ] `monke-docs/checkpoints/phase-2-checkpoint.md` written

### R4 → R5
- [ ] web_search returns results (mock + real if API key available)
- [ ] snowflake_connector executes parameterized queries (mock + real if creds available)
- [ ] pdf_processor extracts text from test PDF
- [ ] decypher_agent handles multi-turn conversation with tool use
- [ ] decypher_agent sliding window evicts at 200 messages
- [ ] decypher_agent loop breaker triggers after 2 identical tool calls
- [ ] host_orchestrator delegates to local A2A agent
- [ ] All S7 boundary contracts verified
- [ ] Phase 3 system test passes
- [ ] `monke-docs/checkpoints/phase-3-checkpoint.md` written

### R5 → Done
- [ ] agui_client connects to backend, deserializes all event types
- [ ] chat_view renders messages, streaming text, tool calls, errors
- [ ] app_shell loads, error boundary works, agent discovery populates
- [ ] Tabbed multi-conversation works
- [ ] decypher_app creates agent, runs conversation via UI
- [ ] routeshq_app classifies all 3 intent types
- [ ] E2E system test: browser → UI → AG-UI → agent → tool → LLM → response → UI
- [ ] Multi-agent system test: orchestrator → A2A → agent → result → UI
- [ ] `monke-docs/checkpoints/phase-4-checkpoint.md` written
- [ ] `.env.template` final
- [ ] Developer guide written

---

## Deferred Items (Post-v1)

These items are explicitly out of scope for the alpha rewrite. Tracked here for completeness.

| Item | Source | Why Deferred |
|------|--------|-------------|
| Rate limiting on endpoints | SEC-04 | Requires reverse proxy or middleware infra not justified for alpha |
| Persistent conversation storage | HLD OUT | Database-backed checkpoints — in-memory sufficient for alpha |
| CI/CD pipeline | HLD OUT | Single developer, manual testing. Add when team grows. |
| Distributed tracing / OpenTelemetry | HLD OUT | Structured logging covers alpha needs |
| Intent-based routing (RoutesHQ → AG-UI) | OQ-029 | Manual agent selection via discovery endpoint for v1 |
| Local embeddings/inference (PyTorch) | OQ-003 | Not needed for v1 core |
| Data visualization (NumPy/Matplotlib) | OQ-005 | Not needed for v1 core |
| Dynamic agent discovery/registry | HLD OUT | Static agent card config for v1 |
| HTTP/2 support | PERF-09 | SSE connection limit acceptable for alpha |
| Bundle size analysis | PERF-10 | Premature optimization |
| Color contrast/theme support | D9-03 | Accessibility polish post-alpha |
| Focus management during async updates | D9-04 | Accessibility polish post-alpha |
| Keyboard navigation for chat | D9-01 | Accessibility polish post-alpha |
| Screen reader support for streaming | D9-02 | Accessibility polish post-alpha |
