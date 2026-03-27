# Gap Analysis — SynaptiCore

> Generated: 2026-03-25 by `/monke-recon:orchestra` Phase 3
> Scope: Alpha v1 rewrite. 9 dimensions, 63 gaps identified.

---

## Summary

| Dimension | Critical | High | Medium | Low | Total |
|-----------|----------|------|--------|-----|-------|
| 1. Error Handling | 1 | 4 | 3 | 2 | 10 |
| 2. Security | 1 | 4 | 4 | 1 | 10 |
| 3. Performance | 0 | 3 | 4 | 3 | 10 |
| 4. Observability | 0 | 3 | 3 | 1 | 7 |
| 5. Testing | 1 | 3 | 2 | 1 | 7 |
| 6. Data Integrity | 0 | 3 | 2 | 1 | 6 |
| 7. Documentation | 0 | 3 | 2 | 0 | 5 |
| 8. Architecture | 3 | 3 | 2 | 1 | 9 |
| 9. Accessibility | 0 | 0 | 2 | 2 | 4 |
| **Total** | **6** | **26** | **24** | **12** | **68** |

---

## Critical Gaps (must resolve before implementation)

| ID | Dimension | Component | Description | Fix |
|----|-----------|-----------|-------------|-----|
| **EH-01** | Error Handling | `llm_provider` | No retry policy for rate limits or transient LLM failures. Every LLM call is one-shot. | Add exponential backoff with jitter for `RateLimitError`, `Timeout`, `APIConnectionError` inside `acomplete()`. Configurable via `LlmConfig.retry_policy`. |
| **SEC-01** | Security | `snowflake_connector` (legacy) | SQL injection in existing `serverSnowflake.py` — executes user SQL directly. | Rewrite addresses this. Ensure legacy code is not importable from new entry point. |
| **T-01** | Testing | All components | Zero test infrastructure. No conftest.py, no fixtures, no mocks. 24 LLDs assume test infra that doesn't exist. | Create `tests/conftest.py` with shared fixtures (`mock_llm_provider`, `mock_tool_registry`, `sample_llm_config`) before Phase 1 implementation. |
| **D8-01** | Architecture | 5 components | 5 components blocked by unresolved ADRs (OQ-001 through OQ-007). Includes the primary agent (`decypher_agent`). | Resolve ADRs: OQ-001 first, then OQ-002, then OQ-004/006/007. Lean toward simplest option. |
| **D8-06** | Architecture | synapticore-ui (C2) | React+Vite UI has zero scaffolding. No package.json, no source files. 3 LLDs reference paths that don't exist. | Scaffold: `npm create vite@latest ui -- --template react-ts`. Add `@ag-ui/client`, `@ag-ui/core`. |
| **D8-04** | Architecture | app_server | No liveness/readiness probe distinction. Single `/health` endpoint serves all purposes. | For alpha: document `/health` as both. Post-alpha: add `/health/live`, `/health/ready`, `/health/deps`. |

---

## High Gaps (address during implementation)

### Error Handling
| ID | Component | Description |
|----|-----------|-------------|
| EH-02 | decypher_agent | Unbounded conversation memory → context overflow crashes agent |
| EH-03 | agui_server | `emit()` on full queue blocks indefinitely if watchdog fails |
| EH-04 | host_orchestrator | A2A client errors surface as raw tracebacks to ADK LLM |
| EH-08 | agents | No timeout on individual agent runs |

### Security
| ID | Component | Description |
|----|-----------|-------------|
| SEC-02 | snowflake_connector | Multi-statement SQL not restricted (`DROP TABLE` via injection) |
| SEC-03 | app_server | CORS defaults to `["*"]` (allow all origins) |
| SEC-04 | all servers | No rate limiting on any endpoint — cost amplification risk |
| SEC-05 | agui_server | No auth on `agent_id` — any client can invoke any agent |

### Performance
| ID | Component | Description |
|----|-----------|-------------|
| PERF-01 | decypher_agent | In-memory conversation store grows without bound (memory leak) |
| PERF-02 | agui_server | SSE connections not bounded (unbounded background tasks) |
| PERF-03 | host_orchestrator | Agent card resolution is sequential at startup |

### Observability
| ID | Component | Description |
|----|-----------|-------------|
| O-01 | All | No structured logging implementation — HLD promises not translated to LLDs |
| O-02 | llm_provider | LLM call tracing specified but not wired (no callback registration) |
| O-05 | decypher_agent | No agent decision tracing (why did it pick tool X?) |

### Testing
| ID | Component | Description |
|----|-----------|-------------|
| T-02 | llm_provider, agents | LLM mockability designed but no shared mock infrastructure |
| T-03 | web_search, snowflake | External service mocking unspecified |
| T-04 | agui_server, agui_client | AG-UI SSE streaming test strategy missing |

### Data Integrity
| ID | Component | Description |
|----|-----------|-------------|
| D-01 | a2a_task_manager | In-memory task state lost on crash/restart |
| D-02 | agui_server | thread_id collision possible for concurrent users |
| D-04 | a2a_task_manager | SSE subscriber queues unbounded — memory leak |

### Documentation
| ID | Component | Description |
|----|-----------|-------------|
| D7-01 | protocols | No OpenAPI spec for HTTP endpoints |
| D7-02 | Project | No developer guide for building new agents/tools |
| D7-04 | Project | No migration guide from legacy to new architecture |

### Architecture
| ID | Component | Description |
|----|-----------|-------------|
| D8-03 | app_server | Single-process uvicorn concurrency under mixed-protocol load unvalidated |
| D8-07 | pyproject.toml | Not updated for new package structure (legacy entry point, ADR-gated deps committed as hard reqs) |
| D8-08 | Project | No `synapticore/` package directory exists — all LLDs reference it |

