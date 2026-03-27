# Implementation Specs

> Core principle: **shape before behavior**. Build the type skeleton, verify the contracts compile, then fill in logic with tests alongside.

---

## 1. Relationship to Design Specs

- This document governs the gap between "design converged" and "phase checkpoint."
- Design specs governs everything before design convergence (HLD/LLD creation, pause gates, ADR, teams).
- Test specs governs HOW tests are written (fixtures, mock boundaries, coverage).
- This document governs WHEN and IN WHAT ORDER code + tests are produced.
- Project specs binds these rules to specific tooling and configuration.

---

## 2. Engineering Foundations

The Contract-First layered approach synthesizes four established practices — three structural (shape the code) and one functional (enforce purity).

### 2.1 Design by Contract (DbC) — Bertrand Meyer, 1986

The foundational practice. Every software module has a precise specification — preconditions, postconditions, invariants — defined BEFORE implementation. Contracts between modules are the primary design artifact, not the logic inside them.

**How it drives this approach:** Layer 0 (types) and Layer 1 (signatures) ARE the contracts. Schema validators define preconditions/postconditions. ORM models define invariants. If contracts compile and imports resolve, module boundaries are correct before a single line of logic exists.

**Key insight:** Bugs cluster at boundaries, not inside functions. Verifying contracts first catches the highest-impact defects earliest.

### 2.2 Type-Driven Development — ML/Haskell Community

"Make illegal states unrepresentable" — encode domain rules in the type system so incorrect programs cannot compile. Types ARE the specification; implementation is guided and constrained by them.

**How it drives this approach:** Even in dynamically-typed or gradually-typed languages, schema validators + ORM column types + linter type checking approximate this. Layer 0 encodes structural rules. If types are wrong, Layer 2 bodies will fight them — so get types right first.

### 2.3 Stepwise Refinement — Niklaus Wirth, 1971

Decompose a program top-down in successive layers of detail. Each layer is a complete, verifiable artifact. Never jump from specification to full implementation — refine through intermediate representations.

**How it drives this approach:** The four layers are refinement steps:
- Layer 0: **what data exists** (structure)
- Layer 1: **what operations exist** (interface)
- Layer 2: **how operations work** (behavior)
- Layer 3: **how modules interact** (integration)

### 2.4 Pure Functions, Clear Boundaries — Meyer (CQS, 1988), Bernhardt (FC/IS, 2012), Wlaschin (ROP, 2014)

Functions are either **pure** (compute values, deterministic, no side effects) or **effectful** (IO, DB, network). Don't mix. Business logic goes in pure functions. Side effects are pushed to a thin outer layer (the "shell"). Expected errors are return values, not exceptions.

**How it drives this approach:**
- Layer 0: models frozen/immutable by default. Define error types alongside data types.
- Layer 1: separate pure signatures from IO signatures.
- Layer 2: implement pure functions first (trivially testable), then wire IO shell around them.

**Key insight:** If a unit test needs mocks, the function is doing too much — extract the logic into a pure function and push the IO to the caller.

### Why These Four Together

| Practice | Contribution | Without it |
|----------|-------------|------------|
| Design by Contract | Boundary correctness before logic | Bugs found at integration time (expensive) |
| Type-Driven Dev | Domain rules in types, not comments | Runtime surprises from invalid states |
| Stepwise Refinement | Verifiable intermediate steps | Big-bang implementation with no checkpoints |
| Pure Functions, Clear Boundaries | Logic separated from IO, errors in types | Business logic buried in handlers, invisible exception flows |

The first three enforce **shape**. The fourth enforces **purity** — logic separated from side effects.

---

## 3. Contract-First Layered Pipeline

### Layer 0: Type Skeleton
- Create all enum, model, and schema files from the LLD file map.
- No logic, no method bodies — pure declarations and column/field definitions.
- Models and schemas **frozen by default**. Define error types alongside data types.
- **Versioned types:** For types serving versioned-artifact or data-dependent tools (design-specs S1.2): include artifact version pin and distributional expectations as declarative annotations. These are still pure declarations — no logic — but they encode contract stability metadata that Layer 2 and eval tests depend on. Example (language-agnostic):
  ```
  EmbeddingVector:
    dimensions: 768             # pinned to model version
    model_version: "v2.1"       # artifact version pin
    value_range: [-1.0, 1.0]    # distributional expectation

  LLMToolConfig:
    model_id: "claude-sonnet-4-6"    # exact model version pin
    max_tokens: 4096                  # output budget
    temperature: 0.7                  # sampling config
    prompt_template_version: "v2.3"   # procedural memory pin
  ```
