# NIH Grant — `RubricObligation` set (v1, first pass)

**What this is.** The concrete, checkable obligations the **Blueprint Planner** emits for an
`NIHGrantTask` — the NIH Simplified Review Framework compiled into `RubricObligation`s. The agent's
draft is checked against this set: the Internal Critic scores the qualitative ones, the hard
invariants (main contract §3) enforce the structural ones. This is a **minimal v1 template** — the
Blueprint specializes each `requirement` to the topic at plan time; the *shape* below is fixed.

**Grounded in** the NIH Simplified Review Framework (RPG due dates ≥ 2025-01-25): the five
regulatory criteria (Significance, Innovation, Approach, Investigator, Environment) reorganized into
three factors — F1 and F2 scored 1–9, F3 rated sufficient/insufficient. The organizing question is
*"Can and should the proposed research be conducted?"* → F1 = *should*, F2 = *can*, F3 = *by this
team, here*. Sources at the end.

**Maps to** `RubricObligation = Obligation` (main contract §1.2): `dimension ∈ {F1, F2, F3}`,
`requirement` = the predicate below, `satisfied_by` = Proposal section/aim ids, `evidence_ids` =
backing corpus / `EvidenceScores` keys. `self_score` is 1–9 for F1/F2, {sufficient, insufficient}
for F3. **`check`** = how it's verified: **code** (structural / countable, by the Orchestrator or
the invariants) or **critic** (qualitative, scored by the Internal Critic on its dimension) — the
`[hard structure · soft check]` split of principle 1.

---

## Factor 1 — Importance of the Research (Significance + Innovation) · scored 1–9 · *should it be done?*

| ID | Requirement (checkable) | Check | Satisfied by |
|----|--------------------------|-------|--------------|
| F1-1 | The Significance section names a specific problem or barrier to progress and states why resolving it matters to the field, with ≥1 corpus citation. | critic + code (≥1 `evidence_id`) | `significance` |
| F1-2 | A single central hypothesis is stated explicitly and follows from the named gap. | code (present) + critic (follows) | `central_hypothesis` |
| F1-3 | Innovation names the specific departure from current concepts, methods, or practice being claimed — not a generic "novel". | critic | `innovation` |

## Factor 2 — Rigor and Feasibility (Approach) · scored 1–9 · *can it be done?*

| ID | Requirement (checkable) | Check | Satisfied by |
|----|--------------------------|-------|--------------|
| F2-1 | Each aim states one explicit, testable hypothesis or objective. | code (present per aim) + critic (testable) | `aims[].hypothesis` |
| F2-2 | Each aim's approach names the key methods/design at enough specificity to judge rigor — not goals alone. | critic | `aims[].approach` |
| F2-3 | Each aim includes a pitfalls / alternative-strategies paragraph. | code (present per aim) | `aims[].pitfalls_alternatives` |
| F2-4 | Each aim states expected outcomes tied to its hypothesis. | code (present per aim) + critic (tied) | `aims[].expected_outcomes` |

## Factor 3 — Expertise and Resources (Investigator + Environment) · sufficient / insufficient · *by this team, here?*

> **Scope.** This agent writes from scientific evidence, not investigator or institutional data, so
> it cannot *evidence* F3. It surfaces what F3 requires and defaults to `insufficient` (needs
> external confirmation) rather than asserting a sufficiency it can't support.

| ID | Requirement (checkable) | Check | Satisfied by |
|----|--------------------------|-------|--------------|
| F3-1 | For each aim, the expertise and resources the approach assumes are surfaced, so an investigator/environment owner can confirm sufficiency. | code (present per aim) | `aims[].approach` |
| F3-2 | The agent does not assert F3 sufficiency; `self_score` defaults to `insufficient` pending external confirmation. | code (policy) | — |

## Cross-cutting (enforced by the hard invariants, main contract §3 — not Critic-scored)

| ID | Requirement | Check |
|----|-------------|-------|
| X-1 | Every empirical claim carries an `evidence_id`, and every citation ∈ corpus. | code — invariant 1 (citation integrity) |
| X-2 | No claim's assertiveness exceeds the rung its evidence grade permits. | code — invariant 3 (overclaim; main contract §1.12) |

---

## Notes for the Blueprint Planner

- Emit one `RubricObligation` per row above; specialize the `requirement` wording to the topic
  (e.g. name the actual disease/mechanism in F1-1), but keep the predicate checkable.
- F2-1…F2-4 and F3-1 are **per-aim** — instantiate one obligation per aim (`map_over = aims`).
- `status` starts `unsatisfied`; the writer sets `satisfied_by` + `self_score`; the Critic scores
  the `critic` rows blind; `code` rows are decided by the invariants.

## Sources

- NIH, *Simplified Review Framework for NIH Research Project Grant Applications* — three factors;
  F1/F2 scored 1–9; F3 sufficiency:
  https://grants.nih.gov/policy-and-compliance/policy-topics/peer-review/simplifying-review
- NIH CSR, *Review Matters* / NIH Extramural Nexus announcement — the "can and should the proposed
  research be conducted?" framing and factor definitions:
  https://www.csr.nih.gov/reviewmatters and https://nexus.od.nih.gov (Simplified Review Framework).