---

## Medium Gaps (address post-alpha or during polish)

| ID | Dimension | Component | Description |
|----|-----------|-----------|-------------|
| EH-05 | Error | a2a_server | All errors return HTTP 400, even internal errors (should be 500) |
| EH-06 | Error | agui_server | RunErrorEvent after CancelledError may silently fail |
| EH-07 | Error | snowflake_connector | Large result sets load entirely into memory |
| SEC-06 | Security | llm_provider | Tool results passed back to LLM unsanitized (prompt injection) |
| SEC-07 | Security | app_server | Error middleware may leak internal details in debug mode |
| SEC-08 | Security | host_orchestrator | Remote agent responses unsanitized (prompt injection) |
| SEC-09 | Security | snowflake_connector | Password in env var, no encryption at rest |
| SEC-10 | Security | agui_server | No input size limit on request body |
| PERF-04 | Perf | snowflake_connector | Pool size of 3 may be small under load |
| PERF-05 | Perf | llm_provider | No streaming support — UI feels sluggish |
| PERF-06 | Perf | app_server | Eager startup for all tools/agents |
| PERF-07 | Perf | agui_server | Disconnect watchdog polls every 1s |
| O-03 | Observability | a2a_task_manager | Task lifecycle not logged |
| O-04 | Observability | agui_server | AG-UI event streams not traceable (no run_id in logs) |
| O-07 | Observability | host_orchestrator | Remote delegation is opaque (no delegation chain logging) |
| T-05 | Testing | All | ~600-900 specified tests — need triage to P0/P1 |
| T-06 | Testing | All | 70% coverage unrealistic without coverage tooling |
| D-03 | Data | tool_registry | Startup race conditions if parallel init |
| D-07 | Data | chat_view | Conversation lost on browser refresh |
| D7-03 | Docs | open-questions.md | OQs lack deadlines and ownership |
| D7-05 | Docs | .env.template | Missing new env vars, contains legacy toggle |
| D8-05 | Arch | app_server | Graceful shutdown underspecified |
| D9-01 | A11y | chat_view | No keyboard navigation |
| D9-02 | A11y | chat_view | No screen reader support for streaming |

---

## Low Gaps (defer to post-v1)

| ID | Dimension | Component | Description |
|----|-----------|-----------|-------------|
| EH-09 | Error | app_server | Failed tools/agents not surfaced in health check |
| EH-10 | Error | llm_provider | ProviderError doesn't distinguish retriable vs non-retriable |
| PERF-08 | Perf | host_orchestrator | list_remote_agents tool is redundant with prompt injection |
| PERF-09 | Perf | app_server | No HTTP/2 support (SSE connection limit in browsers) |
| PERF-10 | Perf | synapticore-ui | No bundle size analysis |
| O-06 | Observability | All | Third-party log noise not enforced |
| T-07 | Testing | a2a_task_manager | Concurrency tests are hard to write correctly |
| D-05 | Data | snowflake_connector | Connection pool leak detection not specified |
| D-06 | Data | a2a_task_manager | Task history grows without bound |
| D8-10 | Arch | types | No `__all__` exports |
| D9-03 | A11y | app_shell | No color contrast/theme support |
| D9-04 | A11y | chat_view | No focus management during async updates |

---

## Top 5 Actions Before Implementation

1. **Create test infrastructure** (T-01) — `tests/conftest.py` with shared fixtures. Blocks all testing.
2. ~~**Resolve blocking ADRs** (D8-01)~~ — **RESOLVED.** All 5 ADRs resolved via OQ-001, OQ-002, OQ-004, OQ-006, OQ-007.
3. **Scaffold package + UI** (D8-08, D8-06) — Create `synapticore/` and `ui/` directories. Blocks all implementation.
4. **Update pyproject.toml** (D8-07) — New structure, new deps, ADR-gated deps as optionals.
5. **Add LLM retry policy** (EH-01) — Without retries, every transient failure kills user requests.
6. **Bound memory and concurrency** (PERF-01, PERF-02, EH-08) — Sliding window, SSE semaphore, agent run limits. Prevents resource exhaustion under load.

---

## Gaps Addressed by OQ Resolutions

> Cross-reference: OQ resolutions from `recon-oqs.md` that directly close or mitigate gaps above.

| Gap ID | Gap | Resolved By | Resolution |
|--------|-----|-------------|------------|
| D8-01 | 5 components blocked by unresolved ADRs | OQ-001, OQ-002, OQ-004, OQ-006, OQ-007 | OQ-001: plain Python loop. OQ-002: SmolAgents optional. OQ-004: Pandas required. OQ-006/007: evaluate during implementation. 5/5 ADRs resolved. |
| PERF-01 | In-memory conversation grows without bound | OQ-027 | Sliding window, max 200 messages per thread. |
| PERF-02 | SSE connections not bounded | OQ-024 | Semaphore limit, max 50 concurrent SSE. |
| SEC-05 | No auth on agent_id | OQ-018 | Server-generated UUID4 only for thread_id. (agent_id auth still open) |
| D-02 | thread_id collision | OQ-018 | Server-generated UUID4, client IDs ignored. |
| D-07 | Conversation lost on refresh | OQ-019 | Server sessions with GET /agui/threads/{thread_id}/messages recovery. |
| EH-08 | No timeout on agent runs | OQ-025, OQ-028 | 30s tool timeout + max 5 concurrent agent runs with queue. |
| SEC-10 | No input size limit | OQ-023 | 5MB body limit + 100 message limit. |