- Verification: linter clean + all cross-module imports resolve.
- If applicable: generate database migration from models, verify up + down.
- Gate: **IL-0** — all types importable, models frozen, version pins present (if applicable), migration runs (if applicable), linter clean.

### Layer 1: Interface Skeleton
- Create all function/method stubs with full type annotations from LLD signatures.
- Separate pure signatures from IO signatures. Fallible functions return error types, not raise exceptions.
- Bodies are placeholder stubs (e.g., `raise NotImplementedError`).
- Docstrings from LLD (one-liner purpose + param types).
- Verification: linter clean + downstream modules can import upstream.
- Gate: **IL-1** — compilable skeleton, all imports resolve, pure vs IO separated.

### Layer 2: Bodies + Unit Tests (interleaved)
- Implement **pure functions first**, then IO shell that calls them.
- **For components with versioned-artifact or data-dependent tools:** the pre/post-processing around the tool call is pure (prompt construction, feature extraction, input validation, output parsing, response scoring, metric computation). The tool call itself (LLM call, model inference, embedding search, feature store query, artifact loading) is IO shell. Decompose accordingly — the pure logic is trivially testable, the IO shell is thin.
- For each function (in dependency order per LLD decomposition tree):
  1. Replace stub with real implementation.
  2. Write unit tests for that function per LLD test plan rows.
  3. For functions with eval obligations: write unit-level eval tests (mocked artifact, fixture data).
  4. Run unit tests + eval tests — must pass before moving to next function.
  5. Run linter on modified files.
- Gate: **IL-2** — all unit tests passing, eval tests passing (if applicable), linter clean, pure functions have no IO.

### Layer 3: Integration Tests + Verification
- Write integration tests per LLD integration test plan.
- **For components with eval obligations:** write integration-level eval tests (real artifact, test dataset, metric thresholds from LLD).
- Run full test suite (unit + integration + eval).
- Verify coverage meets project-defined threshold.
- Update LLD test checklist with commit references.
- Gate: **IL-3** — all tests passing (including eval), coverage met → ready for phase checkpoint.

### Layer Diagram

```
Design converged (e.g., PG-9/PG-10)
    │
    ▼
┌─────────────┐
│  Layer 0    │  Types, enums, models (frozen), schemas, error types
│  IL-0 gate  │  Imports resolve, models frozen, migration runs
└──────┬──────┘
       │
┌──────▼──────┐
│  Layer 1    │  Function stubs + types, pure vs IO separated
│  IL-1 gate  │  Compilable skeleton
└──────┬──────┘
       │
┌──────▼──────┐
│  Layer 2    │  Pure functions first → IO shell second, tests interleaved
│  IL-2 gate  │  All unit tests passing, pure functions have no IO
└──────┬──────┘
       │
┌──────▼──────┐
│  Layer 3    │  Integration tests + coverage
│  IL-3 gate  │  Full suite green → phase checkpoint ready
└─────────────┘
```

---

## 4. Implementation Gates (IL-0 through IL-3)

| ID | After Layer | Verification | Proceeds When |
|----|-------------|-------------|---------------|
| IL-0 | 0 (Types) | Linter clean, all imports resolve, models frozen by default, version pins present (if applicable), migration up/down (if applicable) | Types correct |
| IL-1 | 1 (Signatures) | Linter clean, downstream can import upstream, pure vs IO separated | Skeleton compilable |
| IL-2 | 2 (Bodies) | All unit tests pass, eval tests pass (if applicable), linter clean, pure functions have no IO | Logic correct |
| IL-3 | 3 (Integration) | Full suite green (including eval), coverage ≥ threshold, LLD checklist updated | → Phase checkpoint |

IL gates are lightweight self-verification (run commands, check output). They are NOT user-confirmation pause gates — the user confirms at the phase checkpoint gate defined in the design specs.

---

## 5. Dependency Management Principles

