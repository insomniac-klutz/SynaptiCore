# Project Specs — SynaptiCore

> Project-specific bindings for the design, implementation, and test specs. This file maps abstract rules to concrete tools.

**This is a living document.** Update it in the same commit whenever code, config, or infrastructure changes make any section inaccurate.

### Continuous Improvement Directive

Claude MUST keep this document current:

- **After adding a dependency:** Update the dependency table and relevant commands.
- **After changing directory structure:** Update the directory tree.
- **After modifying CI/CD:** Update the pipeline section.
- **After adding/changing environment variables:** Update the variables table.
- **After resolving a test specs binding (e.g., choosing factory-boy vs manual):** Replace "TBD" with the decision.
- **After any phase completion:** Review all sections for staleness.
- **After an ADR that affects tooling:** Propagate the decision into the relevant binding table.

---

## 1. Specs References

| Spec | Document | Governs |
|------|----------|---------|
| Design | [monke-docs/design-specs.md](design-specs.md) | HLD/LLD creation, pause gates, ADR, teams |
| Implementation | [monke-docs/implementation-specs.md](implementation-specs.md) | Layer pipeline, IL gates, code standards |
| Test | [monke-docs/test-specs.md](test-specs.md) | Test tiers, fixtures, coverage, mock boundaries |
| **This document** | monke-docs/project-specs.md | Tooling, config, CI/CD for SynaptiCore |

---

## 2. Stack Bindings

Maps implementation specs' abstract references to SynaptiCore's locked stack:

| Abstract Concept | SynaptiCore Binding |
|-----------------|-------------------|
| Primary language | Python 3.12+ |
| Frontend language | TypeScript (React + Vite) |
| Package manager (Python) | UV (`uv.lock`) |
| Package manager (Frontend) | npm / pnpm (TBD on frontend init) |
| Build system | Hatchling (`pyproject.toml`) |
| LLM orchestration | LangChain 0.3.21+ / LangGraph 0.3.18+ |
| Lightweight agents | SmolAgents 1.9.2 |
| Unified LLM routing | LiteLLM 1.66.1 |
| Agent-to-Agent protocol | a2aPro (custom, `SynaptiCore/Core/a2aPro/`) |
| Agent-to-Tools protocol | MCP via `mcp[cli]` 1.4.1+ / `fastapi-mcp` 0.2.0 |
| Agent-to-UI protocol | AG-UI (`ag-ui-protocol` Python / `@ag-ui/client` JS) |
| ML framework | PyTorch 2.2.0 / Transformers 4.48.3 |
| Data processing | NumPy 1.26.4 / Pandas 2.2.3 |
| Visualization | Matplotlib 3.9.4 |
| Cloud LLM providers | AWS Bedrock (Boto3), Google GenAI/ADK, Gemini |
| Data warehouse | Snowflake (`snowflake-connector-python` 3.13.2) |
| PDF processing | PyMuPDF 1.25.3 |
| Env management | python-dotenv 1.0.1 |

---

## 3. Dependency Configuration

- **Manifest:** `pyproject.toml` (Hatchling build system)
- **Lock file:** `uv.lock` (committed, 3309 lines)
- **Freeze snapshot:** `uv_freeze.txt`
- **Server-specific:** `SynaptiCore/Servers/requirements.txt`
- **Frontend (planned):** `ui/package.json` (React + Vite + AG-UI SDKs)

### Commands

| Action | Command |
|--------|---------|
| Install all deps | `uv sync` |
| Install dev deps | `uv sync --extra dev` |
| Add a dependency | `uv add <package>` |
| Add dev dependency | `uv add --extra dev <package>` |
| Remove dependency | `uv remove <package>` |
| Run project entry | `uv run synapticore` |
| Run arbitrary script | `uv run python <script.py>` |
| Freeze deps | `uv pip freeze > uv_freeze.txt` |
| Build package | `uv build` |

---

## 4. Environment Configuration

### Files

| File | Purpose | Committed? |
|------|---------|-----------|
| `.env.template` | Variable reference with placeholders | Yes |
| `.env` | Actual secrets (Tavily, AWS, Gemini, Snowflake) | No (gitignored) |
| `.python-version` | Python 3.12 pinning for UV | Yes |

### Required Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `TAVILY_API_KEY` | Tavily search API | `tvly-xxxx` |
| `ANTHROPIC_MODEL_ID` | Bedrock Claude model deployment ID | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `AWS_REGION_NAME` | AWS region for Bedrock | `us-east-1` |
| `ANTRHOPIC_ACCESS_KEY_ID` | AWS access key for Bedrock | `AKIAxxxx` |
| `ANTRHOPIC_SECRET_ACCESS_KEY` | AWS secret key for Bedrock | `wJalrXxxxx` |
| `GEMINI_API_KEY` | Google Gemini API key | `AIzaSyxxxx` |
| `SNOWFLAKE_DB_USER` | Snowflake username | `my_user` |
| `SNOWFLAKE_DB_PASSWORD` | Snowflake password | `****` |
| `SNOWFLAKE_DB_ACCOUNT` | Snowflake account ID | `xy12345.us-east-1` |
| `SNOWFLAKE_DB_HOST` | Snowflake host | `xy12345.snowflakecomputing.com` |
| `SNOWFLAKE_DB_DBNAME` | Snowflake database name | `MY_DB` |
| `SNOWFLAKE_DB_PORT` | Snowflake port | `443` |
| `SNOWFLAKE_DB_ROLE` | Snowflake role | `SYSADMIN` |
| `SNOWFLAKE_DB_WAREHOUSE` | Snowflake warehouse | `COMPUTE_WH` |
| `USE_MODEL_INFERENCE` | LLM provider selector | `GEMINI` or empty (defaults to Bedrock) |

