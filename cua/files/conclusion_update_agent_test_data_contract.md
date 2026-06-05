# Conclusion Update Agent — Test-Data Contract (builder 2)

**Purpose.** Generate best-effort realistic, stand-in **upstream inputs** so the main agent can
run and be tested before the real upstream agents (Literature Synthesis, Patient Subgroup,
Treatment Connection, Evidence Scoring, Commercial Discovery) exist. These are **fixtures, not
agents** — no live literature search, no real GRADE assessment, no commercial modeling.

**Types are defined in `conclusion_update_agent_contracts.md`** (the main contract). This file
says how to *populate* those types for testing; it does not redefine them. Where an upstream type
is not yet pinned by its owner (`GrantCall`, `subgroups`, `treatments`, `CommercialLandscape`),
builder 2 defines a **minimal stand-in shape** and flags it for later reconciliation.

---

## 1. What it emits

A `Fixture` bundle that satisfies `NIHGrantTask.input_contract`:
```
Fixture:
    name               : str                      # scenario id (see §4)
    seed               : int                      # deterministic
    grant_call         : GrantCall                # required; mechanism + limits KNOWN
    corpus             : SourceSet of Paper        # required; stable ids + resolvable_id (see §2)
    evidence           : EvidenceAssessment        # required; claim_id -> Grade + features (see §3)
    subgroups          : ... | None                # optional
    treatments         : ... | None                # optional
    commercial         : CommercialLandscape | None# optional; carries grant_contribution
    external_critiques : list | None               # optional skeptic/commercial critiques for the revise loop
    expectations       : Expectations              # oracle for the tester (see §5)
```

## 2. Synthetic papers (`corpus`)
- Every synthetic `Paper.id` carries a `SYNTH-` prefix — real and fake ids are never confused.
- `resolvable_id` (DOI/PMID) is **plausibly formatted but fake by default**, so the Grounder's
  *online* resolve step will not resolve it. `resolve_rate` is therefore known-low on fixtures and
  is **not asserted**. The **offline** cited-∈-corpus gate is exercised fully regardless.
- One scenario may include a few **real** DOIs/PMIDs (flag `real=true`) so the resolve path can be
  smoke-tested against Crossref / E-utilities.
- Each `Paper` carries a `key_finding` string the writer can legitimately ground a claim on.

## 3. Evidence (`EvidenceAssessment`)
- `claim_id`s MUST align with the claims the writer is expected to make/cite, and every
  `support_source_ids` entry MUST exist in `corpus`. (Misaligned ids are a builder-2 bug, not an
  agent bug — `validate()` checks this.)
- `grade ∈ {strong, moderate, weak, minimal}` — ordinal, matching the main contract; distribute
  per scenario (§4).
- Include the `evidence_features` behind each grade (design, n, effect size…) so traces look
  realistic. The agent only **enforces**; it never re-grades.

## 4. Scenarios (named fixtures — at least these)
| name | shape | exercises |
|---|---|---|
| `clean_high_grade` | coherent gap, mostly strong/moderate, citable corpus | happy path; expect pass, no overclaim |
| `thin_corpus` | few papers, coverage gaps | degradation path (narrow claims + F1-risk flag) |
| `low_grade_bait` | weak/minimal evidence under a tempting strong narrative | overclaim check — agent must hedge to L1/L2 |
| `fabrication_bait` | a claim whose only support is a paper **absent** from corpus | **negative test** — citation-integrity gate must catch cited id ∉ corpus |
| `unscored_claim` | a claim with no `EvidenceAssessment` entry | must default to `minimal` and flag |

## 5. Expectations (oracle for the tester)
Each `Fixture` ships an `Expectations` block builder 3 checks against:
```
Expectations:
    expect_pass                : bool
    expected_overclaim_claim_ids: list[str]
    expected_orphan_ids        : list[str]      # for fabrication_bait
    min_obligations_satisfied  : int
```
These are best-effort oracles, **not** ground-truth science.

## 6. Determinism & validation
- Same `seed` ⇒ identical `Fixture` (reproducible test runs).
- `validate(fixture)` MUST type-check every field against the main contract and confirm
  `input_contract.required` ({`GrantCall`, `corpus`, `EvidenceAssessment`}) is fully populated and
  internally consistent (claim_id ↔ support_source_ids ↔ corpus) **before** the fixture is handed
  to the agent.
