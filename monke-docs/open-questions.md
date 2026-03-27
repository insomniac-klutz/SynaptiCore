# Open Questions — SynaptiCore

> Updated: 2026-03-26 — all 32 OQs resolved or deferred.

## Framework & Dependencies (from L3)

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-001 | `decypher_agent` | Agent execution framework: LangGraph StateGraph, plain Python loop, or other? LangChain ecosystem was used for learning, not a committed choice. Requires ADR/LATS gate. | Plain Python async loop. | Resolved |
| OQ-002 | `tools/*` | SmolAgents coexistence with LiteLLM-based tools. All tool rewrites eliminate SmolAgents dependency — ADR may conclude removal from locked stack. Requires LATS/ADR. | Keep SmolAgents as optional dependency. | Resolved |
| OQ-003 | future tool | Local embeddings/inference tool using PyTorch + Transformers. Not needed for v1 core — defer to post-core implementation. Requires ADR if added. | Deferred to post-v1. | Deferred |
| OQ-004 | `snowflake_connector` | Pandas for result formatting vs. raw dict serialization. Requires ADR. | Pandas required for Snowflake results. | Resolved |
| OQ-005 | future tool | Data visualization tool using NumPy + Matplotlib. Not needed for v1 core — defer. Requires ADR if added. | Deferred to post-v1. | Deferred |
| OQ-006 | `pdf_processor` | PyMuPDF vs. alternative PDF library. Requires ADR. | Defer binding — evaluate during implementation, pick what gives best results. | Resolved |
| OQ-007 | `web_search` | DuckDuckGo client: langchain-community wrapper vs. direct API. Requires ADR. | Defer binding — evaluate during implementation. | Resolved |

## Data Model

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-008 | `types/*`, protocol upgrades | No schema versioning for AG-UI/A2A Pydantic models. Protocol spec updates break consumers with no migration path. | No versioning in v1, update atomically. | Resolved |
| OQ-009 | `agui_server`, `decypher_agent` | Two message types (`ConversationMessage` vs `AgUiMessage`) with no documented translation layer. `arguments` dict-vs-JSON-string mismatch risks double-encoding at LiteLLM boundary. | agui_server owns ConversationMessage↔AgUiMessage translation. | Resolved |
| OQ-010 | `agents/*`, `app_server` | `LlmConfig` set once at startup from env — no per-request override, no runtime fallback. Server locked to one model per agent until restart. | Per-agent default LlmConfig with per-request override via optional field in AgUiRunConfig. | Resolved |

## Communication Patterns

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-011 | `agui_server`, `agui_client` | No SSE heartbeat/keepalive. Proxies kill idle SSE connections after 30-60s. Long agent tasks produce gaps exceeding typical idle timeouts. | SSE comment heartbeat every 15s. | Resolved |
| OQ-012 | `agui_server`, `a2a_server` | Two SSE implementations (AG-UI + A2A) share one asyncio event loop. No contention or interference analysis. | Separate thread pools for A2A and AG-UI SSE handlers. | Resolved |
| OQ-013 | `agui_server`, UI | No agent discovery endpoint. UI must hardcode `agent_id`. A2A has `/.well-known/agent.json` but AG-UI has no equivalent. | Add GET /agui/agents discovery endpoint. | Resolved |

## Error Strategy

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-014 | `agui_server`, UI | Provider-specific error details (model slugs, rate limits) leak to end users via `RunErrorEvent`. No error sanitization. | Sanitize errors at agui_server, log raw details server-side. | Resolved |
| OQ-015 | `decypher_agent` | Tool failure: no programmatic retry/skip/abort. LLM decides but loops on failing tools. No transient-vs-permanent distinction. | Feed tool errors to LLM with same-tool-same-args loop breaker (max 2 identical calls). | Resolved |
| OQ-016 | `agui_server`, UI | Cascading failure UX undefined: LLM down → stream ends → UI has no retry/reconnect. Conversation context lost mid-stream. | UI retry button on RunErrorEvent, client preserves conversation history. | Resolved |

