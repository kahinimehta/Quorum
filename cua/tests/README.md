# tests/ — tester & reviewer (builder 3)

Verifies the agent at development time. **Read-only** over the agent's outputs; runs **outside the
agent loop**. The only feedback it provides upstream is the Critic-calibration target — computed
offline, never injected into a live run (test-review boundaries).

Governing contract: `files/conclusion_update_agent_test_review_contract.md`. Invariant definitions:
main contract §3, §1.12.

> Status: Part A (offline invariants) landed at S3 (`invariants.py` + `test_invariants.py`); Part B
> (eval & calibration) landed at S7 (`tests/eval/`). Part C (review report) is S8. Part A needs only
> outputs — no LLM, no network. Part B *in production* needs network + an LLM judge; the **v1 build is
> offline + deterministic** — the blinded judge + RePORTER reference set are deterministic surrogates
> and the live paths are gated (build/decisions/2026-06-02-eval-methodology.md). Header per CONVENTIONS
> rule 1; tests cite invariant / B-criterion ids per rule 2.

## Part A — offline invariants (S3) — `tests/invariants.py`

Run on any `(Proposal, Audit)` or intermediate draft; no LLM, no network. Emits
`InvariantReport: { per_test, all_passed }`.

| id | invariant | contract |
|---|---|---|
| `inv-1` | citation integrity — `all_in_source_set == true` and `orphan_ids == []` (HARD fail) | §3.1 |
| `inv-2` | obligation coverage — every `status == satisfied` with ≥1 `evidence_id` | §3.2 |
| `inv-3` | no overclaim — every `Audit.overclaim_check` row `ok == true` | §3.3, §1.12 |

On builder-2 fixtures, also assert each fixture's `Expectations` (test-review part A; test-data §5) —
how `fabrication_bait` / `low_grade_bait` / `unscored_claim` negatives are checked.

## Part B — eval harness (S7) — `tests/eval/`

RePORTER reference set (`api.reporter.nih.gov`); a **blinded** LLM judge (different model/prompt from
the Internal Critic); Critic **calibration** (per-factor MAE + rank-corr); **competitiveness** vs
matched funded human grants. Emits `EvalReport`. **Contamination rule:** RePORTER text is never
inserted into any agent input; writer few-shot exemplars stay disjoint from it and abstracted to
structure (test-review part B; design §5).

| file | role | contract |
|---|---|---|
| `reporter_reference.py` | RePORTER reference set (stored, abstracted) + live sampler spec (gated) + the **contamination guard** | B1, Boundaries |
| `blinded_judge.py` | `BlindedJudge` ≠ Internal Critic (Sonnet 4.6 @ temp 0 vs Opus 4.8 effort high; different prompt; source-blind), F1/F2 1–9 + F3 sufficiency | B2 |
| `critic_calibration.py` | per-factor **MAE + Spearman** over the gap-5 anchors; `fill_calibration` (→ `Audit.calibration.{mae,rank_corr}`); the **dev-5** retune projection | B3, §1.10 |
| `competitiveness.py` | AI proposals vs matched funded-human references; per-factor gap (v1 plumbing; S8 expands) | B4 |
| `eval_report.py` | the `EvalReport { calibration, competitiveness, contamination, dev5, n }` assembly | part B |
| `test_eval.py` | the pytest suite (the B-criteria + done-criteria + dev-5) | part B |

Run: `python -m pytest tests/eval` (offline, deterministic) · `python tests/eval/eval_report.py`
(emit the EvalReport JSON) · `python tests/eval/critic_calibration.py` (calibration table + retune).

## Part C — review report (S8) — `tests/review.py`

Given `(Proposal, Trace, Audit, InvariantReport, EvalReport?)` emits a human-readable `ReviewReport`:
which obligations failed/are unmet + the **overclaim list** + **citation issues** + the **calibration
summary** (filled from `Audit.calibration.{mae,rank_corr}` via `fill_calibration`, the single eval
entry point `build_eval_report()`) + a **go/no-go**. The go/no-go gates on the three hard invariants
(§3); a below-bar competitiveness gap is a **caveat, not a NO-GO**. **Review only — never edits the
proposal** (asserted by a deep before/after snapshot). Reports against the **live Critic state** (v1
base-7; the dev-5 retune is ratified-as-analysis, deferred). `review_all()` reviews all 5 fixtures +
a build-level decision; `tests/test_review.py` is the suite.

Run: `python tests/review.py` (per-proposal ReviewReports + the build-level go/no-go) ·
`python -m pytest tests/test_review.py -q`.
