# High-Level Design — SynaptiCore

Version: 1.1 | Date: 2026-03-26
Source: reverse-engineered from existing codebase + rewrite design
Change: OQ resolutions — ADK dropped, framework decisions, boundary limits

---

## S1: System Context (L1)

**SynaptiCore** is a Python 3.12+ framework for building and orchestrating autonomous multi-agent systems, targeting developers and AI engineers who compose LLM-powered agents that communicate with each other (A2A), access external tools (MCP), and stream results to end users (AG-UI) through a unified React+Vite interface.

Developers interact with SynaptiCore in two modes: (1) building agents and tools via the Python API (`from synapticore import ...`), and (2) using the React+Vite UI to test and iterate on agent behavior.

### External Actors & Systems

| Actor/System | Role | Protocol |
|-------------|------|----------|
| **Developer** | Builds agents/tools via Python API, iterates via UI | Python imports + AG-UI (browser) |
| **End User** | Interacts with agents via unified UI | AG-UI (bidirectional: SSE server→client, HTTP client→server) |
| **LLM Providers (via LiteLLM)** | All LLM inference — cloud and local. LiteLLM is the sole routing layer; no direct provider SDK calls. | LiteLLM unified API |
| ↳ AWS Bedrock | Claude models | LiteLLM → boto3 |
| ↳ Google Gemini | Gemini models | LiteLLM → google-genai |
| ↳ LM Studio | Local models | LiteLLM → OpenAI-compatible HTTP |
| **Snowflake** | Data warehouse queries | snowflake-connector-python |
| **Tavily** | Web search API | HTTPS |
| **DuckDuckGo** | Web search (free fallback for local dev without API keys) | HTTPS (via langchain-community) |
| **Remote A2A Agents** | External agent services. Discovery via static agent card config (`.well-known/agent.json`). Dynamic registry is OUT v1. | A2A protocol (JSON-RPC 2.0 / SSE) |

**LLM routing decision:** The rewrite eliminates direct provider SDK usage (e.g., `langchain-aws.ChatBedrock`). All LLM calls go through LiteLLM, including Bedrock. This simplifies provider switching to a config change (model slug + optional `api_base`).

### Scope

**IN v1:**
- Agent orchestration engine (LangChain/LangGraph workflows)
- Unified LLM routing through LiteLLM (all providers — Bedrock, Gemini, LM Studio)
- A2A client/server for multi-agent communication (plain Python + a2a_client orchestrator)
- MCP server framework for tool exposure
- AG-UI Python backend emitting bidirectional protocol events
- React+Vite frontend consuming/sending AG-UI events
- Tool library: web search (Tavily, DuckDuckGo), calculator, Snowflake SQL, PDF processing (PyMuPDF)
- ML capabilities: PyTorch + Transformers for local inference/embeddings *(requires ADR/LATS gate)*
- SmolAgents for lightweight agent tasks *(optional — ADR/LATS-gated, OQ-002 resolved: not committed)*
- Data processing utilities: NumPy, Pandas, Matplotlib *(requires ADR/LATS gate)*
- DeCypher (conversational agent) and RoutesHQ (intent classifier) as idea apps built on the framework
- In-memory state checkpointing for workflow resumption (plain dict per session_id/thread_id, not persisted across restarts)
- Structured logging replacing print-based debugging

**OUT v1:**
- Custom model training / fine-tuning
- Multi-tenant auth / user management
- Persistent conversation storage (database-backed checkpoints)
- CI/CD pipeline (deferred to post-rewrite)
- Mobile frontend
- Agent marketplace / plugin system
- Dynamic agent discovery / registry
- Distributed tracing / OpenTelemetry (structured logging only in v1)

---

## S2: Container Diagram (L2)

3 containers. Python backend is a monolith with subpackages. Split only at real deployment boundaries (Python process vs JS frontend vs app layer).

| # | Container | Type | Tech Stack | Responsibility | Deploy |
|---|-----------|------|------------|----------------|--------|
| **C1** | **synapticore-core** | `agentic` | Python 3.12, LiteLLM, ag-ui-protocol, mcp[cli], FastMCP, httpx, Starlette, sse-starlette, Pydantic. Agent/ML frameworks (LangChain, LangGraph, PyTorch, etc.) are ADR/LATS-gated per component — see S3 Framework Policy. SmolAgents is optional/ADR-gated (OQ-002 resolved). | All Python logic: agent orchestration, tool library, protocol servers (A2A, MCP, AG-UI), shared types. Subpackages: `agents/`, `tools/`, `protocols/`, `types/`. Single uvicorn process serves all protocol endpoints as mounted sub-apps. | Single uvicorn process |
| **C2** | **synapticore-ui** | `traditional` | TypeScript, React 18, Vite, @ag-ui/client, @ag-ui/core | Unified frontend — consumes AG-UI event streams (SSE), sends user actions (HTTP POST), renders chat, tool outputs, state, and human-in-the-loop flows. | Vite dev server (dev) / static build (prod) |
| **C3** | **synapticore-apps** | `traditional` | Python 3.12, imports from C1 | Idea applications built on the framework — DeCypher (conversational agent), RoutesHQ (intent classifier), future experiments. Each app composes agents, tools, and workflows from C1. Apps are framework consumers, not agents themselves. | Run within C1's process or as standalone scripts |

**Agentic tagging note:** C1 is tagged `agentic` because its `agents/` subpackage contains agentic behavior (LLM-driven decision loops, tool selection, multi-step reasoning). Other subpackages (`tools/`, `types/`, `protocols/`) are traditional. CoALA specification applies to `agents/` components at L3. C3 (apps) is `traditional` — it composes agentic components from C1 but does not implement its own decision procedures.

