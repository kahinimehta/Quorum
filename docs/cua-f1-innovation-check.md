# How CUA Checks Innovation in F1

**NeuroDiscover / Quorum — Grant Proposal Tab (Step 3)**  
**Audience:** Dashboard users and CUA developers  
**Demo reference:** bundled `graded6` static report

---

## Overview

Tab 3 (**Grant Proposal**) shows output from the **CUA** (Conclusion Update Agent) package — a multi-agent pipeline that writes an NIH R01 proposal from the evidence corpus. One part of NIH review is **Factor 1 (F1)**: *Should this project be done?* F1 combines **Significance**, **Innovation**, and the **central hypothesis**.

Innovation is **not** a separate dashboard KPI. It is enforced through obligation **F1-3** in *the contract* and contributes to the aggregate **Critic F1** score (1–9) shown in Tab 3’s “Run at a glance” strip.

---

## NIH framing: F1 vs F2 vs F3

| Factor | Question | Innovation’s role |
|--------|----------|-------------------|
| **F1** | Should it be done? | **Innovation (F1-3)** — what is *new* vs current practice |
| **F2** | Can it be done rigorously? | Aim methods, pitfalls, outcomes (not innovation) |
| **F3** | Can this team do it here? | Expertise/resources surfaced per aim |

F1 and F2 are scored **1–9** by the Internal Critic. The revise loop typically requires F1 ≥ 5 and F2 ≥ 5 before stopping (or max rounds).

---

## The contract: obligation F1-3

Before drafting, the **Blueprint Planner** compiles ~21 checkable obligations from the NIH Simplified Review Framework. Innovation is **F1-3**:

> **F1-3:** Innovation names the **specific departure** from current concepts, methods, or practice — **not** a generic “novel”.

For Parkinson’s (`graded6`), the requirement is specialized further, e.g. naming a novel target, assay, biomarker, or therapeutic mechanism — not vague “innovative” language.

**Satisfied by:** the proposal section bound to claim id `innovation`.

**Check type:** **critic** (qualitative) — structural presence is also verified in code.

Related F1 obligations:

| ID | What it checks |
|----|----------------|
| **F1-1** | Significance — specific barrier + ≥1 corpus citation |
| **F1-2** | One explicit central hypothesis following from the gap |
| **F1-3** | Innovation — specific departure, not generic novelty |

Cross-cutting rules (**X-1**, **X-2**) apply to innovation claims too: every cite must exist in the corpus; assertiveness cannot exceed evidence grade.

---

## Four layers of checking

### Layer 1 — Writer (Synthesizer)

The **Argument Synthesizer** must emit a structured `innovation` field alongside gap, significance, and central hypothesis. The live prompt instructs:

- *“Innovation: the specific departure from current concepts/methods/practice (not a generic ‘novel’).”*

If the `innovation` field is missing, validation fails and the candidate is rejected before ranking.

Innovation is a **framing** claim: it is phrased at the assertiveness permitted by its evidence grade and must still cite real corpus ids only.

### Layer 2 — Code (ledger / invariants)

After drafting, `mark_ledger()` binds **F1-3 → claim `innovation`**:

| Check | Pass | Fail |
|-------|------|------|
| Claim present | `satisfied_by: ["innovation"]` | `at_risk` |
| ≥1 evidence_id (inv-2) | `status: satisfied` | downgraded to `at_risk` |
| Citations in corpus (inv-1) | Grounder PASS | orphans dropped; revise |
| No overclaim (inv-3) | clean | hedge directive; F1 penalty |

**Important:** Code verifies that innovation **exists and is cited**. It does **not** judge whether the departure is scientifically compelling — that is the Critic’s job.

### Layer 3 — Best-of-N (Selection Scorer)

At the opening, the Synthesizer writes **N independent F1 pitches** (four in `graded6`). The **Selection Scorer** ranks them on **F1 as a whole** (significance + hypothesis + innovation together):

- Rewards grounded, specific F1 coverage
- Penalizes vague phrasing and overclaim
- Picks one winner; losers appear under **Explored & dropped** in Tab 3

This is a **fast picker**, not the final judge. The Internal Critic measures quality later.

### Layer 4 — Internal Critic (quality judgment)

The **Internal Critic** (Opus, blind to writer self-scores) is the authoritative innovation quality check:

1. Reads obligation **F1-3** requirement text
2. Reads the grounded `innovation` claim and its citations
3. Scores **F1 (1–9)** for Significance **and** Innovation together
4. May add **`F1-3`** to `flagged_obligation_ids` if innovation is generic or unmet
5. Applies code penalties on F1 for missing targets, overclaims, or orphan citations

**Stopping rule:** F1 and F2 must meet dimension thresholds (default ≥ 5). In `graded6`, final scores are **F1 = 7**, **F2 = 5**, **F3 = 6**.

---

## What passes vs fails (examples)

### Fails F1-3 (qualitative)

- “This project is novel and innovative.”
- Restating the central hypothesis without a distinct departure
- Innovation that duplicates significance (“unmet need in PD…”) without naming *what is new*

### Passes F1-3 (graded6 pattern)

- Names a **specific departure**: biomarker-stratified enrollment, lysosome-directed intervention in a GBA-stratified cohort, unified GBA / α-syn / gut-axis framework
- **Corpus-backed** citations (PMIDs, grant ids from the evidence store)
- Clearly distinct from significance (why it matters) and from F2 aim methods (how you will do it)

---

## Where to see this in Dashboard Tab 3

| UI component | Innovation-related content |
|--------------|----------------------------|
| **Critic F1** KPI | Aggregate F1 score (includes innovation), shown as `n/9` |
| **Report toolbar** | `17/21 obligations satisfied` (example from `graded6`) |
| **The proposal** | Innovation section in NIH text (always visible) |
| **The contract** | Full F1-3 requirement |
| **Explored & dropped** | Selection Scorer rationale comparing candidates’ F1 (incl. innovation) |
| **The loop, round by round** | F1 scores per revise round |
| **Audit → obligation ledger** | F1-3 row: status, citations, `notes: critic` |

Tab 3 is **static** (`graded6`) and not tied to Step 1/2 `run_id`. Live runs: `python -m cua.nih.run_db` (see Tab 3 CLI block).

---

## Data flow (summary)

```
Blueprint Planner → F1-3 obligation in contract
       ↓
Synthesizer ×N → innovation claim (required field)
       ↓
Selection Scorer → ranks F1 (incl. innovation) → one winner
       ↓
Aim Architect → three aims
       ↓
Grounder → citation integrity (inv-1)
       ↓
Internal Critic → F1 score + flag F1-3 if generic/unmet
       ↓
Reviser (+ optional F2 Booster) → revise until thresholds met
       ↓
Audit ledger → F1-3 satisfied / at_risk → Tab 3 report
```

---

## Key takeaway

**Innovation in F1 is checked by obligation F1-3:** the writer must produce a cited `innovation` claim naming a *specific* departure; code ensures it exists and is grounded; the **Internal Critic** judges whether it is specific enough (not generic “novel”); the result rolls into **Critic F1**, not a separate innovation score.

**Sources in repo:** `cua/files/conclusion_update_agent_nih_obligations.md`, `cua/src/cua/nih/obligations.py`, `cua/src/cua/roles/synthesizer.py`, `cua/src/cua/roles/critic.py`, `docs/dashboard.md` (Step 3 report structure).
