# Recon Survey — SynaptiCore

> Generated: 2026-03-25 by `/monke-recon:orchestra` Phase 1

---

## Overview

| Metric | Value |
|--------|-------|
| **Project** | SynaptiCore v0.1.0 (Alpha) |
| **Primary Language** | Python 3.12+ |
| **Planned Frontend** | TypeScript (React + Vite + AG-UI) |
| **Total Python Files** | ~39 |
| **Total LOC (Python)** | ~2,800 |
| **Containers** | 6 (Apps, Core, Servers, Tools, Data, DevX) |
| **Components** | 14 (see breakdown below) |
| **Test Coverage** | ~0% formal (notebook demos only) |
| **Quality Rating** | Experimental — functional prototypes, not production-hardened |

---

## Containers & Components

### Container 1: Apps (Application Layer)

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **DeCypher** | 1 | ~245 | Needs-work | Critical bug: `list.extend()` returns None (line 181); assertions instead of exceptions; no tests |
| **RoutesHQ/classifier** | 1 | ~273 | Production-ready | Clean LangChain chains, good error handling with defaults |
| **RoutesHQ/classifier_langchain** | 1 | ~415 | Experimental | Debug prints in production, commented-out code, overkill graph for the task |
| **RoutesHQ/schema** | 1 | ~43 | Production-ready | Clean Pydantic models, type-safe enums |
| **RoutesHQ/utils** | 1 | ~66 | Production-ready | Simple, focused context formatting |

**Dependencies:** LangChain, LangGraph, LangChain-AWS (Bedrock), SmolAgents, Pydantic
**Internal deps:** Tools/langBots

### Container 2: Core (Protocol Implementations)

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **a2aPro/client** | 1 | ~84 | Production-ready | SSE streaming, proper async, custom exceptions |
| **a2aPro/server** | 1 | ~117 | Production-ready | JSON-RPC routing, Starlette-based; minor bug line 87 (wrong var in error msg) |
| **a2aPro/orchestrator** | 1 | ~244 | Production-ready | Google ADK integration, task delegation; needs docstrings |
| **a2aPro/types** | 1 | ~366 | Production-ready | Comprehensive Pydantic types, 50+ models, JSON-RPC 2.0 compliant |
| **a2aPro/task_manager** | 1 | ~276 | Needs-work | Abstract stubs that are dead code (lines 112-120); task model field mismatch |
| **a2aPro/utils** | 3 | ~141 | Production-ready | Card resolver, remote connections, server utils |
| **mcPro/anyMCP** | 1 | ~227 | Experimental | F-string bugs (lines 41-44); `ast.literal_eval()` on untrusted input; no error handling in query processing |

**Dependencies:** httpx, httpx-sse, starlette, sse-starlette, uvicorn, google-adk, google-genai, mcp, litellm, Pydantic
**Internal deps:** None (leaf container)

### Container 3: Servers (MCP Entry Points)

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **mcpServer** | 1 | ~15 | Experimental | Stub — just starts sub-servers |
| **serverDeCypher** | 1 | ~50 | Needs-work | Instantiates DeCypher on every call; no error handling |
| **serverSnowflake** | 1 | ~50 | Needs-work | `.to_string` missing parens; SQL injection risk; connection leak on error |
| **mcpClient** | 1 | ~30 | Needs-work | No validation, hardcoded env check |

**Dependencies:** mcp (FastMCP), pandas
**Internal deps:** Core/genFuncs, Core/mcPro, Apps/DeCypher, Tools/liteLM

### Container 4: Tools (LLM Wrappers)

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **langBots** | 1 | ~100 | Needs-work | Naming inconsistency (camelCase class); decorator issue on calculator |
| **liteLM** | 1 | ~35 | Needs-work | No input validation; returns None for invalid values |
| **smolBots** | 1 | ~45 | Production-ready | Misspelled method `calculater`; otherwise functional |
| **settings** | 1 | ~5 | Experimental | Class with no methods/attributes |

**Dependencies:** langchain, langchain-community, smolagents, litellm, dotenv
**Internal deps:** smolBots used by langBots

### Container 5: Data (Placeholder)

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **(empty)** | 1 | 0 | Stub | `__init__.py` only — no data models exist |

### Container 6: DevX (Experiments)

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **test_langraph** | 1 | ~211 | Experimental | Not a test suite — global execution, hardcoded queries |
| **test_smol** | 1 | ~44 | Experimental | Not a test suite — single hardcoded task |
| **test_jupy** | 1 | 1 cell | Stub | Abandoned notebook |

### Supporting: Demo/