### Communication

```
                        ┌──────────────────────────────┐
                        │      C2: synapticore-ui       │
                        │   React + Vite + @ag-ui       │
                        └──────────┬───────────────────┘
                                   │ AG-UI (SSE ↓, HTTP ↑)
                                   │
┌──────────────────────────────────┼─────────────────────────────────────┐
│                  C1: synapticore-core (single uvicorn process)         │
│                                  │                                     │
│  ┌──────────┐  ┌──────────┐  ┌──┴──────────────────┐  ┌──────────┐  │
│  │ agents/  │  │  tools/  │  │     protocols/       │  │  types/  │  │
│  │LangChain │←→│search,sql│  │  agui/ ← AG-UI SSE  │  │ Pydantic │  │
│  │LangGraph │  │calc, pdf │  │  a2a/  ← JSON-RPC   │  │ models   │  │
│  │a2a_client│  │          │  │  mcp/  ← FastMCP     │  │          │  │
│  └────┬─────┘  └──────────┘  └──┬──────────┬───────┘  └──────────┘  │
│       │                         │          │                          │
│       │ LiteLLM (all calls)     │          │                          │
│       ↓                         │          │                          │
│  LLM Providers                  │          │                          │
│  (Bedrock, Gemini,              │          │                          │
│   LM Studio)                    │          │                          │
│                                 │          │                          │
└─────────────────────────────────┼──────────┼──────────────────────────┘
                                  │          │
                    A2A (JSON-RPC/SSE)    MCP protocol
                                  │          │
                                  ↓          ↓
                         Remote A2A    Snowflake, Tavily,
                         Agents        DuckDuckGo
                         (.well-known/
                          agent.json)

┌──────────────────────────────────┐
│      C3: synapticore-apps        │
│      DeCypher, RoutesHQ          │──── Python imports (in-process from C1)
└──────────────────────────────────┘
```

### Cross-Cutting Concerns

**Configuration:**
- Single `.env` file loaded at startup via python-dotenv
- All subpackages share the process, so env vars are available everywhere
- Secrets: Tavily, AWS (Bedrock), Gemini, Snowflake creds via env vars. Env vars use LiteLLM-compatible names (AWS_ACCESS_KEY_ID, GEMINI_API_KEY, etc.) — the legacy ANTRHOPIC typo is dropped (OQ-032).
- LLM provider selection: LiteLLM model slug in config (e.g., `bedrock/claude-3`, `gemini/flash`, `openai/local-model` with `api_base`)

**Logging:**
- stdlib `logging` with structured JSON formatter
- Replace all `print()` with logger calls
- Log levels: DEBUG (LLM call traces), INFO (agent lifecycle), WARNING (fallbacks), ERROR (failures)
- LLM call logging: model, tokens, latency per call via LiteLLM callbacks
- Third-party framework logs (LangChain, LangGraph): captured by stdlib logging, level-gated to WARNING+ in production to avoid noise

**Persistence:**
- No persistent store in v1. Task state and conversation checkpoints are in-memory (plain dict per session_id/thread_id)
- Acknowledged limitation: state lost on restart. Persistent checkpointing is a post-v1 concern.

**Startup:**
- Single entry point: `uvicorn synapticore.main:app` (replaces current `mcpServer:main`)
- Mounts protocol sub-apps (A2A, MCP, AG-UI) on the main Starlette/FastAPI app
- Apps (C3) loaded as importable modules, optionally registered as agents on startup

### Key Decisions

| Decision | Rationale |
|----------|-----------|
| 3 containers, not 7 | Single developer, ~2,800 LOC alpha. Boundary contract tax of 7 containers outweighs protocol purity. Split when evidence demands it. |
| Single uvicorn process | A2A, MCP, AG-UI servers mounted as sub-apps. No multi-process orchestration overhead. |
| Monolith with subpackages | `agents/`, `tools/`, `protocols/`, `types/` are import boundaries, not package boundaries. Enforced by convention. |
| LiteLLM for all LLM calls | Eliminates `langchain-aws.ChatBedrock` and direct provider SDKs. Provider switching is a config change. |
| All agent/ML frameworks ADR-gated | LangChain, LangGraph, SmolAgents (optional, OQ-002), Google ADK (dropped, OQ-017), PyTorch, Transformers, NumPy, Pandas, Matplotlib — none committed. Each component's LLD specifies framework choice with mandatory ADR. Only LiteLLM is committed. |
| Google ADK dropped | OQ-017: Provider-agnostic routing matters more. Orchestrator uses a2a_client + Python loop directly. |
| Apps are traditional consumers | C3 composes agents from C1 but implements no decision procedures. `traditional` tag. |

---

## S3: Component Map (L3)

### Framework Policy

No agent or ML framework is committed. LangChain, LangGraph, SmolAgents, PyTorch, Transformers, NumPy, Pandas, Matplotlib — all require ADR/LATS gate before use in any component. The L3 defines framework-agnostic contracts. Each LLD specifies its framework choice with a mandatory ADR reference.

**Google ADK dropped (OQ-017)** — orchestrator uses plain Python + a2a_client. Provider-agnostic routing matters more than framework convenience. SmolAgents is optional/ADR-gated (OQ-002 resolved).

**Only committed frameworks:** LiteLLM (LLM routing), Pydantic (types), Starlette (server), React+Vite (frontend), AG-UI SDKs, MCP SDK.

### C1: synapticore-core

4 subpackages: `types/`, `tools/`, `protocols/`, `agents/`.