---

## 5. Directory Structure

### Implementation

```
SynaptiCore/
├── SynaptiCore/                    # Main Python package
│   ├── __init__.py
│   ├── Apps/                       # Ready-to-use applications
│   │   ├── DeCypher.py             # Conversational AI + tool integration
│   │   └── RoutesHQ/               # Intent classification app
│   │       ├── intent_classifier/
│   │       │   ├── classifier.py
│   │       │   ├── classifier_langchain.py
│   │       │   ├── schema.py
│   │       │   └── utils.py
│   │       └── notebooks/
│   │           ├── intent_classifier_demo.ipynb
│   │           └── intent_classifier_graph_demo.ipynb
│   ├── Core/                       # Protocol implementations
│   │   ├── a2aPro/                 # Agent-to-Agent (A2A)
│   │   │   ├── anyA2A.py
│   │   │   ├── core/               # orchestrator, server, client
│   │   │   └── utils/              # types, card_resolver, task_manager
│   │   └── mcPro/                  # Model Context Protocol (MCP)
│   │       └── anyMCP.py
│   ├── Servers/                    # MCP server entry points
│   │   ├── mcpServer.py            # Main MCP server
│   │   ├── serverDeCypher.py       # DeCypher MCP server
│   │   ├── serverSnowflake.py      # Snowflake MCP server
│   │   └── mcpClient.py
│   ├── Tools/                      # LLM utility wrappers
│   │   ├── langBots.py             # LangChain bots
│   │   ├── liteLM.py               # LiteLLM utilities
│   │   ├── smolBots.py             # SmolAgents utilities
│   │   ├── settings.py
│   │   ├── genFuncs.py
│   │   └── langFuncs.py
│   ├── Data/                       # Data models (placeholder)
│   └── DevX/                       # Developer experiments
│       ├── test_langraph.py
│       ├── test_smol.py
│       └── test_jupy.ipynb
├── Demo/                           # Demo scripts
│   ├── demDeCypher.py
│   └── helpers.py
├── ui/                             # (Planned) React + Vite + AG-UI frontend
├── pyproject.toml
├── uv.lock
├── .env.template
└── .python-version
```

### Tests

```
SynaptiCore/
├── SynaptiCore/DevX/               # Current test/experiment location
│   ├── test_langraph.py            # LangGraph integration tests
│   ├── test_smol.py                # SmolAgents tests
│   └── test_jupy.ipynb             # Jupyter experiment notebook
├── tests/                          # (Planned) Formal test directory
│   ├── unit/
│   ├── integration/
│   └── system/
```

---

## 6. Linting & Formatting Configuration

| Tool | Config Location | Settings |
|------|----------------|----------|
| Black | `pyproject.toml [tool.black]` | `line-length = 88` |
| isort | `pyproject.toml [tool.isort]` | `profile = "black"` |
| mypy | `pyproject.toml [tool.mypy]` | `python_version = "3.12"` |

---

## 7. CI/CD Pipeline (GitHub Actions)

Not yet configured. To be set up during implementation phase. Planned:

- Lint + type check (black, isort, mypy)
- Test (pytest)
- Build validation (hatchling)
- Frontend build (Vite)

---

## 8. Implementation Specs Bindings

Maps abstract IL gate verifications to SynaptiCore commands:

| Gate | Abstract Verification | SynaptiCore Command |
|------|----------------------|-------------------|
| IL-0 (Types compile) | Type check passes | `uv run mypy SynaptiCore/` |
| IL-1 (Stubs pass) | Stubs importable, no runtime errors | `uv run python -c "import SynaptiCore"` |
| IL-2 (Unit tests) | All unit tests green | `uv run pytest tests/unit/ -v` |
| IL-3 (Integration tests) | Integration tests green | `uv run pytest tests/integration/ -v` |
| IL-4 (Lint clean) | No lint/format violations | `uv run black --check . && uv run isort --check . && uv run mypy SynaptiCore/` |
| IL-5 (Build) | Package builds successfully | `uv build` |

---

## 9. Test Specs Bindings

| Abstract Concept | SynaptiCore Binding |
|-----------------|-------------------|
| Test framework | pytest 7.0.0+ |
| Test runner command | `uv run pytest` |
| Unit test dir | `tests/unit/` |
| Integration test dir | `tests/integration/` |
| System test dir | `tests/system/` |
| Object factory library | TBD (factory-boy or manual builders) |
| HTTP mock library | TBD (responses, httpx-mock, or respx) |
| Async test support | pytest-asyncio |
| DB fixture strategy | TBD (Snowflake test account or mock) |
| Coverage tool | pytest-cov |
| Coverage threshold | 70% (initial target, raise after stabilization) |
| Shared fixture file | `tests/conftest.py` |
| Eval metric library | TBD (ragas, deepeval, or custom) |
| Eval test dataset dir | `tests/eval/datasets/` |

