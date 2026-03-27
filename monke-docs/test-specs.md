# Test Specs

> Governs HOW tests are written — tiers, isolation rules, mock boundaries, fixture strategy, coverage philosophy, and test data management. Design specs (§11) governs WHEN tests are planned and gated. Implementation specs governs WHEN tests are executed in the layer pipeline. Project specs binds these abstract rules to concrete tools.

---

## 1. Test Tiers

| Tier | Scope | When Written | When Run | Pass Gate For |
|------|-------|-------------|----------|---------------|
| **Unit** | Single function/class in isolation | LLD creation (PG-10) | After each function implemented (Layer 2) | IL-2 |
| **Integration** | Boundary contract between components | LLD creation (PG-10) | After component + neighbors available (Layer 3) | IL-3 |
| **Eval** | Metric threshold for versioned-artifact or data-dependent components | LLD creation (PG-10) | With unit (IL-2, mocked artifact) and integration (IL-3, real artifact) | IL-2 / IL-3 (no separate gate) |
| **System** | End-to-end data flow (HLD S4) | Phase planning (before phase starts) | After all phase components pass IL-3 | PG-11 (phase checkpoint) |

---

## 2. Tier Rules

### Unit Tests

- Every public function: **1 happy path + 1 edge case + 1 error case** minimum.
- State machines: every valid transition + every invalid transition.
- Agentic components: loop termination, tool failure, stale memory, context overflow.
- **Isolation:** all external services mocked. No network calls, no filesystem side effects.

### Integration Tests

- Every boundary in the HLD boundary matrix: upstream consumption, downstream production, error propagation.
- Cross-language boundaries: serialization round-trip verification.
- Agentic components: memory write→read consistency, tool call contracts, agent-to-agent message formats.
- **Isolation:** both sides of the boundary under test are REAL. Everything else mocked. Database tests use a real instance, not an in-memory substitute.

### Eval Tests

Applies only to components whose tools include versioned-artifact or data-dependent subtypes (design-specs S1.2).

- Assertions are **metric thresholds** (accuracy ≥ X, F1 ≥ Y, coherence ≥ Z, hallucination rate ≤ W, latency p99 ≤ V, drift score ≤ U, cost per call ≤ T), not exact-match.
- **Unit-level eval (runs at IL-2):** mocked artifact, fixture dataset. Verifies pre/post-processing logic produces expected metrics. Tests the function's correctness, not the artifact's quality.
- **Integration-level eval (runs at IL-3):** real artifact, test dataset. Verifies the actual artifact meets the metric threshold defined in the LLD.
- Eval metrics are defined in the LLD test plan alongside unit and integration tests — not in a separate document.
- A failing eval metric blocks the gate exactly like a failing test. No weakening thresholds to pass.
- Components with only static-contract tools have no eval obligations.

### System Tests

- Each HLD S4 data flow exercised end-to-end.
- Error injection per flow (at least one failure scenario per flow).
- Agentic components: full decision loop with happy and adversarial inputs.
- **Isolation:** all internal components REAL. External third-party systems mocked or sandboxed.

---

## 3. Mock Boundaries

| Dependency | Unit | Integration | System |
|------------|------|-------------|--------|
| Function under test | Real | Real | Real |
| Same-module dependencies | Real | Real | Real |
| Cross-module dependencies | Mocked | Real (both sides) | Real |
| Primary database | Mocked | Real (test instance) | Real (test instance) |
| Cache / message broker | Mocked | Mocked (unless it IS the boundary) | Real |
| External third-party APIs | Mocked | Mocked | Mocked / sandbox |
| Filesystem | Mocked | Mocked | Real |
| LLM calls | Mocked | Mocked | Mocked / sandbox |
| Model artifacts (classifiers, embedders, indices) | Mocked (fixture output) | Real (test instance) | Real |
| Data sources (feature stores, profile stores) | Mocked | Real (test instance) | Real |

**Rule:** Integration tests MUST NOT mock the boundary under test. If both sides aren't available yet, the integration test is deferred — never written with mocks as a placeholder for real components.

---

## 4. Fixture Strategy

### Database Fixtures

