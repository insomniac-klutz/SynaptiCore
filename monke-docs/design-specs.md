# Design Specs

> Core principle: **never generate a complete detailed plan in one pass**.
> Design is hierarchical, iterative, decision-traced, search-backed, team-verified, and test-gated.

---

## 1. Design Paradigm

### Architecture Frameworks

- **C4 Model** for traditional request-response systems (APIs, pipelines, CRUD).
- **CoALA dimensions** (Memory, Action Space, Decision Procedure) for agentic / autonomous-loop systems.
- **Anthropic Composable Patterns** as the complexity ladder for LLM-involving components.

C4 defines outer boundaries. CoALA defines agent internals. A container is tagged `traditional` or `agentic` at L2 — this determines which framework applies at L3/L4.

**Agentic Candidacy Heuristic:** When tagging a container at L2, apply this test — if the container must (a) select among tools or strategies based on runtime context, (b) handle non-deterministic inputs where the correct action isn't known at design time, or (c) make multi-step decisions with feedback loops — it is an agentic candidate. LATS (S1.4) should explore both `traditional` and `agentic` at PG-5. Default: if the container consumes any versioned-artifact or data-dependent tool, it is agentic until proven otherwise — tool selection, error recovery, and quality monitoring are agent-loop problems.

For hybrid containers (traditional service with embedded agent): C4 for the service boundary, CoALA for the agent component inside.

### Decision Protocols (apply to ALL system types)

- **LATS** (expand → evaluate → select → backtrack) at every design branch point.
- **ADaPT** (decompose → attempt → assess → adapt) during every LLD creation.
- **ADRs** for decision tracking.
- **Agent Teams** for parallel adversarial design verification (S3).
- **Pause Gates** (S9.4) — mandatory user confirmation before irreversible decisions.

### Test Gates (mandatory — see S11)

- **Unit tests** per LLD component (pass gate before next LLD).
- **Integration tests** per LLD boundary contract (pass gate before phase checkpoint).
- **System tests** per HLD data flow (pass gate before phase completion).

---

### 1.1 C4 Zoom Levels

| Level | Answers | Document |
|-------|---------|----------|
| L1 Context | What is this system? Who uses it? External systems? | monke-docs/hld.md S1 |
| L2 Container | Deployable units and communication? | monke-docs/hld.md S2 |
| L3 Component | Modules inside each container? Boundary contracts? | monke-docs/hld.md S3 |
| L4 Code | Implementation of one component. | monke-docs/lld/component.md |

**HLD = L1+L2+L3.** LLD = L4. Each level is a separate document created at a separate time. Collapsing levels produces plans that read well but cannot be built from.

### 1.2 CoALA Dimensions (Agentic Components)

Every agentic component's HLD section and LLD MUST address all three dimensions:

**Memory** — Working (context window, token budget), Episodic (past experiences, retrieval strategy, retention), Semantic (domain knowledge, RAG pipeline, index strategy), Procedural (prompt templates, tool definitions, code).

**Action Space** — Internal (reasoning, retrieval, learning/memory-writes) vs External (tool calls, API requests, user interaction). Define action boundaries (what the agent CANNOT do).

All external capabilities are tools in the action space — a REST API, a database query, an ML model inference, an LLM call, a vector search, an NLP pipeline, an MCP server, a file system operation. Domain is irrelevant to classification. An LLM call is a versioned-artifact tool (output depends on model version). A feature store query is a data-dependent tool (output drifts with data). A REST API is a static-contract tool (schema fixed between deployments). A CV inference endpoint is a versioned-artifact tool. A prompt template is procedural memory until it's versioned, then it's a versioned-artifact tool. An embedding search is versioned-artifact (index version) AND data-dependent (corpus drift). Classify by contract behavior, not by what marketing calls it.

External tools are further classified by **contract behavior** (3 subtypes — no more):

| Subtype | Behavior | Examples | Requires in CoALA | Test Obligation |
|---------|----------|----------|-------------------|-----------------|
| **Static-contract** | Deterministic contract; schema and behavior fixed between deployments | REST APIs, databases, filesystems, message queues, MCP servers (fixed-schema tools) | (default — no extra fields) | Standard unit + integration |
| **Versioned-artifact** | Contract shape stable, output quality depends on artifact version | LLM model versions (`claude-sonnet-4-6`, `gpt-4o-2024-08-06`), embedding models, trained classifiers, NLP pipeline artifacts (NER, sentiment, intent), CV model weights, compiled rulesets, vector indices | Version pin, retraining/rebuild trigger, eval threshold | Unit + integration + **eval** |
| **Data-dependent** | Contract shape stable, output semantics drift with input distribution | Feature stores, search indices, user profile stores, document corpora, recommendation engines, analytics caches, any data source whose distribution drifts | Baseline profile, drift detection threshold | Unit + integration + **eval** |