---

## 10. Design Specs Bindings

### 10.1 Locked Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language (backend) | Python 3.12+ | Primary — all agent logic, servers, tools |
| Language (frontend) | TypeScript | React + Vite UI |
| Runtime | CPython via UV | `.python-version` pins 3.12 |
| Build | Hatchling | `pyproject.toml` |
| Package manager (Python) | UV | `uv.lock` committed |
| Package manager (JS) | npm / pnpm | TBD on frontend init |
| LLM orchestration | LangChain + LangGraph | Core agent workflows |
| Agent framework (light) | SmolAgents | Simple agent tasks |
| LLM routing | LiteLLM | Multi-provider abstraction |
| A2A protocol | Custom (a2aPro) | Agent-to-Agent communication |
| MCP protocol | mcp[cli] + fastapi-mcp | Agent-to-Tools/Data |
| AG-UI protocol | ag-ui-protocol (Py) + @ag-ui/client (JS) | Agent-to-UI streaming |
| ML | PyTorch + Transformers | Model inference, embeddings |
| Data | Snowflake | Warehouse, queried via connector |
| Frontend | React + Vite | Unified agent UI (planned) |
| Formatter | Black (88 cols) | Via pyproject.toml |
| Linter | isort + mypy | Via pyproject.toml |
| Test | pytest | With pytest-cov |

### 10.2 Supported Languages

| Language | Best For | LLM Integration | Test Framework |
|----------|---------|-----------------|----------------|
| Python 3.12+ | Agent logic, servers, ML, data pipelines | LangChain, LangGraph, SmolAgents, LiteLLM | pytest |
| TypeScript | Frontend UI, AG-UI client, browser-side tools | @ag-ui/client, @ag-ui/core | Vitest (planned) |

### 10.3 Stack Enforcement Rules

- **Python is the default** for all backend, agent, and server code. No exceptions without an ADR.
- **TypeScript is allowed only** in the `ui/` directory for the React+Vite frontend and AG-UI client code.
- **New LLM providers** must go through LiteLLM — no direct SDK calls outside `Tools/`.
- **New protocols** must implement through `Core/` — no ad-hoc protocol code in `Apps/` or `Servers/`.
- **AG-UI** is the only sanctioned agent-to-frontend protocol. No custom WebSocket/REST streaming.
- **Dependency additions** require updating this file and `pyproject.toml` in the same commit.

### 10.4 Modifications

- Design specs Section 1.2 (versioned artifacts): Applies — SynaptiCore uses multiple LLM providers with pinned model versions.
- AG-UI adds a new protocol layer not covered in the base design specs. The HLD must include an AG-UI boundary in the L2 container diagram showing event flow between Python agent backends and the React frontend.

### 10.5 Pause Gate Artifacts

Maps design specs pause gates to SynaptiCore-specific artifacts:

| Gate | Artifact Location |
|------|------------------|
| PG-1 (L1 Context) | `monke-docs/hld.md` S1 |
| PG-2 (L2 Containers) | `monke-docs/hld.md` S2 |
| PG-3 (L3 Components) | `monke-docs/hld.md` S3 |
| PG-4 (Boundary Matrix) | `monke-docs/hld.md` S7 |
| PG-5 (LATS decision) | `monke-docs/decisions/NNN-slug.md` (ADR for selected option) |
| PG-6 (Language choice) | `monke-docs/decisions/NNN-slug.md` (ADR for exception) |
| PG-7 (Pattern selection) | `monke-docs/decisions/NNN-slug.md` (ADR for pattern) |
| PG-8 (ADaPT decomposition) | `monke-docs/lld/<component>-draft.md` |
| PG-9 (LLD converged) | `monke-docs/lld/<component>-draft.md` (final) |
| PG-10 (Test plan) | Unit + integration test tables in LLD |
| PG-11 (Phase checkpoint) | `monke-docs/checkpoints/phase-N-checkpoint.md` |
| PG-12 (Stack violation) | `monke-docs/decisions/NNN-slug.md` (ADR with status "exception") |
| PG-13 (Test failure escalation) | `monke-docs/open-questions.md` |
| PG-14 (HLD revision from LLD) | `monke-docs/hld.md` (updated section) |
| ADRs | `monke-docs/decisions/NNN-slug.md` |
| Open questions | `monke-docs/open-questions.md` |

### 10.6 AI & Data Science Infrastructure

| Concept | SynaptiCore Binding |
|---------|-------------------|
| Model registry | None (provider-hosted models — Bedrock, Gemini, HuggingFace) |
| Feature store | None (not applicable yet) |
| Experiment tracker | TBD (MLflow or Weights & Biases when needed) |
| Eval metric thresholds | TBD (intent classification accuracy, agent task completion rate) |