**Dependency direction:** `types/` (leaf) ← `tools/` ← `protocols/` ← `agents/`. No lateral deps between `tools/` and `protocols/`. `agui_server` receives agent executors via dependency injection at startup (no import-time dep on `agents/`).

**Error hierarchy:** `SynaptiCoreError` (base) → `ProviderError`, `ToolExecutionError`, `ConfigurationError`, `ToolNotFoundError`, `DuplicateToolError`. Protocol layers map internal errors to protocol-specific codes (JSON-RPC error codes for A2A, MCP error codes for MCP, `RunErrorEvent` for AG-UI).

---

#### C1.1 types/ (leaf — no internal deps)

**C1.1.1 a2a_types**
- **Responsibility:** Pydantic models for A2A protocol — task lifecycle, JSON-RPC messages, agent cards, protocol errors.
- **Contracts:** `Task`, `TaskState`, `TaskStatus`, `TaskSendParams`, `TaskQueryParams`, `Message`, `Part` (union: `TextPart | FilePart | DataPart`), `Artifact`, `AgentCard`, `AgentSkill`, `AgentCapabilities`, all JSON-RPC request/response pairs, `A2ARequest` (discriminated union), error types (`JSONParseError`, `InvalidRequestError`, `InternalError`, `TaskNotFoundError`, etc.), exceptions (`A2AClientError`, `A2AClientHTTPError`, `A2AClientJSONError`).
- **Dependencies:** None. Pydantic only.
- **LLD:** `lld/a2a-types.md`

**C1.1.2 agui_types**
- **Responsibility:** Pydantic models for AG-UI protocol events — run lifecycle, text streaming, tool calls, state sync, human-in-the-loop.
- **Contracts:** `RunStartedEvent`, `RunFinishedEvent`, `RunErrorEvent`, `TextMessageStartEvent`, `TextMessageContentEvent`, `TextMessageEndEvent`, `ToolCallStartEvent`, `ToolCallArgsEvent`, `ToolCallEndEvent`, `StateSnapshotEvent`, `StateDeltaEvent`, `MessagesSnapshotEvent`, `StepStartedEvent`, `StepFinishedEvent`, `CustomEvent`, `AgUiEvent` (discriminated union), `AgUiRunConfig`, `AgUiMessage`, `AgUiRole`.
- **Dependencies:** None. Pydantic only.
- **LLD:** `lld/agui-types.md`

**C1.1.3 mcp_types**
- **Responsibility:** Thin wrapper over MCP SDK types with project-specific extensions (tool metadata tagging).
- **Contracts:** `McpToolDefinition`, `McpToolResult`, `McpServerConfig`.
- **Dependencies:** None internally. MCP SDK types.
- **LLD:** `lld/mcp-types.md`

**C1.1.4 common_types**
- **Responsibility:** Shared domain models crossing subpackage boundaries — LLM config, conversation primitives, error base classes.
- **Contracts:** `LlmConfig` (model_slug, provider, temperature, max_tokens, api_base), `ConversationMessage`, `ConversationRole`, `ToolCall`, `ToolResult`, `TokenUsage`, `SynaptiCoreError` (base), `ProviderError`, `ConfigurationError`, `ToolExecutionError`.
- **Dependencies:** None. Pydantic only.
- **LLD:** `lld/common-types.md`

---

#### C1.2 tools/ (depends on types/ only)

**C1.2.1 llm_provider**
- **Responsibility:** Single gateway for all LLM calls. Wraps LiteLLM for unified async chat completion. All providers (Bedrock, Gemini, LM Studio) accessed through this module only.
- **Contracts:**
  - Input: `LlmConfig`, `list[ConversationMessage]`, `list[McpToolDefinition] | None`
  - Output: `LlmResponse` (content: str, tool_calls: `list[ToolCall] | None`, usage: `TokenUsage`, model: str, latency_ms: float)
  - Errors: `ProviderError`, `ConfigurationError`
- **Dependencies:** `types/common_types`. External: `litellm`.
- **LLD:** `lld/llm-provider.md`

**C1.2.2 web_search**
- **Responsibility:** Web search tools — Tavily (primary, API key required) and DuckDuckGo (free fallback for local dev).
- **Contracts:**
  - Input: `SearchQuery` (query: str, max_results: int, search_depth: str)
  - Output: `SearchResult` (results: `list[SearchResultItem]`, source: str)
  - Errors: `ToolExecutionError`
- **Dependencies:** `types/common_types`. External: `tavily`, DuckDuckGo client *(ADR: choose between langchain-community wrapper or direct API)*.
- **LLD:** `lld/web-search.md`

**C1.2.3 calculator**
- **Responsibility:** Safe math expression evaluator. Deterministic, no LLM call needed.
- **Contracts:**
  - Input: `CalcRequest` (expression: str)
  - Output: `CalcResult` (result: str, expression: str)
  - Errors: `ToolExecutionError`
- **Dependencies:** `types/common_types`. No external AI deps.
- **LLD:** `lld/calculator.md`

**C1.2.4 snowflake_connector**
- **Responsibility:** Snowflake SQL execution with parameterized queries (no SQL injection), connection pooling, result serialization. *(ADR: Pandas for result formatting vs. raw dicts.)*
- **Contracts:**
  - Input: `SnowflakeQuery` (sql: str, params: `dict[str, Any] | None`, timeout_seconds: int)
  - Output: `SnowflakeResult` (columns: `list[str]`, rows: `list[dict[str, Any]]`, row_count: int, execution_time_ms: float)
  - Errors: `ToolExecutionError`, `ConfigurationError`
