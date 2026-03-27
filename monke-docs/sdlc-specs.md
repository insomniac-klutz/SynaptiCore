# SDLC Specs

> How the specs docs connect end-to-end. Each phase follows this flow — design specs produces the inputs that implementation specs consumes, and test gates enforce quality at every transition.

---

## 1. HLD (one-time, governs all phases)

Design specs owns this. Uses Agent Teams (Architect + Critic).

```
L1 Context → ⏸ PG-1 → L2 Containers → ⏸ PG-2 → L3 Components → ⏸ PG-3 → Boundary Matrix → ⏸ PG-4
```

Output: `monke-docs/hld.md` with phase plan (S8), boundary matrix (S7), data flows (S4). LATS (⏸ PG-5) fires at every design branch within each level.

---

## 2. LLD (per component, just-in-time)

Design specs owns this. Uses Agent Teams (Designer + Reviewer).

```
ADaPT decomposition → ⏸ PG-8 → Design rounds (max 3) → ⏸ PG-9 → Test plan → ⏸ PG-10
```

Output: `monke-docs/lld/<component>.md` with typed signatures, file map, unit test plan, integration test plan.

---

## 3. Implementation (per component)

Implementation specs owns this. IL gates are self-verification (no user pause).

```
Layer 0: Types/models/schemas → IL-0 (imports resolve, migration up/down)
Layer 1: Function stubs + annotations → IL-1 (skeleton compiles)
Layer 2: Bodies + unit tests (interleaved per function) → IL-2 (all unit tests pass)
Layer 3: Integration tests → IL-3 (full suite green, coverage met)
```

Dependency order: implement functions per LLD decomposition tree. Each function body is immediately followed by its unit tests — never batch.

---

## 4. Phase Checkpoint

Design specs owns the gate. Requires ALL components in the phase to have passed IL-3.

```
All component IL-3 gates green → System tests (end-to-end HLD data flows) → ⏸ PG-11 (user sign-off)
```

Output: `monke-docs/checkpoints/phase-N-checkpoint.md`. Phase N must pass before Phase N+1 begins.

---

## 5. Doc Interaction Map

```
design-specs.md ──produces──→ HLD + LLD artifacts
                                        │
                                   (hand-off: LLD file map + signatures + test plans)
                                        │
                                        ▼
implementation-specs.md ──consumes──→ Layer 0-3 pipeline
                                        │
                                   (hand-off: passing IL-3 gate)
                                        │
                                        ▼
design-specs.md §11 ──owns──→ Phase checkpoint (PG-11)

project-specs.md ──binds──→ All of the above to concrete tools + locked stack (S2, S8-S10)
test-specs.md ──governs──→ HOW tests are written (tiers, fixtures, mocks, coverage rules)
```

---

## 6. Failure Protocol

| Failure at | Action |
|------------|--------|
| Unit test (IL-2) | Fix implementation or surface LLD issue to user |
| Integration test (IL-3) | Trace to boundary — update HLD matrix + both LLDs if contract wrong |
| System test | Trace to boundary, apply integration protocol |
| Persistent (>2 cycles) | ⏸ PG-13 — escalate to user. Likely LATS backtrack required |

Claude MUST NOT weaken a test to pass a gate. Claude MUST NOT advance past a failing gate.