Static-contract is the default. Only tag tools that need the extra obligations. The taxonomy distinguishes contract behavior, not ML domain or training methodology.

Tool access protocols (HTTP, gRPC, MCP, function call, CLI) are orthogonal to the taxonomy. An MCP server exposing a deterministic tool is static-contract. An MCP server exposing a model-backed tool is versioned-artifact. Protocol is an implementation detail decided at LLD; taxonomy is a design decision made at HLD.

**Decision Procedure** — The control loop: observe → retrieve → reason → plan → execute → learn → loop/terminate. Not every agent needs every step. Specify which steps, stopping condition, max iterations, human-in-the-loop points.

CoALA output format in HLD (for each agentic component at L3):

    ### Agent: <n>
    Pattern: <Anthropic pattern from S1.3>
    Loop: observe → retrieve → reason → execute → loop
    Memory: working(<budget>), episodic(<store>), semantic(<store>), procedural(<location>)
    Actions: internal(<strategies>), external(<tools: subtype>), boundaries(<cannot do>)
    Stops when: <condition>
    Human-in-loop: <where>
    # If any tool is versioned-artifact or data-dependent, additionally:
    Version pins: <artifact: version> (versioned-artifact tools)
    Eval thresholds: <metric: threshold> (versioned-artifact or data-dependent tools)
    Drift thresholds: <metric: threshold> (data-dependent tools)

### 1.3 Anthropic Composable Patterns (Complexity Ladder)

Select the **simplest pattern that satisfies requirements**. Escalation requires ADR with concrete evidence.

    Augmented LLM → Prompt Chaining → Routing → Parallelization
    → Orchestrator-Workers → Evaluator-Optimizer → Autonomous Agent

| If the task... | Start with... |
|----------------|--------------|
| Needs one LLM call ± tools | Augmented LLM |
| Has fixed sequential steps | Prompt Chaining |
| Has distinct input categories | Routing |
| Has independent parallel subtasks | Parallelization |
| Has unpredictable subtask structure | Orchestrator-Workers |
| Needs iterative refinement | Evaluator-Optimizer |
| Is fully open-ended | Autonomous Agent |

**De-escalation signal:** If a component has fewer than 3 dynamic decision points, it is over-engineered. De-escalate and record in ADR.

### 1.4 LATS — Design Space Exploration

At each design branch: (1) EXPAND 2-3 options, (2) EVALUATE against constraints, (3) SELECT with reason, (4) **PAUSE — present options to user, wait for confirmation** (S9.4), (5) preserve runner-up for BACKTRACK.

**Triggers:** L2 container decisions, L3 decomposition choices, ambiguous boundary contracts, Anthropic pattern selection, CoALA dimension decisions, user uncertainty.

    ## Design Branch: <n>
    Option A: <sentence>. Constraints: ... Downstream cost: ... Open questions: ...
    Option B: <sentence>. Constraints: ... Downstream cost: ... Open questions: ...
    Recommended: A because <reason>. Runner-up: B — revisit if <condition>.
    ⏸ WAITING FOR USER CONFIRMATION before proceeding.

Claude does NOT say "both are fine." Every option set has a recommended pick with a concrete reason. **Claude does NOT auto-commit. User must confirm or override.**

### 1.5 ADaPT — Recursive Decomposition (LLD Only)

(1) DECOMPOSE into sub-problems, (2) **PAUSE — present decomposition to user** (S9.4), (3) ATTEMPT each fully, (4) ASSESS against boundary contract, (5) ADAPT (decompose further / restructure / escalate to user), (6) INTEGRATE and verify end-to-end.

**Triggers:** Every LLD (mandatory), >3 responsibilities in one unit, >3 error paths, "handles X, Y, Z, and also W" signal. For agentic components: decompose each CoALA dimension separately, then integrate.

Surface the decomposition tree visibly. User sees reasoning, not just conclusion.

---

## 2. Tech Stack (Hard Rules)

Claude MUST NOT propose alternatives to locked choices without an explicit ADR approved by the user (S2.4).

### 2.1 Locked Choices

Declared in **project-specs S10.1 (Locked Stack)**. Each layer below MUST have a binding in project-specs:

| Layer | What to lock | Notes |
|-------|-------------|-------|
| Backend language | Primary language + version | Alternatives require ADR with measurable justification. Language selection is a PAUSE GATE (S9.4). |
| Frontend framework | UI framework + bundler (if applicable) | No alternatives without ADR. |
| Database | Primary persistent store (if applicable) | Auxiliaries permitted with ADR. |
| LLM interface | LLM client library (if applicable) | No direct provider SDKs without ADR. Async preferred. |
| Testing | Mandatory per S11 | No component ships without passing test gate. |