- **Dependencies:** `types/common_types`. External: `snowflake-connector-python`.
- **LLD:** `lld/snowflake-connector.md`

**C1.2.5 pdf_processor**
- **Responsibility:** PDF text extraction and chunking for agent consumption. *(ADR: PyMuPDF vs. alternatives.)*
- **Contracts:**
  - Input: `PdfProcessRequest` (file_path: str | bytes, pages: `list[int] | None`)
  - Output: `PdfProcessResult` (pages: `list[PdfPage]`, total_pages: int)
  - Errors: `ToolExecutionError`
- **Dependencies:** `types/common_types`. External: *(ADR-gated)*.
- **LLD:** `lld/pdf-processor.md`

**C1.2.6 tool_registry**
- **Responsibility:** Central registry for all tools. Runtime singleton, populated at startup. Agents query it for available tools. MCP server reads it to expose tools externally.
- **Contracts:**
  - Register: `ToolRegistration` (name: str, description: str, input_schema: dict, handler: `Callable`)
  - Query: `get_tools(names: list[str] | None) -> list[ToolDefinition]`
  - `ToolDefinition`: (name: str, description: str, input_schema: dict)
  - Errors: `ToolNotFoundError`, `DuplicateToolError`
- **Dependencies:** `types/common_types`, `types/mcp_types`.
- **LLD:** `lld/tool-registry.md`

---

#### C1.3 protocols/ (depends on types/; mcp_server depends on tools/tool_registry)

**C1.3.1 a2a_server**
- **Responsibility:** A2A JSON-RPC server. Validates incoming requests via discriminated union, dispatches to TaskManager, returns JSON or SSE streaming. Serves `/.well-known/agent.json`. Starlette sub-app mounted on main server.
- **Contracts:**
  - HTTP IN: POST `/a2a/` (body: `A2ARequest`)
  - HTTP IN: GET `/a2a/.well-known/agent.json` → `AgentCard`
  - HTTP OUT: `JSONRPCResponse` | `EventSourceResponse` (SSE stream)
  - Errors: JSON-RPC error responses (`JSONParseError`, `InvalidRequestError`, `InternalError`)
- **Dependencies:** `types/a2a_types`, `protocols/a2a_task_manager`. External: `starlette`, `sse-starlette`.
- **LLD:** `lld/a2a-server.md`

**C1.3.2 a2a_client**
- **Responsibility:** Async HTTP client for sending tasks to remote A2A agents. Supports request-response and SSE streaming modes.
- **Contracts:**
  - Input: `SendTaskRequest`, `GetTaskRequest`, `CancelTaskRequest`, `SetTaskPushNotificationRequest`, `GetTaskPushNotificationRequest`
  - Output: Corresponding response types or `AsyncIterable[SendTaskStreamingResponse]`
  - Errors: `A2AClientHTTPError`, `A2AClientJSONError`
- **Dependencies:** `types/a2a_types`. External: `httpx`, `httpx-sse`.
- **LLD:** `lld/a2a-client.md`

**C1.3.3 a2a_task_manager**
- **Responsibility:** Abstract task lifecycle manager + in-memory reference implementation. Task state (submitted/working/completed/failed/cancelled/input-required), history, SSE subscriber queues, push notification config.
- **Contracts:**
  - Abstract: `TaskManager` (7 async methods: get, cancel, send, subscribe, set_push, get_push, resubscribe)
  - Concrete: `InMemoryTaskManager` (dict-based storage, asyncio locks, SSE queue management)
  - All JSON-RPC request/response pairs from `types/a2a_types`
- **Dependencies:** `types/a2a_types`.
- **LLD:** `lld/a2a-task-manager.md`

**C1.3.4 a2a_card_resolver**
- **Responsibility:** Fetches and validates `AgentCard` from a remote agent's `/.well-known/agent.json` endpoint.
- **Contracts:**
  - Input: base_url: str
  - Output: `AgentCard`
  - Errors: `A2AClientHTTPError`, `A2AClientJSONError`
- **Dependencies:** `types/a2a_types`. External: `httpx`.
- **LLD:** `lld/a2a-card-resolver.md`

**C1.3.5 mcp_server**
- **Responsibility:** FastMCP server exposing tools from `tool_registry` as MCP-protocol endpoints. Mounted as sub-app on main server.
- **Contracts:**
  - Reads from: `tool_registry.get_tools()`
  - MCP IN: tool discovery, tool invocation
  - MCP OUT: `McpToolResult`
  - Errors: `ToolExecutionError` mapped to MCP error responses
- **Dependencies:** `types/mcp_types`, `tools/tool_registry`. External: `mcp[cli]`, `FastMCP`.
- **LLD:** `lld/mcp-server.md`

**C1.3.6 agui_server**
- **Responsibility:** AG-UI protocol backend. Accepts user messages via HTTP POST, streams agent execution events to frontend via SSE. Translates agent lifecycle into AG-UI protocol events. Receives agent executor callables via dependency injection at startup (no import-time dep on `agents/`).
- **Contracts:**
  - HTTP IN: POST `/agui/runs` with `AgUiRunConfig` (agent_id: str, messages: `list[AgUiMessage]`, thread_id: str | None)
  - HTTP OUT (SSE): Stream of `AgUiEvent` (discriminated union)
  - Errors: `RunErrorEvent` in SSE stream, HTTP 400/500 for malformed requests
- **Dependencies:** `types/agui_types`, `types/common_types`. Agent executors injected at runtime.
- **LLD:** `lld/agui-server.md`