| Component | Files | LOC | Maturity |
|-----------|-------|-----|----------|
| **demDeCypher** | 1 | ~50 | Production-ready (demo) |
| **helpers** | 1 | ~15 | Production-ready (duplicates Core/genFuncs) |

### Supporting: Core Utilities

| Component | Files | LOC | Maturity | Key Issues |
|-----------|-------|-----|----------|------------|
| **genFuncs** | 1 | ~27 | Needs-work | No error handling on Snowflake connection |
| **langFuncs** | 1 | ~7 | Stub | No type hints, assumes state structure |

---

## Dependency Map

```
Apps/DeCypher ──→ Tools/langBots ──→ Tools/smolBots
     │                                     │
     └──→ LangGraph, SmolAgents            └──→ smolagents

Apps/RoutesHQ ──→ LangChain-AWS (Bedrock), LangGraph, Pydantic

Core/a2aPro ──→ httpx, starlette, google-adk, Pydantic
Core/mcPro  ──→ mcp, litellm

Servers ──→ Core/genFuncs, Core/mcPro, Apps/DeCypher, Tools/liteLM

Tools/langBots ──→ LangChain, LangChain-Community, Tools/smolBots
Tools/liteLM   ──→ LangChain-Community, smolagents
Tools/smolBots ──→ smolagents
```

---

## Cross-Cutting Observations

### Error Handling
- **a2aPro/client, server:** Good — custom exceptions, JSON-RPC error codes
- **RoutesHQ/classifier:** Good — try/except with sensible defaults
- **Everything else:** Poor to none — bare calls, assertions, no custom exceptions

### Naming Conventions
- **Inconsistent casing:** `langBots` (camelCase class), `smolBots`, `anyMCP`, `anyA2A`
- **Misspellings:** `calculater`, `ANTRHOPIC_ACCESS_KEY_ID`
- **PEP 8 compliance:** Partial — classes should be PascalCase

### Documentation
- **RoutesHQ:** Excellent docstrings throughout
- **DeCypher:** Good docstrings
- **a2aPro:** No docstrings on any class/method
- **mcPro, Servers, Tools:** Minimal to none

### Test Infrastructure
- **pytest declared** in `pyproject.toml [dev]` but never used
- **Zero conftest.py**, zero fixtures, zero mocks
- **Jupyter notebooks** serve as integration demos (RoutesHQ only)
- **DevX/** contains experimental sketches, not tests
- **No CI/CD** pipeline exists

### Security
- **SQL injection:** `serverSnowflake.py` executes user input directly
- **Unsafe eval:** `mcPro/anyMCP.py` uses `ast.literal_eval()` on tool args
- **No secret validation:** Environment variables used without checking they exist

---

## Critical Bugs

| # | Location | Severity | Description |
|---|----------|----------|-------------|
| 1 | `Apps/DeCypher.py:181` | Critical | `list.extend()` returns None — custom tools silently fail |
| 2 | `Core/mcPro/anyMCP.py:41-44` | High | F-string syntax errors in error messages |
| 3 | `Servers/serverSnowflake.py:48` | High | `.to_string` missing parentheses — returns method ref, not string |
| 4 | `Core/a2aPro/task_manager.py:112-120` | High | Abstract methods with dead `pass` bodies |
| 5 | `Core/a2aPro/server.py:87` | Medium | Wrong variable name in TypeError message |

---

## Rewrite Intent

**The existing modules are legacy prototypes and will be rewritten, not incrementally improved.** The current code serves as reference for behavior and intent, but the HLD and LLDs should target a clean architecture. Key implications:

- The survey documents what exists for **behavioral reference only**
- The reconstruction (Phase 2) should design the **target architecture**, not codify the current one
- Bugs listed above are **not worth fixing** — they'll be eliminated by the rewrite
- Patterns worth preserving: a2aPro's type system (Pydantic models), RoutesHQ's intent classification approach, LangGraph state machine patterns
- Patterns to discard: camelCase naming, print-based logging, assertion-based validation, manual path hacking, scattered `genFuncs`/`langFuncs` utilities
- **New addition:** AG-UI protocol layer + React+Vite unified frontend
- **New addition:** LM Studio support via LiteLLM's OpenAI-compatible endpoints (local model inference)

---

## Top 3 Concerns

1. **Zero formal test coverage.** No pytest infrastructure despite being declared. All "testing" is manual notebook runs or experimental sketches. Any refactoring or bug fix risks breaking untested code.

2. **Security gaps in user-facing components.** SQL injection in Snowflake server, unsafe `literal_eval` in MCP client, no input validation at system boundaries.

3. **Critical bugs in core paths.** DeCypher's tool binding is silently broken with custom tools, Snowflake server returns a method reference instead of data, and MCP error messages have f-string bugs.