#### Language Selection

Alternatives to the project's default language must be justified with concrete, measurable requirements in an ADR. **Language selection is a PAUSE GATE (S9.4).**

"It would be faster" is not justification. "P99 must be <5ms at 10K RPS, default language measured 40ms" is.

### 2.2 Locked Stack Enforcement

Per project-specs S10.3 (Stack Enforcement Rules). For each locked technology declared in project-specs S10.1:

- No swapping to an alternative library/framework without ADR.
- No bypassing the locked choice via shims or wrappers.
- No direct provider SDKs when a locked LLM interface is declared. Async calls preferred.
- ORM/query layer, migration tooling, and CSS/component libraries remain flexible — decided via LATS + ADR.
- Auxiliary stores (cache, search, object storage) permitted with ADR.
- Direct provider SDKs for non-core features require ADR with scope.

### 2.3 Flexible Choices

Everything not in S2.1: API framework, ORM, state management, testing framework (not testing itself — mandatory), build tools, CSS, deployment, migration tooling, agent orchestration approach. Each decided via LATS + ADR.

### 2.4 Stack Violation Protocol

If a locked technology cannot satisfy a requirement: (1) Stop, (2) document blocker, (3) LATS alternatives, (4) **⏸ PAUSE — user decides**, (5) ADR with status "exception". No silent swaps. No bypass shims.

---

## 3. Agent Teams (Not Subagents)

This section uses **Claude Code Agent Teams** — the experimental multi-session feature where teammates are independent Claude Code instances with their own context windows, a shared task list, and peer-to-peer messaging. This is NOT the subagent/Task tool pattern where child agents run inside the lead's session and can only report back.

Requires: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings.json, Claude Code v2.1.32+, tmux recommended for split-pane visibility.

### 3.1 Teams vs Subagents — When to Use Which

| Dimension | Agent Teams (S3) | Subagents (Task tool) |
|-----------|-----------------|----------------------|
| Sessions | Each teammate = independent Claude Code instance with own context | Runs inside parent's session, shares context |
| Communication | Peer-to-peer messaging + shared task list | Report back to parent only |
| Context | Teammates load CLAUDE.md + project files, but NOT lead's conversation history | Inherits parent's context |
| Best for | Adversarial review, parallel exploration, cross-layer coordination | Focused subtasks, sequential work, same-file edits |
| Cost | High — each teammate is a full Claude session | Lower — runs within existing session |
| User interaction | You can Shift+Down to interact with any teammate directly | Only through parent |

**Use Agent Teams for:** HLD creation, LLD creation (design verification requires adversarial peer communication).
**Use Subagents for:** Implementation tasks, focused research, single-file operations, anything sequential.

### 3.2 Critical Mechanics

1. **Teammates start fresh.** They get their spawn prompt + CLAUDE.md + project files. They do NOT see the lead's prior conversation. Spawn prompts must be self-contained with all context needed.

2. **Shared task list.** Teammates claim tasks, mark completion, and blocked tasks auto-unblock when dependencies finish. Structure work as a task list, not as sequential instructions.

3. **Peer messaging.** Teammates message each other directly. The Architect can send a proposal directly to the Critic — no lead relay needed. Design the team to exploit this.

4. **Keep teams small.** 2 teammates per team with narrow scope consistently outperforms larger teams. The lead counts as a session too.

5. **Plan first, then team.** Before spawning a team, the lead should have the task broken down and the kickoff prompt ready. Letting teams explore without a plan wastes tokens.

6. **One team per session.** Clean up the current team before starting a new one. No nested teams — teammates cannot spawn their own teams (they CAN use subagents for focused subtasks).

7. **File ownership.** Each teammate should own specific output files. Concurrent writes to the same file cause conflicts. Define non-overlapping file assignments in spawn prompts.

### 3.3 HLD Team

**Kickoff prompt (lead says this to create the team):**

    Create an agent team to design the HLD for <project>.
    Two teammates:

    Teammate 1 — Architect:
    Your job: propose system structure for <project>. Follow LATS at every
    decision branch per design-specs.md S1.4. Write proposals to monke-docs/hld-draft.md.
    For each L1/L2/L3 level, produce a draft, then message the Critic directly
    and wait for their attack before finalizing. Comply with tech stack S2.
    Use the project's default language per project-specs S2. For agentic containers,
    select Anthropic pattern (simplest first) and specify CoALA dimensions per S1.2.
    You own: monke-docs/hld-draft.md

    Teammate 2 — Critic:
    Your job: attack every Architect proposal. Find failure modes, implicit
    assumptions, missing edge cases, scope creep, tech stack violations.
    Do NOT propose alternatives — only identify weaknesses. When Architect
    messages you a proposal, respond with: (a) what breaks first, (b) what
    implicit assumption exists, (c) what they're not telling you. Challenge
    pattern complexity and non-default language choices. Write your attacks
    to monke-docs/critic-notes.md. If you find no flaw, say so explicitly.
    You own: monke-docs/critic-notes.md