**C1.3.7 app_server**
- **Responsibility:** Main Starlette/FastAPI application. Single entry point (`uvicorn synapticore.main:app`). Mounts protocol sub-apps, loads `.env`, initializes logging, registers tools, wires agent executors into `agui_server`.
- **Contracts:**
  - Mounts: `a2a_server` at `/a2a/`, `mcp_server` at `/mcp/`, `agui_server` at `/agui/`
  - Startup: env loading, tool registration, agent initialization, logging config
- **Dependencies:** All protocol sub-apps, `tools/tool_registry`. External: `starlette`, `uvicorn`, `python-dotenv`.
- **LLD:** `lld/app-server.md`

---

#### C1.4 agents/ (agentic — CoALA applies)

**C1.4.1 decypher_agent**
- **Responsibility:** Conversational agent with tool access. Receives user messages, reasons about whether to use tools or respond directly, executes tool calls if needed, returns responses. *(OQ-001 resolved: plain Python loop, single reasoning pass — not ReAct loop.)*
- **Contracts:**
  - Input: `ConversationMessage`
  - Output: `ConversationMessage` or async stream of `AgUiEvent` (when invoked via `agui_server`)
  - Tools accessed via: `tool_registry` (web_search, calculator, extensible)
- **Dependencies:** `types/common_types`, `types/agui_types`, `tools/llm_provider`, `tools/tool_registry`.

**CoALA:**
```
### Agent: decypher_agent
Pattern: Augmented LLM
Loop: observe(user message) → retrieve(tool execution, e.g. web search) → reason(LLM call with tool defs + results) → [execute(next tool call)] → respond/loop
Memory: working(context window, budget per LlmConfig), episodic(plain dict per thread_id), semantic(none — no persistent knowledge base in v1), procedural(system prompt template)
Actions: internal(reasoning via LLM), external(web_search: static-contract, calculator: static-contract, llm_provider: versioned-artifact), boundaries(no filesystem access, no arbitrary code execution, no network calls outside registered tools)
Stops when: LLM returns response without tool calls, OR max iterations reached (configurable, default 10)
Human-in-loop: none in v1 (future: AG-UI interrupt events)
Version pins: LLM model slug per LlmConfig
Eval thresholds: none v1 (deferred — llm_provider is versioned-artifact but eval infra not yet built)
```
- **LLD:** `lld/decypher-agent.md`

**C1.4.2 host_orchestrator**
- **Responsibility:** Multi-agent orchestrator using plain Python async loop + a2a_client. Discovers available remote agents via agent cards, delegates tasks via A2A protocol, aggregates results, manages session state.
- **Contracts:**
  - Input: `Message` (A2A) from `a2a_task_manager`
  - Output: `Task` (A2A) with aggregated results
  - Remote calls: `a2a_client.send_task` / `a2a_client.send_task_streaming`
  - Discovery: `a2a_card_resolver.get_agent_card` at startup (static list of agent URLs)
- **Dependencies:** `types/a2a_types`, `types/common_types`, `protocols/a2a_client`, `protocols/a2a_card_resolver`, `tools/llm_provider`.

**CoALA:**
```
### Agent: host_orchestrator
Pattern: Orchestrator-Workers
Loop: observe(user request) → retrieve(list available agents from card registry) → reason(select agent + formulate task via LLM) → execute(send_task to remote agent) → observe(result) → [reason(need more agents?) → loop] → respond
Memory: working(context window via LiteLLM), episodic(in-memory dict per session_id), semantic(agent card registry: name→description→skills), procedural(root_instruction prompt template)
Actions: internal(agent selection reasoning via LLM), external(list_remote_agents: static-contract, send_task: versioned-artifact — output depends on downstream agent's model version, a2a_card_resolver: static-contract, llm_provider: versioned-artifact), boundaries(cannot execute tools directly — delegates to remote agents only, cannot modify agent cards, cannot discover agents dynamically in v1)
Stops when: all delegated tasks complete/fail/cancel, OR user cancels, OR input_required escalation from remote agent
Human-in-loop: input_required state triggers escalation to user via AG-UI
Version pins: LLM model slug (overridable via LlmConfig)
Eval thresholds: none v1 (send_task is versioned-artifact — eval deferred)
```
- **LLD:** `lld/host-orchestrator.md`

---

### C2: synapticore-ui (traditional — no CoALA)

**C2.1 agui_client**
- **Responsibility:** AG-UI client layer. Connects to backend SSE endpoint, deserializes `AgUiEvent` stream, exposes typed event callbacks for React components.
- **Contracts:**
  - Input: `AgUiRunConfig` (sent via HTTP POST to `/agui/runs`)
  - Output: Typed event callbacks: `onRunStarted`, `onTextMessageStart/Content/End`, `onToolCallStart/Args/End`, `onStateSnapshot/Delta`, `onStepStarted/Finished`, `onRunFinished`, `onRunError`
  - Errors: connection errors, malformed SSE events
- **Dependencies:** External: `@ag-ui/client`, `@ag-ui/core`.
- **LLD:** `lld/agui-client.md`

**C2.2 chat_view**
- **Responsibility:** React component rendering the conversational UI — message list, user input, typing indicators, tool call visualizations, state displays.
- **Contracts:**
  - Props: AG-UI event stream from `agui_client`
  - Emits: user messages (HTTP POST to `/agui/runs` via `agui_client`)
  - Renders: message bubbles, tool call cards, streaming indicators, error displays
- **Dependencies:** `C2.1 agui_client`. External: React 18.
- **LLD:** `lld/chat-view.md`

**C2.3 app_shell**
- **Responsibility:** Top-level React application shell. Layout, error boundary, Vite entry point. Hosts `chat_view` as primary view.
- **Contracts:**
  - Renders: `chat_view` as main content
  - Config: API base URL (from Vite env vars)