## State Management

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-017 | `decypher_agent`, `host_orchestrator` | No unified state management. DeCypher uses dict (or LangGraph per OQ-001). Host uses ADK session. Context doesn't transfer between agents. | Drop Google ADK entirely. Orchestrator uses plain a2a_client + Python async loop. Full provider-agnostic routing via LiteLLM. State is dict-based. google-adk and google-genai removed from committed deps (move to optional or drop). | Resolved |
| OQ-018 | `agui_server`, security | `thread_id` hijack risk. No auth + client-provided `thread_id` = any client can read/write any thread's memory. | Server-generated UUID4 only, ignore client-provided thread_id. | Resolved |
| OQ-019 | `agui_server`, UI | No session concept spanning multiple AG-UI runs. No server-side history query. Client state lost on refresh. | Lightweight server sessions with GET /agui/threads/{thread_id}/messages recovery endpoint. | Resolved |

## Agentic Patterns

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-020 | `decypher_agent` docs | CoALA labels DeCypher "Augmented LLM" but the loop is ReAct (multi-iteration reason+act). Mislabel affects eval design. | Keep "Augmented LLM" label. Rewrite fixes the looping — design as proper Augmented LLM (single reasoning pass with tool augmentation), not ReAct. | Resolved |
| OQ-021 | `host_orchestrator`, `tool_registry` | ADK tools not in `tool_registry`. MCP can't expose them. Other agents can't discover them. Hidden tool bifurcation. | A2A delegation stays internal to orchestrator, not in tool_registry. | Resolved |
| OQ-022 | `agents/*` | No local agent-to-agent call path. Co-located agents must go through A2A over HTTP. Adds unnecessary latency. | A2A over HTTP for all agent-to-agent, even local. Consistency over latency. | Resolved |

## Boundaries

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-023 | `agui_server`, security | No max request body size. `AgUiRunConfig.messages` grows every turn. Single large POST can exhaust memory. | Both body size limit (5MB) + message count limit (100 messages). | Resolved |
| OQ-024 | `agui_server`, scale | No max concurrent SSE connections. Each spawns 2+ asyncio tasks. No backpressure. | Semaphore limit, max 50 concurrent SSE connections, 503 when full. | Resolved |
| OQ-025 | `tool_registry`, `decypher_agent` | No tool execution timeout. Hung tool blocks agent loop indefinitely. Only `snowflake_connector` has its own timeout. | Global 30s timeout in execute_tool via asyncio.wait_for, per-tool override supported. | Resolved |

## Scale

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-026 | `app_server`, deployment | Single-process concurrency unvalidated under mixed protocol load. No benchmarks, no capacity plan. | Accept single-process for v1, benchmark post-implementation. | Resolved |
| OQ-027 | `decypher_agent`, scale | No memory budget per conversation thread. In-memory dict grows without bound or eviction. Will OOM. | Sliding window, max 200 messages per thread, oldest evicted. | Resolved |
| OQ-028 | `agui_server`, `a2a_task_manager` | No execution queue or admission control. All runs spawn immediately. Burst traffic cascades LLM rate limits. | Semaphore limit, max 5 concurrent agent runs, queue with timeout. | Resolved |

## Business Logic

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-029 | `agui_server`, UI | Agent routing is manual (`agent_id`). RoutesHQ exists but isn't wired into AG-UI flow. No intent-based routing. | Manual agent selection via discovery endpoint for v1. Intent-based routing post-v1. | Resolved |
| OQ-030 | UI, `agui_client` | UI supports one agent conversation at a time. No multi-pane or parallel agent views. | Tabbed conversations from day one. Multiple agui_client instances, tab UI. | Resolved |

## Flash Shortcuts

| ID | Blocks | Summary | Resolution | Status |
|----|--------|---------|------------|--------|
| OQ-031 | `decypher_agent`, `tool_registry` | Tool defs frozen at agent creation (flash shortcut). Registry supports runtime changes but agents snapshot once. MCP sees live; agents see stale. | Agents query tool_registry per-request, no snapshot. Always live. | Resolved |
| OQ-032 | `.env.template`, `app_server` | `ANTRHOPIC` env var typo: no decision to fix or preserve in rewrite. If fixed without updating template, Bedrock auth silently fails. | Use LiteLLM-compatible env vars (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, GEMINI_API_KEY etc). LiteLLM reads natively — zero mapping code. Drop ANTRHOPIC typo. | Resolved |