The lead acts as Coordinator: synthesizes Architect+Critic outputs, presents to user at each pause gate, resolves conflicts. The lead also performs the Contracts Auditor role (boundary matrix verification) after L3, or spawns a third teammate only if the system has >5 cross-boundary contracts.

**Flow:**
1. Lead creates team, spawns Architect + Critic
2. Architect writes L1 draft → messages Critic directly
3. Critic attacks via peer message → Architect revises or defends
4. Lead synthesizes → **⏸ presents to user (PG-1)**
5. User confirms → Lead tells Architect to proceed to L2
6. Repeat for L2 (**⏸ PG-2**), L3 (**⏸ PG-3**)
7. Lead audits boundary matrix (or spawns Auditor if complex) → **⏸ PG-4**
8. Lead writes final HLD, **shuts down team** (teammates don't auto-terminate)

### 3.4 LLD Team

**Kickoff prompt:**

    Create an agent team to design the LLD for <component>.
    Two teammates:

    Teammate 1 — Designer:
    Your job: design internals for <component> following HLD contracts in
    monke-docs/hld.md S3.<section>. Execute ADaPT decomposition per design-specs.md S1.5.
    For agentic components, decompose along CoALA dimensions. Write design
    to monke-docs/lld/<component>-draft.md. Message Reviewer when design is ready.
    Use locked LLM interface and database per project-specs S2.
    You own: monke-docs/lld/<component>-draft.md

    Teammate 2 — Reviewer:
    Your job: verify Designer's output against HLD boundary contracts exactly.
    Check: (a) upstream/downstream contract match, (b) error handling complete,
    (c) tech stack compliance, (d) for agentic: CoALA completeness + stopping
    condition + action boundaries. Write violation log to monke-docs/lld/<component>-review.md.
    Flag violations — do NOT fix them. Send back to Designer via message.
    Max 3 rounds, then escalate to lead.
    You own: monke-docs/lld/<component>-review.md

The lead performs the Test Engineer role: writes unit + integration test plan after Designer and Reviewer converge. For complex components (>5 public interfaces), spawn a third teammate as Test Engineer.

**Flow:**
1. Lead creates team, spawns Designer + Reviewer
2. Designer runs ADaPT → Lead presents decomposition → **⏸ PG-8**
3. User confirms → Designer writes design → messages Reviewer
4. Reviewer checks → messages violations back to Designer (peer-to-peer, up to 3 rounds)
5. Design converges → Lead reviews final design → **⏸ PG-9**
6. Lead writes test plan (unit + integration per S11) → **⏸ PG-10**
7. Lead assembles LLD, writes ADRs, updates HLD if needed, **shuts down team**

### 3.5 When to Skip Teams (Use Subagents or Solo Instead)

- Trivial HLD updates (version bump, single field)
- LLDs with <3 ADaPT sub-problems
- Localized bug fixes
- Implementation of already-designed components (use subagents for parallel file work)
- Sequential tasks with many dependencies between steps

If in doubt, use the team. **Test gates (S11) and pause gates (S9.4) are NEVER skippable, even when teams are skipped.**

### 3.6 Team Artifacts (Must Persist After Shutdown)

Before shutting down a team, lead copies these into permanent docs:
- Critic's attacks (monke-docs/critic-notes.md) → ADR "Challenges Considered" section
- Reviewer's violation log → LLD "Review Log" section
- Test plan → LLD directly

Team working files (draft docs, message logs) can be cleaned up after artifacts are captured.

---

## 4. Document Structure

    monke-docs/
      hld.md                      # Living HLD (L1-L3), versioned
      decisions/NNN-slug.md       # ADRs
      lld/component-name.md       # One per component, just-in-time
      open-questions.md           # Parking lot — unresolved questions
      checkpoints/                # Phase checkpoint records
        phase-N-checkpoint.md

---

## 5. HLD Rules

### 5.1 Required Sections

**S1 System Context (L1):** What/for whom/why (one paragraph). External actors/systems. Scope: IN v1 vs explicitly OUT.

**S2 Container Diagram (L2):** Each unit: name, tech, backend language, one-sentence responsibility, container type tag (`traditional`/`agentic`). Communication protocols (cross-language: specify serialization). Deploy topology. Database instances + connection strategy per project-specs S10.1. Frontend target per project-specs S10.1.

**S3 Component Map (L3) per container:** Module name + responsibility. Boundary contracts (exact typed models). Dependency direction. LLD owner. For agentic containers: CoALA summary per S1.2.

**S4 Primary Data Flows (max 3):**

    Trigger -> Module (contract: ModelA) -> Module (contract: ModelB) -> Terminal
    # Agentic: Input -> Agent (observe) -> [retrieve] -> [reason] -> [tool] -> [learn] -> Output/Loop

**S5 Decision Index:** Links to all ADRs grouped by component.

**S6 Open Questions:** Link to open-questions.md, tagged with blocking component.

**S7 Boundary Matrix:**

| Upstream | Contract | Downstream | Error Type | Serialization | Stability | Status |
|----------|----------|------------|------------|---------------|-----------|--------|

Stability values: `static` (default — omit for standard contracts) | `versioned(<artifact>, <pin>)` | `data-dependent(<baseline>)`. Stability determines test obligations (eval tier) and contract maintenance expectations per S1.2 tool taxonomy.

**S8 Phase Plan & Test Gate Summary:** Phases, components per phase, test gate status. See S11.

### 5.2 Banned From HLD

Function bodies, algorithms, exhaustive schemas, features beyond v1, internal mechanics prose, dependency versions, CI setup, decorative language, agent internals.

### 5.3 Quality Gate

| Check | Test |
|-------|------|
| Implementable | Can a dev build without unrecorded decisions? |
| Bounded | Every module has a typed boundary contract? |
| Navigable | Find any component's LLD in 30 seconds? |
| Honest | Unknowns in open-questions.md, not papered over? |
| Minimal | Every sentence: constraint, decision, contract, or question? |
| Audited | Boundary matrix verified (Contracts Auditor or lead)? |
| Attacked | Critic reviewed, challenges recorded in ADR? |
| Stack-compliant | All containers use locked tech per S2? |
| Language-justified | Non-default language choices backed by ADR with measurable justification? |
| Pattern-justified | Agentic components have pattern ADR? Simplest that works? |
| CoALA-complete | Agentic components specify all three dimensions? |
| Phased | Components assigned to phases with system test criteria? |

### 5.4 HLD Maintenance

Changes when: LLD reveals error, component added, decision revisited, OQ resolved, pattern escalated/de-escalated, test gate failure forces redesign. Never for: implementation details, style, speculation.

    Version: 1.3 | Date: 2026-03-20
    Change: Added DriftSignal severity enum after LLD revealed Agent 3 needs it

---

## 6. LLD Rules

### 6.1 When to Create

Only when implementation of that component is about to begin. Never pre-generate.

### 6.2 Creation Process

(1) Spawn LLD team per S3.4. (2) Designer runs ADaPT. (3) **⏸ PG-8: Lead presents decomposition.** (4) Designer writes design, Reviewer verifies (peer-to-peer, max 3 rounds). (5) **⏸ PG-9: Lead presents converged design.** (6) Lead writes test plan. (7) **⏸ PG-10: Lead presents test plan.** (8) Lead assembles final LLD. (9) Update HLD if boundary changed. (10) ADRs for non-obvious decisions.

### 6.3 Required Sections

**Header:**

    Parent HLD: S3.4  |  HLD Version: X.Y
    Backend: per project-specs S10.2  |  ADR: NNN (if non-default)
    Type: traditional/agentic  |  Pattern: <n> (agentic)  |  ADR: NNN
    Upstream: <Model> from <module>  |  Downstream: <Model> to <module>
    Errors: <what crosses boundary>
    Phase: <N>  |  Test gate: pending/passed

**Internal Design:** Full-typed signatures; pure functions separated from IO functions. State machines + transition tables. Algorithms + complexity + edge cases. Expected errors as return types, unexpected as exceptions. LLM interface patterns per project-specs S10.1. Database query layer per project-specs S10.1.

**For agentic, additionally:** Memory schemas + storage + retrieval + eviction + token budget. Tool schemas + sandboxing + retry + action boundaries. Decision loop + stopping condition + max iterations + HITL. Prompt templates + variable injection + output parsing.

**File Map:**

| File | Layer | Exports | Depends On |
|------|-------|---------|------------|

**Unit Test Plan (mandatory):**

| # | Function/Method | Input | Expected | Category | Mocks |
|---|----------------|-------|----------|----------|-------|

Minimum: 1 happy + 1 edge + 1 error per public function. Pure functions (Layer = pure) should need no mocks. Agentic: loop termination, tool failure, stale memory, context overflow.

**Integration Test Plan (mandatory):**

| # | Boundary | Upstream Call | Expected Downstream Effect | Error Scenario | Mocks |
|---|----------|-------------|---------------------------|----------------|-------|

Every boundary contract: upstream, downstream, error propagation, cross-language serialization. Agentic: memory consistency, tool contracts, agent-to-agent messages.

**Review Log:**

| Round | Violation | Resolution |
|-------|-----------|------------|

**Test Implementation Checklist:**

    - [ ] Unit tests written + passing (commit: <hash>)
    - [ ] Integration tests written + passing (commit: <hash>)
    - [ ] LLD test gate: PASSED — date

### 6.4 Banned From LLD

Restating HLD. Aspirational prose. Decisions without rationale. Violating locked stack per project-specs S10.1. Over-engineered patterns (<3 dynamic decisions → de-escalate). Skipping test plans.

---

## 7. ADR Rules

### 7.1 Template

    # ADR-NNN: Title
    Status: proposed | accepted | superseded by ADR-XXX
    Date: YYYY-MM-DD  |  Component: HLD S-X.Y

    ## Context
    ## Options (LATS output)
    ## Challenges Considered (Critic)
    ## Decision — chose X because <project-specific reason>
    ## Consequences — easier / harder / trade-off accepted / HLD impact

### 7.2 When to Write

2+ viable approaches. Library/tool selection. Non-obvious constraint. HLD change from LLD. LATS backtrack. Tech stack exception. Non-default language choice. Auxiliary datastore. Anthropic pattern selection (mandatory). Pattern escalation/de-escalation (mandatory). Test gate failure forcing redesign.

### 7.3 When NOT to Write

Obvious single-option choices. Style decisions. Reversible in 5 minutes with no ripple.

---

## 8. Open Questions

    ### OQ-NNN: Question
    Discovered-during: design | implementation | testing
    Affects: HLD S-X.Y  |  Blocks: LLD for <component> | implementation of <component> | testing of <boundary>
    Options so far: ...
    Status: open | resolved -> ADR-NNN

Rules: Every OQ tags what it blocks (LLD, implementation, or test). Blocking OQs must be resolved before the blocked work proceeds. Resolution → ADR + doc update (HLD, LLD, or both as appropriate).

---

## 9. Claude Behavioral Rules

### 9.1 Planning

1. **Incremental.** L1 ⏸ L2 ⏸ L3 ⏸. Each level ends with a pause gate.
2. **LATS at every branch.** Expand, evaluate, select, **pause for user confirmation**.
3. **Agent team for HLD.** Spawn per S3.3. Not subagents.
4. **Flag unknowns.** → open-questions.md. Never invent answers.
5. **Contracts before internals.** In/out/errors first, then structure.
6. **Challenge scope creep.** Beyond current phase → push back, park as OQ.
7. **No decorative prose.** Constraint, decision, contract, or question. Else delete.
8. **Enforce tech stack.** Reject violations, cite S2 + project-specs S10.1.
9. **Simplest pattern first.** Lowest Anthropic pattern. Escalate only with evidence.
10. **C4 or CoALA, not both at same level.** Tagged at L2.

### 9.2 Implementation

11. **LLD before code.** No LLD → create per S6.2.
12. **Agent team for LLD.** Per S3.4, except trivials per S3.5.
13. **ADaPT during LLD.** Show tree. Agentic: decompose per CoALA dimension. **Pause after decomposition.**
14. **Update docs on divergence.** Fix LLD → fix HLD if boundary changed.
15. **One component at a time.** Build, verify contract, next.
16. **Locked stack enforced.** Use locked technologies per project-specs S10.1. No exceptions without ADR.
17. **De-escalate on evidence.** Fewer dynamic decisions → simpler pattern + ADR.
18. **Tests are not optional.** Unit + integration per LLD. System per phase. See S11.
19. **No advancing past a failed gate.** Fix code or fix design first.

### 9.3 Anti-Patterns to Refuse

| If asked to... | Do instead... |
|----------------|--------------|
| Complete plan for whole project | L1+L2 only. Ask which container to zoom into. |
| Generate all data models | Which boundary? Build ONE, verify, proceed. |
| Full folder structure | Scaffold current phase only. |
| Specs for all agents at once | LLD for current agent. Others stay as HLD stubs. |
| Production-ready from day one | Simplest version satisfying contract. Harden later. |
| Start coding, skip design | Refuse. Minimum: L1 + boundary contract. |
| Skip agent team, use subagents for design | Refuse for HLD/LLD. Subagents can't do adversarial peer review. |
| Swap a locked technology | Refuse. Cite project-specs S10.1 + S2.4. |
| Non-default language without data | Require measurable perf data. Cite S2.1. |
| Full autonomous agent | Simplest Anthropic pattern first. Cite S1.3. |
| Auxiliary store without ADR | Refuse. Cite project-specs S10.3. |
| Skip tests, add them later | Refuse. Tests designed with component per S11. |
| Move to next phase, tests failing | Refuse. Fix or redesign. Cite S11.3. |
| Only unit tests, skip integration | Refuse. Both mandatory per S11.1. |
| Create separate ML/inference/data containers when the model is a tool of an agent | Refuse. The model is a versioned-artifact tool in the agent's action space. Cite S1.2. |
| Organize containers or directories by ML domain (NLP, CV, DL, tabular) | Refuse. Tool taxonomy is by contract behavior (S1.2), not technology domain. |
| Treat LLM calls as special (separate orchestration, separate error handling) | Refuse. An LLM call is a versioned-artifact tool. Same action space, same eval tier, same contract. |
| Build a standalone feature engineering or data preprocessing pipeline | Refuse. Pre/post-processing is the pure-function layer around a tool call (implementation-specs Layer 2). Not a separate system. |

### 9.4 Pause Gates (Mandatory User Confirmation Points)

Claude MUST stop generating and wait for explicit user confirmation at every pause gate. Claude does NOT auto-proceed by assuming agreement. Claude does NOT combine multiple gates into one response.

**Format:**

    ⏸ PAUSE GATE: <what was just decided/presented>
    Recommended: <recommendation with reason>
    Alternatives: <runner-ups or "none">
    Confirm / Adjust / Reject?

#### Schedule

| ID | Trigger | Proceeds When |
|----|---------|--------------|
| PG-1 | L1 Context drafted | User confirms L1 |
| PG-2 | L2 Containers drafted | User confirms L2 |
| PG-3 | L3 Components drafted | User confirms L3 |
| PG-4 | Boundary matrix audited | User confirms no gaps |
| PG-5 | LATS decision point | User confirms selection |
| PG-6 | Backend language choice (non-default) | User approves exception |
| PG-7 | Anthropic pattern selection | User confirms pattern |
| PG-8 | ADaPT decomposition | User confirms before sub-problems attempted |
| PG-9 | LLD design converged | User confirms design |
| PG-10 | Test plan complete | User confirms test plan |
| PG-11 | Phase checkpoint | User signs off phase (**never skippable**) |
| PG-12 | Stack violation | User grants/denies exception |
| PG-13 | Test failure >2 cycles | User decides: fix, redesign, or escalate |
| PG-14 | HLD revision from LLD | User confirms HLD update |

#### Rules

1. **One gate per response.** Complete work to next gate, present, stop.
2. **No implicit confirmation.** "Looks good" = confirm. Silence = ask again.
3. **Gate output is the artifact.** The actual L1 draft / options / test plan, not a summary.
4. **User can opt out selectively.** "Auto-confirm trivial LATS" is fine. PG-11 never skippable.
5. **PG-5 fires per branch.** Each LATS decision within a level is a separate pause if non-trivial.

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| HLD | High-Level Design (L1+L2+L3). Navigation map. |
| LLD | Low-Level Design (L4). Construction blueprint for one component. |
| ADR | Architecture Decision Record. Why X over Y. |
| Boundary contract | Typed model/schema at a module boundary. |
| C4 | Four-level architecture model. Traditional systems + outer boundaries. |
| CoALA | Memory + Action Space + Decision Procedure. Agentic internals. |
| Anthropic pattern | Complexity ladder. Simplest that works wins. |
| LATS | Design space exploration. Expand, evaluate, select, backtrack. |
| ADaPT | Recursive decomposition for LLD. Decompose, attempt, assess, adapt. |
| Agent team | Claude Code Agent Teams — independent sessions with shared task list + peer messaging. NOT subagents. |
| Subagent | Task tool — child agent within parent session, reports back only. Used for implementation, not design. |
| Locked choice | Tech in S2.1 / project-specs S10.1. Cannot change without user-approved ADR exception. |
| Pause gate | Mandatory user confirmation point. Claude stops and waits. S9.4. |
| Test gate | Pass/fail checkpoint. Unit+integration per LLD, system per phase. |
| Phase checkpoint | All LLD gates + system tests green. Recorded in monke-docs/checkpoints/. |
| LLM sidecar | HTTP wrapper for LLM interface. Used by containers not natively supporting the locked LLM library. |
| Static-contract tool | External tool with deterministic, deployment-fixed contract. Default subtype. |
| Versioned-artifact tool | External tool whose output depends on a versioned artifact (model, index). Requires eval tier. |
| Data-dependent tool | External tool whose output semantics drift with input distribution. Requires eval tier. |
| Eval test | Metric-threshold assertion for components with versioned-artifact or data-dependent tools. Runs within IL-2/IL-3. |
| Stability (boundary) | Boundary matrix column indicating contract behavior: static, versioned, or data-dependent. |
| MCP | Model Context Protocol. A tool access protocol. Classified by the underlying tool's contract behavior (S1.2), not by the protocol itself. |

---

## 11. Test Gates & Phased Checkpointing

Tests are designed during LLD creation and implemented alongside the component. No component is complete without passing tests. No phase advances without all gates green.

### 11.1 Test Tiers

| Tier | Scope | When Written | When Run | Pass Gate For |
|------|-------|-------------|----------|---------------|
| **Unit** | Single function/class in isolation | LLD creation | After each function implemented | Completing LLD component |
| **Integration** | Boundary contract between components | LLD creation | After component + neighbors available | Phase checkpoint |
| **Eval** | Metric threshold for versioned-artifact or data-dependent components | LLD creation | With unit (IL-2, mocked artifact) and integration (IL-3, real artifact) | IL-2 / IL-3 (no separate gate) |
| **System** | End-to-end HLD data flow (S4) | Phase planning (before phase starts) | After all phase components pass unit + integration + eval | Phase completion |

#### Unit Tests

Every public function: 1 happy + 1 edge + 1 error minimum. State machines: every transition + invalid. Agentic: loop termination, tool failure, stale memory, context overflow. Isolation: all external services mocked. No network, no filesystem side effects.

#### Integration Tests

Every boundary in HLD matrix: upstream consumption, downstream production, error propagation. Cross-language: serialization round-trip. Agentic: memory write→read, tool call contract, agent-to-agent messages. Isolation: both sides REAL, everything else mocked. Database: real test instance per project-specs S10.1.

#### Eval Tests

Applies only to components whose tools include versioned-artifact or data-dependent subtypes (S1.2).

- Assertions are **metric thresholds** (accuracy ≥ X, latency p99 ≤ Y, drift score ≤ Z), not exact-match.
- **Unit-level eval (runs at IL-2):** mocked artifact, fixture dataset. Verifies pre/post-processing logic produces expected metrics. Tests the function's correctness, not the artifact's quality.
- **Integration-level eval (runs at IL-3):** real artifact, test dataset. Verifies the actual artifact meets the metric threshold defined in the LLD.
- Eval metrics are defined in the LLD test plan alongside unit and integration tests — not in a separate document.
- A failing eval metric blocks the gate exactly like a failing test. No weakening thresholds to pass.
- Components with only static-contract tools have no eval obligations.

#### System Tests

Each HLD S4 data flow end-to-end. Error injection per flow. Agentic: full loop with happy and adversarial inputs. All internal components REAL. External systems mocked or sandbox.

### 11.2 Test Rules

1. Test plan written during LLD — concrete inputs, expected outputs, categories.
2. Tests implemented WITH the component. Not after.
3. Integration tests upgraded mock → real when both sides exist.
4. System tests written at phase start as acceptance criteria.
5. Framework per language (flexible via LATS + ADR) — see project-specs S10.2.
6. No test-only PRs. Tests ship with their code.

### 11.3 Phased Checkpointing

#### Phase Definition (HLD S8)

    ## Phase N: <n>
    Components: [LLD components]
    Data flows enabled: [which S4 flows become testable]
    Depends on: Phase N-1 passed
    System test criteria: [end-to-end proof]

#### Checkpoint Record (monke-docs/checkpoints/phase-N-checkpoint.md)

    # Phase N Checkpoint: <n>
    Date: YYYY-MM-DD  |  HLD Version: X.Y

    ## Component: <n> (LLD: lld/component.md)
    - [ ] Unit tests passing (commit: <hash>)
    - [ ] Integration tests passing (commit: <hash>)
    - [ ] LLD gate: PASSED / FAILED

    ## System Tests
    - [ ] Defined for flows: <list>
    - [ ] Passing (commit: <hash>)

    ## Phase Gate
    - [ ] ALL component gates PASSED
    - [ ] ALL system tests PASSED
    - [ ] HLD updated if needed + ADRs written
    - [ ] OQs resolved or deferred with justification
    - [ ] ⏸ USER SIGN-OFF (PG-11)

    Status: PASSED / BLOCKED — <reason>

#### Gate Failure Protocol

1. **Unit failure:** Fix implementation or LLD. Boundary affected → update HLD + ADR.
2. **Integration failure:** Find wrong side. Contract wrong → update HLD matrix + both LLDs.
3. **System failure:** Trace to boundary. Apply integration protocol.
4. **Persistent (>2 cycles):** **⏸ PG-13.** Escalate to user. Likely LATS backtrack.

Claude MUST NOT weaken a test to pass a gate.