- **Dependencies:** `C2.2 chat_view`. External: React 18, Vite.
- **LLD:** `lld/app-shell.md`

---

### C3: synapticore-apps (traditional — no CoALA)

Apps are idea POCs built on C1. They compose agents, tools, and workflows from the framework. Each app is a traditional consumer — no decision procedures of its own.

**C3.1 decypher_app**
- **Responsibility:** DeCypher application configuration. Defines system prompt, tool set, LLM config, and entry point. Composes `decypher_agent` from C1 with specific configuration.
- **Contracts:**
  - Exports: `create_decypher_agent(config: DecypherConfig) -> AgentInstance`
  - `DecypherConfig`: (llm_config: `LlmConfig`, tools: `list[str]`, system_prompt: str | None)
  - Registers with: `tool_registry` (optional MCP exposure), `a2a_server` (optional A2A exposure)
- **Dependencies:** C1: `agents/decypher_agent`, `tools/llm_provider`, `tools/tool_registry`, `types/common_types`.
- **LLD:** `lld/decypher-app.md`

**C3.2 routeshq_app**
- **Responsibility:** RoutesHQ intent classification POC. Classifies user input into first-query, follow-up, or salutation intents using LLM calls. Single Augmented LLM call per classification — 1 dynamic decision point, below the 3-point threshold for agentic treatment. CoALA overhead not warranted.
- **Contracts:**
  - Exports: `classify_intent(request: IntentRequest) -> IntentResponse`
  - `IntentRequest`: (query: str, is_first_query: bool, context: `dict[str, Any] | None`)
  - `IntentResponse`: `FirstQueryIntent | FollowupQueryIntent | SalutationIntent`
  - Intent types: `FirstQueryIntentType` (SQL_ONLY, SQL_AND_CHART), `FollowupQueryIntentType` (MODIFY_SQL_AND_CHART, MODIFY_CHART_ONLY), `SalutationType` (GREETING, GOODBYE, THANKS, OTHER)
- **Dependencies:** C1: `tools/llm_provider`, `types/common_types`.
- **LLD:** `lld/routeshq-app.md`

---

### Open Questions from L3

| ID | Blocks | Summary |
|----|--------|---------|
| OQ-001 | `decypher_agent` | ~~Agent execution framework.~~ **Resolved:** plain Python loop, single reasoning pass (Augmented LLM, not ReAct). |
| OQ-002 | `tools/*` | ~~SmolAgents coexistence with LiteLLM-based tools.~~ **Resolved:** SmolAgents optional/ADR-gated, not committed. |
| OQ-003 | future tool | Local embeddings/inference tool using PyTorch + Transformers. Not needed for v1 core — defer to post-core implementation. Requires ADR if added. |
| OQ-004 | `snowflake_connector` | Pandas for result formatting vs. raw dict serialization. Requires ADR. |
| OQ-005 | future tool | Data visualization tool using NumPy + Matplotlib. Not needed for v1 core — defer. Requires ADR if added. |
| OQ-006 | `pdf_processor` | PyMuPDF vs. alternative PDF library. Requires ADR. |
| OQ-007 | `web_search` | DuckDuckGo client: langchain-community wrapper vs. direct API. Requires ADR. |

---

### Dependency Summary

```
types/  (leaf — Pydantic only)
  ├── a2a_types
  ├── agui_types
  ├── mcp_types
  └── common_types

tools/  (depends on types/)
  ├── llm_provider         → common_types
  ├── web_search           → common_types
  ├── calculator           → common_types
  ├── snowflake_connector  → common_types
  ├── pdf_processor        → common_types
  └── tool_registry        → common_types, mcp_types

protocols/  (depends on types/; mcp_server also depends on tools/tool_registry)
  ├── a2a_server           → a2a_types, a2a_task_manager
  ├── a2a_client           → a2a_types
  ├── a2a_task_manager     → a2a_types
  ├── a2a_card_resolver    → a2a_types
  ├── mcp_server           → mcp_types, tools/tool_registry
  ├── agui_server          → agui_types, common_types (agent executors injected at runtime)
  └── app_server           → all sub-apps, tools/tool_registry

agents/  (depends on types/ + tools/; receives calls from agui_server via injection)
  ├── decypher_agent       → common_types, agui_types, llm_provider, tool_registry
  └── host_orchestrator    → a2a_types, common_types, a2a_client, a2a_card_resolver, llm_provider

C2: ui  (connects to C1 via HTTP/SSE only)
  ├── agui_client          → @ag-ui/client
  ├── chat_view            → agui_client
  └── app_shell            → chat_view

C3: apps  (imports from C1 in-process)
  ├── decypher_app         → agents/decypher_agent, tools/*, types/*
  └── routeshq_app         → tools/llm_provider, types/common_types
```

### Component Count

| Container | Components | Notes |
|-----------|-----------|-------|
| C1 types/ | 4 | Leaf models |
| C1 tools/ | 6 | Framework-agnostic |
| C1 protocols/ | 7 | Server adapters |
| C1 agents/ | 2 | CoALA-specified |
| C2 ui | 3 | React + AG-UI |
| C3 apps | 2 | Idea POCs |
| **Total** | **24** | |

---

## S4: Primary Data Flows (max 3)

### Flow 1: User → Chat → Agent → Tool → Response