- Integration and system tests use a **real database instance** (containerized or service-provided), never an in-memory substitute or mock.
- Dedicated test database — never the development database.
- **Transaction rollback per test:** each test runs inside a transaction that rolls back on teardown. No test data leaks between tests.
- Schema migrations run before the test suite starts to verify model-schema alignment.

### Object Factories

- Factory functions/libraries produce **valid domain objects by default**. Tests override only the fields relevant to the scenario under test.
- Factory choice (library vs manual builders) is a project-specs binding.

### HTTP Mocking

- Mock at the **HTTP transport layer**, not by patching client methods. This catches serialization and URL-construction bugs that method-level mocks hide.

### Async Fixtures

- Async fixtures that acquire resources (DB sessions, connections) must **yield and clean up**, not just return.
- Async test support library is a project-specs binding.

### Test Dataset Fixtures (Eval Tests)

- Eval tests require representative test datasets with known metric baselines.
- Test datasets are version-pinned to the artifact version — when the artifact updates, verify test data compatibility.
- Fixture datasets must be small (CI-fast), representative (distribution matches production expectations), and deterministic (no random sampling at test time).
- Store test datasets as fixtures alongside test files, not in external systems.
- Factory functions for test data override only the fields relevant to the eval scenario, same as object factories.

---

## 5. Coverage Rules

- A **minimum line coverage threshold** is enforced in CI. The specific percentage is a project-specs binding.
- Coverage is a **floor, not a target**. High coverage with weak assertions is worse than moderate coverage with strong assertions.
- **Exclusions:** package init re-exports, Layer 1 placeholder stubs (before Layer 2 fills them in), generated code.
- Coverage drops below threshold → CI fails → gate blocked. No exceptions.

---

## 6. Test Data Management

- **No shared mutable state.** Each test creates what it needs via fixtures/factories and rolls back on teardown.
- **Deterministic.** No unseeded randomness in test data. Timestamps use frozen/controlled time.
- **Realistic shapes.** Test data should resemble production data structures — not `"test123"` or `"foo"` placeholders. Domain-valid identifiers, realistic numeric ranges, valid date formats.
- **No real secrets.** Tests use dummy credential values. Never real API keys, even in local-only test runs.

---

## 7. Test File Organization

- **One test file per LLD module** (unit) or per boundary contract (integration).
- **Test function naming:** `test_<function>_<scenario>` or equivalent describe/it blocks.
- **Shared fixtures** live in a central setup/fixture file at the appropriate directory level — root for DB/session fixtures, subdirectory for tier-specific helpers.
- **Tier separation:** unit, integration, and system tests live in separate directories. This allows running tiers independently.

```
tests/
├── <shared fixtures>
├── unit/
│   └── test_<module>.py (or .ts, .rs, etc.)
├── integration/
│   └── test_<boundary>.py
└── system/
    └── test_<phase_or_flow>.py
```

---

## 8. Test Lifecycle Rules

1. Test plans are written during LLD creation — concrete inputs, expected outputs, categories.
2. Tests are implemented WITH the component, not after. Layer 2 interleaves body + unit test per function.
3. Integration tests are deferred (not mocked) until both sides of the boundary exist.
4. System tests are written at phase start as acceptance criteria, run at phase end.
5. No test-only commits. Tests ship with their code.
6. Tests that reveal an LLD design issue → record in `monke-docs/open-questions.md`, stop, surface to user. Do NOT silently fix the design.

---

## 9. Anti-Patterns to Refuse

| If asked to... | Do instead... |
|----------------|--------------|
| Skip tests, add them later | Refuse. Tests are designed at LLD and implemented with the code. |
| Only unit tests, skip integration | Refuse. Both tiers mandatory per LLD. |
| Mock the database in integration tests | Refuse. Real database instance required. |
| Mock both sides of a boundary in integration | Refuse. Both sides must be real. |
| Weaken a test to pass a gate | Refuse. Fix the code or fix the design. |
| Share mutable state between tests | Refuse. Transaction rollback per test. |
| Write integration tests with mock placeholders | Refuse. Defer the test until both sides exist. |
| Batch all tests after all code | Refuse. Layer 2 interleaves per function. |
| Weaken eval thresholds to pass a gate | Refuse. Fix the artifact, the data, or the design. |
| Create separate eval test infrastructure | Refuse. Eval tests live in the same test dirs, same runner, same gates. |
