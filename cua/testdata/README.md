# testdata/ — fixtures (builder 2, S1)

Stand-in **upstream inputs** so the agent runs and is tested before the real upstream agents
(Literature Synthesis, Patient Subgroup, Treatment Connection, Evidence Scoring, Commercial
Discovery) exist. **Fixtures, not agents** — no live literature search, no real GRADE assessment.

Governing contract: `files/conclusion_update_agent_test_data_contract.md`. Types are defined in the
**main contract** (`contracts.md` §1.1, §2.1, §2.3) — this layer *populates* them, never redefines.

> Scaffold note: empty. First brief is `build/briefs/S1_fixtures.md`. Header per CONVENTIONS rule 1.

## What lands here (S1)

| File (planned) | Implements | Notes |
|---|---|---|
| the 5 `Fixture` scenarios | test-data §4 | `clean_high_grade`, `thin_corpus`, `low_grade_bait`, `fabrication_bait`, `unscored_claim` |
| `validate(fixture)` | test-data §6 | type-checks every field vs main contract; asserts `input_contract.required` populated + internally consistent (`claim_id ↔ support_source_ids ↔ corpus`) |
| each fixture's `Expectations` | test-data §5 | oracle consumed by tests/ (builder 3): `expect_pass`, `expected_overclaim_claim_ids`, `expected_orphan_ids`, `min_obligations_satisfied` |

## Hard rules (from the contract)

- Every synthetic `Paper.id` carries a **`SYNTH-`** prefix (test-data §2) — real vs fake never confused.
- `resolvable_id` is **plausibly formatted but fake by default** ⇒ `resolve_rate` is known-low and
  **not asserted**; the offline cited-∈-corpus gate is exercised fully (test-data §2). One scenario
  may carry a few **real** DOIs/PMIDs (`real=true`) for a resolve smoke-test.
- Same `seed` ⇒ identical `Fixture` (test-data §6).
- Minimal stand-in shapes for `GrantCall`, `subgroups`, `treatments`, `CommercialLandscape` are
  defined here and **flagged for reconciliation** (design §6 gap; `build/decisions/OPEN.md`).