```
User (browser)
  → C2/chat_view (user message)
  → C2/agui_client (HTTP POST /agui/runs with AgUiRunConfig)
  → C1/agui_server (deserialize, invoke agent executor)
  → C1/agents/decypher_agent (observe: user message)
    → C1/tools/llm_provider (reason: LLM call with tool defs)
    → LLM Provider (via LiteLLM)
    → [if tool_call: C1/tools/web_search or calculator (retrieve/execute)]
    → C1/tools/llm_provider (reason: LLM call with tool results)
    → LLM Provider
  → C1/agui_server (translate agent events → AgUiEvent stream)
  → C2/agui_client (SSE: TextMessageStart → TextMessageContent* → TextMessageEnd)
  → C2/chat_view (render streamed response)
```

### Flow 2: Host Orchestrator → Remote A2A Agent → Result

```
User request (via agui_server or a2a_server)
  → C1/agents/host_orchestrator (observe: request)
    → list_remote_agents() (retrieve: agent card registry)
    → LLM (reason: select agent + formulate task)
    → C1/protocols/a2a_client.send_task (execute: delegate to remote agent)
      → Remote A2A Agent (JSON-RPC POST /a2a/)
      → [SSE stream: TaskStatusUpdateEvent*, TaskArtifactUpdateEvent*]
    → C1/agents/host_orchestrator (observe: result, reason: need more agents?)
  → Task (A2A) with aggregated results
```

### Flow 3: MCP Client → Tool Execution

```
External MCP Client
  → C1/protocols/mcp_server (tool discovery / tool invocation)
  → C1/tools/tool_registry.get_tools() (resolve tool)
  → C1/tools/<specific_tool>.handler() (execute: e.g. snowflake_connector)
    → External system (Snowflake, Tavily, etc.)
  → McpToolResult
  → External MCP Client
```

---

## S5: Decision Index

Pending ADRs from L3 open questions:

| ADR | Component | Topic | Status |
|-----|-----------|-------|--------|
| — | decypher_agent | Agent execution framework (OQ-001) | **Resolved** — plain Python loop (single reasoning pass, not ReAct) |
| — | tools/* | SmolAgents removal from locked stack (OQ-002) | **Resolved** — SmolAgents optional/ADR-gated, not committed |
| TBD | snowflake_connector | Pandas vs. raw dicts (OQ-004) | Evaluate during implementation |
| TBD | pdf_processor | PyMuPDF vs. alternative (OQ-006) | Evaluate during implementation |
| TBD | web_search | DuckDuckGo client choice (OQ-007) | Evaluate during implementation |

---

## S6: Open Questions

See [open-questions.md](open-questions.md).

---

## S7: Boundary Matrix

### Internal Boundaries (C1 subpackage → subpackage)

| Upstream | Contract | Downstream | Error Type | Serialization | Stability | Status |
|----------|----------|------------|------------|---------------|-----------|--------|
| agents/decypher_agent | `LlmConfig`, `list[ConversationMessage]` → `LlmResponse` | tools/llm_provider | `ProviderError` | In-process (Pydantic) | `versioned-artifact(LlmConfig.model_slug)` | Defined |
| agents/decypher_agent | `get_tools(names)` → `list[ToolDefinition]` | tools/tool_registry | `ToolNotFoundError` | In-process (Pydantic) | static | Defined |
| agents/host_orchestrator | `SendTaskRequest` → `SendTaskResponse` / `AsyncIterable[SendTaskStreamingResponse]` | protocols/a2a_client | `A2AClientHTTPError`, `A2AClientJSONError` | In-process (Pydantic) | `versioned-artifact(remote agent model)` | Defined |
| agents/host_orchestrator | `base_url` → `AgentCard` | protocols/a2a_card_resolver | `A2AClientHTTPError`, `A2AClientJSONError` | In-process (Pydantic) | static | Defined |
| agents/host_orchestrator | `LlmConfig`, `list[ConversationMessage]` → `LlmResponse` | tools/llm_provider | `ProviderError` | In-process (Pydantic) | `versioned-artifact(LlmConfig.model_slug)` | Defined |
| protocols/a2a_server | `A2ARequest` → dispatch | protocols/a2a_task_manager | JSON-RPC errors | In-process (Pydantic) | static | Defined |
| protocols/mcp_server | `get_tools()` → `list[ToolDefinition]` | tools/tool_registry | `ToolNotFoundError` | In-process (Pydantic) | static | Defined |
| protocols/agui_server | agent executor callable → `AgUiEvent` stream | agents/* (injected) | `RunErrorEvent` | In-process (async generator) | `versioned-artifact(agent's LlmConfig)` | Defined |
| protocols/app_server | startup wiring | all sub-apps, tool_registry | `ConfigurationError` | In-process | static | Defined |
| tools/web_search | `SearchQuery` → `SearchResult` | (external: Tavily / DuckDuckGo) | `ToolExecutionError` | HTTPS / JSON | static | Defined |
| tools/snowflake_connector | `SnowflakeQuery` → `SnowflakeResult` | (external: Snowflake) | `ToolExecutionError`, `ConfigurationError` | Snowflake connector | static | Defined |
| tools/llm_provider | `LlmConfig` + messages → `LlmResponse` | (external: LiteLLM → LLM providers) | `ProviderError` | HTTPS / JSON (via LiteLLM) | `versioned-artifact(model_slug)` | Defined |
| C3/decypher_app | `DecypherConfig` → `AgentInstance` | agents/decypher_agent | `ConfigurationError` | In-process (Pydantic) | static | Defined |
| C3/routeshq_app | `IntentRequest` → `IntentResponse` | tools/llm_provider | `ProviderError` | In-process (Pydantic) | `versioned-artifact(model_slug)` | Defined |

### Cross-Container Boundaries (network)

| Upstream | Contract | Downstream | Error Type | Serialization | Stability | Status |
|----------|----------|------------|------------|---------------|-----------|--------|
| C2/agui_client | POST `/agui/runs` (`AgUiRunConfig`) → SSE stream of `AgUiEvent` | C1/agui_server | `RunErrorEvent`, HTTP 400/500 | JSON (HTTP) + SSE (events) | `versioned-artifact(agent's model)` | Defined |
| C2/agui_client | User messages (HTTP POST) | C1/agui_server | HTTP 400/500 | JSON | static | Defined |
| Remote A2A Agents | POST `/a2a/` (`A2ARequest`) → `JSONRPCResponse` / SSE | C1/a2a_server | JSON-RPC errors | JSON / SSE | static | Defined |
| C1/a2a_client | POST to remote `/a2a/` | Remote A2A Agents | `A2AClientHTTPError`, `A2AClientJSONError` | JSON / SSE | `versioned-artifact(remote model)` | Defined |
| C1/a2a_server | GET `/.well-known/agent.json` | (any A2A client) | HTTP 404 | JSON | static | Defined |

### Stability Legend

- **static** — deterministic contract, schema fixed between deployments
- **versioned-artifact(pin)** — output depends on artifact version (LLM model, embedding model). Eval obligations apply at LLD level.

### Audit Notes

- All `versioned-artifact` boundaries trace back to `llm_provider` or remote agent models. No component bypasses LiteLLM.
- No `data-dependent` boundaries in v1 (no feature stores, search indices, or corpora).
- Error mapping: internal `SynaptiCoreError` hierarchy → JSON-RPC codes (A2A), MCP error codes (MCP), `RunErrorEvent` (AG-UI). Each protocol server LLD must specify the mapping table.
- `agui_server` → `agents/*` boundary uses dependency injection, not import. The contract is the async generator signature, typed via `AgUiEvent`.

---

## S8: Phase Plan & Test Gate Summary

### Phase 1: Foundation (types + tools + app_server)

| Component | Test Gate |
|-----------|-----------|
| C1.1.1 a2a_types | Unit: model validation, serialization round-trip |
| C1.1.2 agui_types | Unit: event model validation |
| C1.1.3 mcp_types | Unit: model validation |
| C1.1.4 common_types | Unit: model validation, error hierarchy |
| C1.2.1 llm_provider | Unit: mock LiteLLM, test config routing. Integration: real LLM call (1 provider). |
| C1.2.3 calculator | Unit: expression eval, error cases |
| C1.2.6 tool_registry | Unit: register, query, duplicate, not-found |
| C1.3.7 app_server | Integration: startup, sub-app mounting, env loading |

**System test:** `app_server` starts, tool_registry populated, llm_provider responds to a mock call.

### Phase 2: Protocol Servers (A2A + MCP + AG-UI)

| Component | Test Gate |
|-----------|-----------|
| C1.3.1 a2a_server | Unit: request validation, dispatch. Integration: JSON-RPC round-trip. |
| C1.3.2 a2a_client | Unit: mock HTTP. Integration: client→server round-trip. |
| C1.3.3 a2a_task_manager | Unit: task lifecycle, SSE queues. |
| C1.3.4 a2a_card_resolver | Unit: mock HTTP. Integration: real card fetch. |
| C1.3.5 mcp_server | Unit: tool exposure. Integration: MCP client→server round-trip. |
| C1.3.6 agui_server | Unit: event translation. Integration: HTTP POST → SSE stream. |

**System test:** A2A client sends task to local A2A server, gets response. MCP client discovers and invokes a tool. AG-UI client sends message, receives SSE event stream.

### Phase 3: Agents + Remaining Tools

| Component | Test Gate |
|-----------|-----------|
| C1.2.2 web_search | Unit: mock APIs. Integration: real Tavily call. |
| C1.2.4 snowflake_connector | Unit: mock connector. Integration: real Snowflake query (if creds available). |
| C1.2.5 pdf_processor | Unit: test PDF extraction. |
| C1.4.1 decypher_agent | Unit: mock llm_provider, test tool selection loop. Integration: real LLM + tools. |
| C1.4.2 host_orchestrator | Unit: mock a2a_client, test agent selection. Integration: real A2A delegation. |

**System test:** decypher_agent handles a multi-turn conversation with tool use. host_orchestrator delegates to a local A2A agent and returns results.

### Phase 4: Frontend + Apps

| Component | Test Gate |
|-----------|-----------|
| C2.1 agui_client | Unit: mock SSE stream, test event callbacks. |
| C2.2 chat_view | Unit: component rendering, event handling. |
| C2.3 app_shell | Unit: layout, error boundary. Integration: full UI → backend round-trip. |
| C3.1 decypher_app | Integration: create agent, run conversation via UI. |
| C3.2 routeshq_app | Unit: intent classification with mock LLM. Integration: real classification. |

**System test:** End-to-end — user sends message in UI → agent processes → tools execute → response streams back to UI via AG-UI.

### Phase Summary

| Phase | Components | Focus | Checkpoint |
|-------|-----------|-------|------------|
| P1 Foundation | 8 | Types, core tools, server shell | `monke-docs/checkpoints/phase-1-checkpoint.md` |
| P2 Protocols | 6 | A2A, MCP, AG-UI servers | `monke-docs/checkpoints/phase-2-checkpoint.md` |
| P3 Agents | 5 | Agent logic, remaining tools | `monke-docs/checkpoints/phase-3-checkpoint.md` |
| P4 Frontend + Apps | 5 | React UI, idea apps | `monke-docs/checkpoints/phase-4-checkpoint.md` |
