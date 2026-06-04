# Conclusion Update Agent — Tester & Reviewer Contract (builder 3)

**Purpose.** Verify the agent at development time and produce a review. Two parts: **(A) offline
invariants** over any draft/Audit (no LLM, no network), and **(B) an eval harness** that
calibrates the Internal Critic and checks competitiveness against funded human grants.

**Types are defined in `conclusion_update_agent_contracts.md`.** The tester is **read-only** over
the agent's outputs and runs **outside the agent loop**. The single feedback it provides is the
Critic-calibration target — computed offline, never injected into a live run.

---

## A. Hard invariants (offline — the three from main contract §3)

Run on any (`Proposal`, `Audit`) or intermediate draft; no LLM, no network:
1. **Citation integrity** — `grounding_report.all_in_source_set == true` and `orphan_ids == []`. Hard fail.
2. **Obligation coverage** — every `obligation.status == satisfied` with ≥1 `evidence_id`.
3. **No overclaim** — every row of `Audit.overclaim_check` has `ok == true`.
```
InvariantReport: { per_test: list[{name, passed, detail}], all_passed: bool }
```
When run on builder-2 fixtures, also assert the fixture's `Expectations` (`expect_pass`,
`expected_overclaim_claim_ids`, `expected_orphan_ids`, `min_obligations_satisfied`) — this is how
the negative scenarios (`fabrication_bait`, `low_grade_bait`) are checked.

## B. Eval harness (needs network + LLM judge)
1. **Reference set** — pull same-domain **funded** abstracts / Specific Aims from NIH RePORTER
   (`api.reporter.nih.gov`). Store as the comparison corpus.
   **Contamination rule:** RePORTER reference text is used only for scoring/comparison and is
   **never** inserted into any agent input — the agent must not be able to copy funded grants.
   *Writer few-shot exemplars (work plan §5) may be drawn from approved proposals, but must be
   **disjoint from this reference set** and **abstracted to structure** (skeletons, not verbatim
   text), or the competitiveness comparison is rigged.*
2. **Blinded judge** — an LLM-as-judge scores the three NIH factors (F1/F2 on 1–9, F3 sufficiency)
   per proposal with **source identity hidden and order randomized** (AI vs human). The judge is a
   **different model/prompt** from the Internal Critic; deterministic settings (temperature 0 where
   the model supports it, else low effort on Opus).
3. **Critic calibration** — compare `Audit.calibration.internal_scores` (the Critic) against the
   blinded judge on a held-out set: per-factor **MAE** and **rank correlation**. This number is
   what licenses using the Critic as a reward signal.
4. **Competitiveness** — AI proposals' blinded factor scores vs matched funded human proposals;
   report the gap.
```
EvalReport: { calibration: {mae: per-factor, rank_corr: per-factor}, competitiveness: {...}, n: int }
```

## C. Review report
Given (`Proposal`, `Trace`, `Audit`, `InvariantReport`, `EvalReport?`), emit a human-readable
`ReviewReport`: which obligations failed and why, the overclaim list, citation issues, the
calibration summary, and a **go / no-go**. Review only — it never edits the proposal.

## Boundaries
- Read-only over agent outputs; outside the agent loop.
- Blinded judge ≠ Internal Critic (independent eval; different model and prompt).
- The eval **reference set** is never fed into an agent input; writer few-shot exemplars must be
  disjoint from it and abstracted to structure (contamination rule above).
- A/B parts are independent: invariants need only outputs; the harness additionally needs network
  and the judge.