- All dependencies managed via the project's package manager + manifest file.
- Separate production and development/test dependencies.
- Pin minimum versions, not exact (allow patch updates).
- Sync/install before any implementation session.
- Adding a new dependency requires: (a) verify not already available, (b) add via package manager, (c) note in commit message.
- Locked-stack dependencies (per project-specs S10.1) require ADR for changes.

---

## 6. Code Standards (Universal)

### Naming
- Files: match LLD file map exactly (language conventions apply).
- Types/Classes: PascalCase.
- Functions/Methods: language convention (snake_case for Python, camelCase for TS/JS).
- Constants: UPPER_SNAKE_CASE.
- Test files: `test_<module>` or `<module>.test` (language convention).
- Test functions: `test_<function>_<scenario>` or describe/it blocks.

### Imports
- Grouped: stdlib → third-party → local (enforced by linter).
- Absolute imports preferred over relative.
- No circular imports (LLD dependency arrows are acyclic by design).

### Module Structure
- Each LLD file map entry = one file.
- Package/module init files re-export public API (what LLD lists as "Exports").
- Internal helpers prefixed with `_` (or equivalent visibility modifier).

---

## 7. Migration Workflow (Database Projects)

Applies when the project uses a relational database with schema migrations:

1. Layer 0 creates all ORM/model definitions.
2. Initialize migration tool (first time only).
3. Configure migration env to discover models.
4. Auto-generate migration from model diff.
5. Review generated migration (auto-generation misses: RLS policies, custom indexes, enum types, triggers).
6. Hand-add any SQL from LLD that auto-generation cannot produce.
7. Run migration up — verify schema correct.
8. Run migration down — verify clean teardown.
9. Commit migration with Layer 0 code.

---

## 8. AI Assistant Behavioral Rules (Implementation)

When an AI assistant performs implementation:

### Layer 0-1 Rules
- Read the entire LLD before starting Layer 0.
- Create ALL files in the file map at once, not incrementally.
- Layer 0 commit: `Add <component> type skeleton (Layer 0)`
- Layer 1 commit: `Add <component> interface skeleton (Layer 1)`

### Layer 2 Rules
- Implement functions in LLD decomposition dependency order.
- After each function: immediately write its unit tests.
- Run tests after each function, not in batch.
- If a test reveals an LLD design issue → record in `monke-docs/open-questions.md`, stop, surface to user. Do NOT silently fix the LLD.
- Commit granularity: one commit per sub-problem, not per function.

### Layer 3 Rules
- Write integration tests per LLD plan, one boundary at a time.
- Integration tests use real backing services (not mocks) per test specs.
- After full suite green: update LLD checklist with commit references.

### Anti-Patterns to Refuse

| If asked to... | Do instead... |
|----------------|--------------|
| Skip Layer 0-1, go straight to bodies | Refuse. Skeleton catches contract errors early. |
| Write all tests after all code | Refuse. Layer 2 interleaves body + tests. |
| Skip IL gates | Refuse. Run linter + verify imports at each layer. |
| Mock backing services in integration tests | Refuse. Real services per test specs. |
| Combine multiple LLD components in one pass | Refuse. One component at a time. |
| Put business logic in IO functions | Refuse. Extract to pure function, IO calls pure. |
| Raise exceptions for expected errors | Refuse. Return error type. Exceptions for unexpected only. |

---

## 9. Glossary

| Term | Meaning |
|------|---------|
| Layer 0 | Type skeleton: enums, models (frozen), schemas, error types. No logic. |
| Layer 1 | Interface skeleton: function stubs with types, pure vs IO separated. |
| Layer 2 | Body implementation with interleaved unit tests. Pure first, shell second. |
| Layer 3 | Integration tests + coverage verification. |
| IL-N | Implementation Layer gate. Lightweight self-verification. |
| Compilable skeleton | Layer 0+1 complete: all imports resolve, no logic yet. |
| Contract-First | Build types and signatures before behavior. Shape before logic. |
| Pure function | Deterministic, no IO, no side effects. Same input → same output. |
| Shell | Thin IO layer that calls pure functions and handles side effects. |
| Result/error type | Return type encoding success or expected failure. Replaces exceptions for expected errors. |
| Versioned type | Layer 0 type carrying an artifact version pin and optional distributional expectations. Still pure declaration. |
