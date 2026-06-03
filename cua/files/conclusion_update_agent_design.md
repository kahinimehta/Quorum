# Conclusion Update Agent — Work Plan

**Status:** interfaces frozen for v1 · implementation pending · **Owner:** Amy

**Pipeline Role:** The team is building a multi-agent system for autonomous research. This
agent (Conclusion Update Agent) is the pipeline's terminal agent: it turns upstream evidence
into a written NIH proposal plus the tracing (internal-facing) / audit (judge-facing).

---

## 1. Design principles (the architectural decisions this build presents to judges)

These principles are *load-bearing*. Every structural choice below follows from them, and
they are the reason the interfaces in §4 are frozen.

**0. The Conclusion Update Agent itself is a conditioned generator with self-correction,
steerability, and test-time-compute scaling.** It is multi-agent by design to be capable of
self-correction and to allow each
subagent to use a different LLM model with sampling matched to its role — temperature where the
model supports it; the `effort` parameter on Opus 4.x, which doesn't take temperature. The
engine is task-agnostic: this build instantiates it for one `Task` — an NIH grant — with the
NIH rubric as its `Condition` and the Commercial Discovery agent as a `SteeringSource`. The
generic ⇄ concrete vocabulary map is in §2.

- **As a generator:** the agent synthesizes the upstream evidence it receives (the literature
  summary and corpus) and absorbs potential steering forces (additional inputs, e.g. from
  Commercial Discovery) into the proposal's argument, aims (hypotheses), and approach.
- **The conditioning:** the NIH rubric — [NIH Simplified Review
  Framework](https://grants.nih.gov/policy-and-compliance/policy-topics/peer-review/simplifying-review/framework).
- **The self-correction:** the agent is self-correcting by including a reviewer subagent that
  lives in a separate lineage from the writer module.
- **Loops of operation:** the writer lineage drafts against the compiled rubric; the separate
  critic lineage reviews and scores it; the draft is revised until the bar is clear.
- **Test-time compute:** the agent spends more inference compute for better output along two axes —
  *sequential* refinement (the revise loop = self-correction) and *parallel* sampling (best-of-N,
  ranked by a separate Selection Scorer). Quality scales with run-time compute; no weights change.
- **Steering:** goal-level redirects (e.g. "deprioritize Aim 2") enter as input changes from the
  broader system — e.g. from the Commercial Discovery agent — and trigger a re-plan, not an
  in-loop edit. (Interactive live steering is deferred.)
- **Observability:** every run emits three distinct artifacts, never collapsed — the **Proposal**
  (production), a **Trace** (internal: per-subagent calls with model / sampling / I-O / scores,
  for debugging and tuning), and an **Audit** (judge-facing: citation integrity, the
  rubric-obligation ledger, critic scores + calibration, overclaim check). All assembled by a
  codified (deterministic) module, not by a model.

Principles 1–6 are the consequences of principle 0. Each is tagged `[hard]` (guaranteed by
construction) or `[soft]` (measured / best-effort); compound tags mark a principle whose
*structure* is hard but whose *checking* or downstream work is soft — the distinction a judge
should be able to see.

1. `[hard structure · soft check]` **The rubric is compiled, not graded at the end.**
   - *In scope:* compile the Condition (NIH rubric) into a typed `RubricObligation` set at plan
     time and use each obligation three ways — generation constraint, observability hook, audit
     check (the rubric's factors: F1 Importance [Sig+Innov] 1–9, F2 Rigor & Feasibility
     [Approach] 1–9, F3 Expertise & Resources [Inv+Env] sufficiency). The agent exposes satisfied
     obligations + evidence; it never asserts "Factor 1 is strong."
   - *Out of scope:* judging scientific merit (the Critic does that); guaranteeing the
     checkability of vaguely-written obligations.
   - *Depends on:* the Blueprint Planner writing *concrete* obligations — a vague one
     ("Significance is compelling") logs a status no code can verify, so checkability is a
     Blueprint quality bar, not a free guarantee. (Rubric: a fixed external spec, not an agent.)

2. `[hard]` **Generation and judgment never share a role or a context.**
   - *In scope:* exactly one role scores the *rubric* (the Internal Critic), kept in a separate
     lineage and context from the writer and blind to *how* the draft was produced — this is what
     makes the self-eval credible and yields clean preference pairs.
   - *Out of scope:* the Critic checking citation *integrity* — that is the deterministic gate, a
     different kind of judgment.
   - *Depends on:* self-contained — enforced by how the Critic's context is assembled.

3. `[hard]` **Trust-critical logic lives in code, not in a model.**
   - *In scope:* orchestration (loop, stopping rule, intake gate) and the citation-*integrity*
     gate (reference id ∈ corpus) run as deterministic code — a model can't emit an out-of-corpus
     citation or skip the stopping rule if it never owns that decision.
   - *Out of scope:* DOI-resolution and claim↔source support-matching as *guarantees* (separate,
     non-deterministic checks); guaranteeing a real source is used *correctly*. The gate
     guarantees integrity — no fabricated reference — not correct use.
   - *Depends on:* the upstream corpus carrying *stable ids* (Literature Synthesis), or
     id-membership has nothing to check against.

4. `[grounding: hard gate · calibration: soft]` **Claims are grounded *and* calibrated.**
   Grounding is the precondition for calibration — you can't check how strongly a claim may be
   phrased until it is linked to evidence — so the two run as one chained check.
   - *In scope:*
     - **Grounded (does the claim have evidence?):** every empirical/evaluative claim and citation
       binds to an upstream evidence object; the deterministic gate rejects citations outside the
       corpus; a substantive claim with no evidence ref is flagged *here* (once).
     - **Calibrated (is its strength within what that evidence allows?):** a linked claim may
       assert no more than its evidence's ordinal grade permits — measure assertiveness
       independently (hedge-cue lexicon + Haiku@0), map grade → rung on the ladder (strong→causal
       … minimal→exploratory, rounding *down*), flag overclaims. A composite claim that binds to
       no graded `claim_id` takes the **lowest** constituent grade (or `minimal`); that `minimal`
       default only keeps the ladder total — it does not re-flag the unlinked case.
   - *Out of scope:* **grading the evidence** — the skeptic's job; this agent never produces or
     revises a grade. Also: binding connective prose / the hypothesis statement / standard
     methods; perfect claim detection (a classifier — clear cases, not every borderline sentence);
     calibrating to truth (only to the pipeline's grading).
   - *Depends on:* typed, id-bearing evidence with *stable ids* — `corpus` (Literature Synthesis),
     `CommercialLandscape` (Commercial Discovery); and the skeptic emitting an *ordinal* grade per
     `claim_id` with its features, calibrated against expert GRADE labels (its burden, not this
     agent's).

5. `[hard interface · soft tuning]` **Every LLM role is designed to expose the same tuning knob surface.**
   - *In scope:* a uniform `RoleConfig` on every LLM role behind frozen signatures, so changing a
     role's model, sampling, or prompt doesn't change its contract with the others; roles are
     differentiated by model choice + sampling control + prompt-level levers (§5).
   - *Out of scope:* "drop-in swap" — a retuned role can shift its output distribution, prompts may
     need rework, each change needs revalidation. **Weight-level fine-tuning is also out:** LoRA /
     SFT / DPO are not available on Anthropic's Opus or other Claude 4.x models (only Claude 3 Haiku
     on Bedrock), so the `lora_adapter` hook stays parked — see §5.
   - *Depends on:* a validated Critic + the eval (§6) for trustworthy reward, plus
     accumulated Trace data, before any role can actually be tuned.

6. `[hard]` **Closed-world reasoner — the agent reasons over fixed evidence, it never gathers.**
   - *In scope:* draft, ground, critique, and revise over exactly the upstream evidence handed
     in; only Grounding reaches outside, and only to *verify* references (never to gather). This
     is what makes corpus-binding enforceable.
   - *Out of scope:* web search or retrieval in any writer or the Critic; expanding the evidence
     base mid-run — an unsupported claim is hedged/dropped, not resolved by fetching.
   - *Depends on:* upstream agents (Literature Synthesis, Commercial Discovery) to have gathered
     the evidence; this agent's tool-free role surface enforces the boundary by construction.

---

## 2. Architecture: a generic engine, instantiated for NIH grants

### The reusable pattern

This agent is one instantiation of a **task-agnostic engine**: a *conditioned generator with
self-correction and steering* (principle 0). The engine, its roles, and the loop name nothing
domain-specific; everything NIH is injected through a `Task`. Swapping the `Task` retargets the
whole engine to another domain (a spec-driven code generator, a policy memo, a systematic
review) without touching the engine.

Two layers:
- **Engine (reusable):** the roles `Orchestrator · Conditioner · Generator · Grounder · Critic ·
  Reviser`, plus the abstract types `Task · Condition · Obligation · Artifact · SourceSet ·
  SteeringSource`.
- **Task binding (this hackathon):** `NIHGrantTask` supplies the concrete pieces below.

| Generic (in code) | NIH-grant binding |
|---|---|
| `Task` | `NIHGrantTask` |
| `Artifact` — the generated output | `Proposal` |
| `Condition` — what the artifact must satisfy | NIH Simplified Review Framework |
| `Obligation` — a compiled, checkable unit of a `Condition` | `RubricObligation` |
| `dimension` — a scored axis of a `Condition` | `Factor` (F1 / F2 / F3) |
| `SourceSet` / `Source` — the citable evidence set | `corpus` / `Paper` |
| `reference` — a cite into the `SourceSet` | citation |
| `EvidenceScores` — per-claim *ordinal* grade + features | `EvidenceAssessment` (skeptic, GRADE-style) |
| `SteeringSource` — emits input deltas that trigger a re-plan | `CommercialDiscoverySteering` |
| `Conditioner` role — compiles `Condition` → `Obligation[]` | Blueprint Planner |
| `Generator` role — produces the `Artifact` | Argument Synthesizer + Aim Architect |
| `Grounder` role — verifies every `reference` ∈ `SourceSet` | Grounding & Citation |
| `Critic` role — scores `Artifact` against `Obligation[]` | Internal Critic |
| `Reviser` role — applies critique | Reviser |

**Design rule:** the engine code never names *NIH, proposal, factor, aim,* or *citation*. Those
words live only in `NIHGrantTask` and its bindings. A generic role referencing a domain noun is
a leak to fix. The two diagrams below show the **NIH instantiation**; read each concrete name
through the map above for its generic role.

### Pipeline (data flow)

The draft moves top-to-bottom; the loop is the revise cycle. The **Orchestrator [code]** wraps the
whole pipeline — it invokes each role, writes one Trace event per step, owns the *decide*
(stopping rule), and compiles the Audit at exit. It is not a pipeline stage, so it is not drawn
as a box; it surrounds everything below.

```
   UPSTREAM ─ topic · GrantCall · corpus · evidence · subgroups · treatments · commercial
        │
        ▼
   BLUEPRINT PLANNER [LLM]            obligations + budget
        │ generate
        ▼
   ARGUMENT SYNTHESIZER [LLM · F1]  ┐  ×N → Selection Scorer ranks F1 → keep best  (v1)
        │ per aim                   │ Generator (staged)
        ▼                           │
   AIM ARCHITECT [LLM · F2]         ┘  ×N per aim by F2 — when engaged (single-shot in v1)
        │ draft
        ▼
 ┌─▶ GROUNDING & CITATION [code]
 │      │ grounded draft
 │      ▼
 │   INTERNAL CRITIC [LLM]  ◀── external critiques (skeptic, commercial)
 │      │ scores + critiques
 │      ▼
 │   ORCHESTRATOR decides ── pass ──▶ OUTPUTS: Proposal · Trace · Audit
 │      │ revise
 │      ▼
 │   REVISER [LLM] ─┐ new draft
 └──────────────────┘   loop while Critic scores < threshold and round < max
```

**Best-of-N (v1's main optimization).** The Synthesizer samples N skeletons; a lightweight
**Selection Scorer** ranks them on **F1** and the best proceeds. This is a *separate, cheap* judge —
**not** the Internal Critic, which stays at the end scoring the grounded draft on the full rubric to
drive pass/revise — so the Critic's frozen signature is untouched and selection stays cheap. It's
still judgment kept out of the writer's lineage (principle 2); it just isn't the reward/stopping
signal, and its only quality bar is that its top pick survives the Critic. The Aim Architect does
the same per aim on **F2** when engaged; v1 runs it single-shot.

**Composition:** 5 LLM roles + 2 deterministic (code) roles (7 in total — this counts the
Generator's two stages, Synthesizer and Aim Architect, separately; §2 lists it as one generic
role), plus a lightweight **Selection Scorer** used *inside* best-of-N (an auxiliary, not a pipeline
stage — defined in the contract). The deterministic two are the control and trust boundaries
(principle 3). The "in v1" column reflects §5: only the Synthesizer and Critic are actively engaged;
every other LLM role has its knob wired but idle.

| Role | Type | Tunable in v1 | Model | Sampling |
|------|------|---------------|-------|----------|
| Orchestrator | code | not tunable — config sweep | — | — |
| Blueprint Planner | LLM | knob idle in v1 | Haiku 4.5 | temp 0.1 |
| Argument Synthesizer | LLM | **engaged — primary (F1)** | Opus 4.8 | effort xhigh |
| Aim Architect | LLM | knob idle in v1 (F2 when engaged) | Opus 4.8 | effort high |
| Grounding & Citation | code | not tunable — by design | — | — |
| Internal Critic | LLM | **engaged — calibrated to eval** | Opus 4.8 | effort high |
| Reviser | LLM | knob idle in v1 | Sonnet 4.6 | temp 0.25 |

*Opus 4.7/4.8 reject `temperature`/`top_p`/`top_k` (400 error) — those roles use the `effort`
parameter for reasoning depth. Temperature applies only on Sonnet 4.6 / Haiku 4.5.*

---

## 3. Role definitions

Each named role below is the `NIHGrantTask` configuration of a generic engine role (§2): the
**Blueprint Planner** is the `Conditioner`; the **Argument Synthesizer** and **Aim Architect**
are two stages of the `Generator`; **Grounding & Citation** is the `Grounder`; the **Internal
Critic** is the `Critic`; the **Reviser** and **Orchestrator** keep their generic names. Tuning
or re-binding a role swaps its internals behind the frozen signature in §4.

### ORCHESTRATOR — `[code]`
- **Input:** full `ResearchState`, `RunConfig` (max_rounds, per-factor score threshold).
- **Output:** final state + the three artifacts; owns the generate→critique→revise loop and
  the intake/degradation gate.
- **Gradable / v1:** no — code role; the stopping threshold is a hyperparameter you *sweep*,
  not a model you finetune.
- **Model + sampling:** none. *Why:* the loop and precondition checks must be deterministic and
  inspectable; orchestration inside an LLM is where agent systems go flaky and unauditable.
- **Tuning knobs:** `max_rounds`, `factor_thresholds`, degradation policy (config, not weights).

### BLUEPRINT PLANNER — `[LLM, light]`
- **Input:** `GrantCall` (+ topic).
- **Output:** `RubricObligation[]` + section/word `Budget` — the rubric compiled into typed
  constraints.
- **Gradable / v1:** gradable later (SFT-able if obligations come out generic); **v1: knob idle.**
  The NIH obligation skeleton is templated and only the topic-specific specialization is
  generated, so v1 leans near-deterministic.
- **Model + sampling:** Haiku 4.5, temperature 0.1 (→ Sonnet 4.6 if obligations are shallow). *Why:*
  structured instantiation of a known template — cheap/fast; low temp keeps the obligation
  set stable so traces and audits stay comparable across runs.

### ARGUMENT SYNTHESIZER — `[LLM, heavy]` — primary tuning target
- **Input:** obligations, `LiteratureSynthesis`, `subgroups`, `treatments`,
  `EvidenceAssessment`, `commercial.grant_contribution`.
- **Output:** gap → central hypothesis → aim skeleton + Significance/Innovation prose; every
  claim tagged `serves_dimension` + `evidence_ids`. This is where "the conclusion" forms.
- **Gradable / v1:** gradable on Factor 1; **v1: engaged — primary tuning target**
  (inference-time best-of-N; logs (chosen, rejected) pairs for future fine-tuning — see §5 on availability).
- **Model + sampling:** Opus 4.8, effort `xhigh` (Opus rejects temperature). *Why:* hardest
  reasoning step (defensible novel-but-grounded framing) → best model at max thinking depth.
  Candidate diversity for best-of-N comes from sampling N times per state (adaptive sampling
  varies run to run), not a temperature dial.

### AIM ARCHITECT — `[LLM, heavy]`
- **Input:** one aim stub + central hypothesis + corpus + evidence.
- **Output:** rationale, approach, expected outcomes, explicit pitfalls/alternatives
  paragraph, with `citation_ids`.
- **Gradable / v1:** gradable on Factor 2 (rigor & feasibility) — a separate axis from the
  Synthesizer (cleaner reward attribution); **v1: knob idle** (engaged later).
- **Model + sampling:** Opus 4.8, effort `high` (Sonnet 4.6 — which still takes a low temperature
  — if cost/latency headroom is needed). *Why:* methods should be conservative and standard;
  rigor rewards precision over flourish → less reasoning budget than the Synthesizer.

### GROUNDING & CITATION — `[code]` (optional Haiku sub-check)
- **Input:** assembled draft + `corpus`. *(Amendment 2026-06-02: the assembled `Proposal` envelope is
  structurally validated **before** this gate — a malformed artifact never reaches grounding; local +
  deterministic, structure only, semantics stay with §3. See contracts.md §2.1.)*
- **Output:** grounded draft + `GroundingReport` (every cited id ∈ corpus, DOI-resolution
  rate, orphan list).
- **Gradable / v1:** no — code role, by design; the trust guarantee is enforced in code, not
  by a model that could be coaxed into hallucinating a reference.
- **Model + sampling:** none. An optional Haiku 4.5 @ 0.0 can do fuzzy claim↔paper *support*
  matching, but the pass/fail gate stays deterministic. *Why:* credibility comes from a check
  that literally cannot fabricate.

### INTERNAL CRITIC — `[LLM, heavy]` — the reward engine
- **Input:** the *finished, grounded* draft + obligations (`requirement` + `evidence_ids` only —
  **not** the writer's `self_score`) + evidence + external critiques. **Not** the writer's
  reasoning trace.
- **Output:** `CritiqueReport` — whole-draft `dimension_scores` (per factor, 1–9) **and**
  per-segment `segment_scores` (e.g. F2 per aim, feeding the Aim Architect's reward), with
  justifications tied to text spans + evidence ids, and a revise/pass signal.
- **Gradable / v1:** special — calibrated to *agree with the blinded external eval*; **v1:
  engaged.** Its scores become the process reward for the writer roles, measured by calibration
  MAE / rank correlation against the eval (§6).
- **Model + sampling:** Opus 4.8, effort `high` (Opus rejects temperature, so the old "temp 0 for
  reproducible scores" is no longer available). *Why:* a weak critic gives a biased reward, so it
  must be ≥ the writer in capability. Score stability comes from a fixed prompt + structured
  outputs (and, if needed, averaging N passes or using the second-critic disagreement flag), not a
  temperature of 0. Decorrelation from the writer comes from blind context, not a weaker model.
  *Optional:* a second critic on Opus 4.7 — disagreement becomes an uncertainty flag for human review.

### REVISER — `[LLM, mid]`
- **Input:** prior draft + critic critiques + external critiques + the specific obligations
  flagged unsatisfied.
- **Output:** a targeted edit (next draft), then re-routed through Grounding.
- **Gradable / v1:** gradable (reward = *delta* in Critic dimension scores round-over-round —
  did the edit help); **v1: knob idle** (engaged later).
- **Model + sampling:** Sonnet 4.6, temperature 0.25 (Sonnet accepts temperature; on Opus 4.8
  you'd drop temp and use low effort instead). *Why:* edits must be surgical — preserve
  what passed, change only what was flagged. Low temp prevents rewriting working sections;
  a mid-tier model suffices for constrained edits.

---

## 4. Contracts (frozen)

The executable specs live in their own files — single source of truth; code agents implement
against them, this plan is the surrounding context. Changing any signature needs team sign-off.

- **`conclusion_update_agent_contracts.md`** — the **main agent** (builder 1). Generic engine
  types + `NIHGrantTask` bindings, the six role signatures, `RoleConfig`, `CritiqueReport`,
  `Trace`/`Audit`, the loop/stopping rule, and the calibration/overclaim rule. Also carries the
  two open cross-team binding decisions (`Paper.resolvable_id` type; ordinal `EvidenceScores.grade`).
- **`conclusion_update_agent_test_data_contract.md`** — **stand-in upstream data** (builder 2).
  How to generate best-effort realistic fixtures (`GrantCall`, `corpus`, `EvidenceAssessment`,
  `subgroups`, `treatments`, `commercial`) that satisfy the main contract's input contract, so the
  agent runs and is testable before the real upstream agents exist. Fixtures, not real agents.
- **`conclusion_update_agent_test_review_contract.md`** — **dev-time tester + reviewer**
  (builder 3). The hard invariants (offline), the eval harness (RePORTER comparison, blinded
  judge, critic calibration, competitiveness), and the review report. Read-only over the agent's
  `Proposal`/`Trace`/`Audit`; runs outside the agent loop.
- **`conclusion_update_agent_nih_obligations.md`** — *companion to the main contract.* The
  first-pass NIH `RubricObligation` set the Blueprint Planner emits (the Simplified Review Framework
  compiled into concrete, checkable obligations per F1/F2/F3).

---

## 5. Tuning surface (the same knobs on every LLM role)

Every LLM role is built from the same `RoleConfig` behind a frozen signature, so a role can be
changed without touching its callers. Roles are differentiated three ways, in order of how much v1
leans on each:

1. **Model choice** — the biggest lever: Haiku 4.5 for cheap templated work (Blueprint), Opus 4.8
   for the hard reasoning (Synthesizer, Aim Architect, Critic), Sonnet 4.6 for constrained edits
   (Reviser).
2. **Sampling control** — *model-dependent*: `temperature` on the models that accept it (Sonnet 4.6,
   Haiku 4.5), and the **`effort`** parameter on Opus 4.x, which rejects temperature and uses
   adaptive thinking depth instead. Same intent (how hard / how varied the generation is), two
   different dials depending on the model.
3. **Prompt-level** — `system_prompt_template` on every role; `few_shot_exemplars` on the two
   writer roles only (Synthesizer, Aim Architect).

```
RoleConfig:
    model_id     : str                              # which model
    temperature  : float | None                     # Sonnet/Haiku only; None on Opus 4.x
    effort       : low|medium|high|xhigh|max | None  # Opus reasoning depth (temp analog)
    system_prompt_template : str                    # role instructions + obligations
    few_shot_exemplars     : list                   # writer roles only
    n_samples    : int                              # >1 = best-of-N at inference
    reward_source: list[dimension]                  # dimension(s) this stage is scored on
    lora_adapter : path | None                      # weight-FT hook; parked (None)
    log_pairs    : bool                             # log best-of-N pairs for future FT
```

**Prompt-level.** Every role gets a tuned `system_prompt_template`. `few_shot_exemplars` go on the
two **writer** roles only — Synthesizer and Aim Architect — drawn from approved, funded proposals,
which *are* examples of their output (a funded Significance/Innovation for the Synthesizer, funded
Aims for the Aim Architect). Since we have the polished text but not the evidence base that produced
it, these are **structural exemplars** (form and voice), not input→output pairs — kept **disjoint
from the eval reference set** and abstracted toward skeletons rather than pasted verbatim, so the
agent imitates structure without copying funded grants (builder-3 contamination rule). **Blueprint
and Reviser run system-prompt-only** — their output (obligations, edits) isn't what a proposal
demonstrates. The **Critic's 1–9 calibration anchors are a separate, deferred artifact**: scored
drafts spanning the range (hand-scored, or from the builder-3 blinded judge), not approved proposals
— which only show the high end and carry no score.

**Weight-level fine-tuning is parked — not available on these models.** LoRA / SFT / DPO are not
offered for Anthropic's Opus or other Claude 4.x models (only Claude 3 Haiku on Bedrock, too weak
for these roles), so `lora_adapter` stays `None` and no live weight update happens. What v1 does
*instead* is **inference-time best-of-N**: sample `n_samples` candidates and keep the one a
lightweight **Selection Scorer** ranks highest — a separate, cheap judge (not the Critic; §2). The
"v1 engaged" roles (Synthesizer, Critic) are the ones wired for this loop; the
rest run single-shot. (The "engaged/idle" labels in §2–§3 refer to this best-of-N + reward wiring —
prompt-level few-shot is on everywhere.)

**What gets ranked in best-of-N — the unit matches the stage's `map_over`.** The Selection Scorer
ranks candidates at each writer stage:

- **ArgumentSynthesizer** (`map_over = None`): sample N skeletons per state, keep the best by **F1**.
- **AimArchitect** (`map_over = aim_stubs`): sample N expansions *per aim*, keep the best by that
  aim's **F2** — finer signal than draft-level.

The Internal Critic is separate: it scores the *grounded* draft on the full rubric for pass/revise
and the audit, and its per-aim `segment_scores` give the validated per-aim quality (for the audit
now; the per-aim training reward if fine-tuning ever lands). The Selection Scorer is the fast proxy
that *picks*; the Critic is the validated judge that *measures*.

Best-of-N produces (chosen, rejected) pairs as a byproduct; with `log_pairs` on, they're recorded
per obligation (rubric-aligned). Logging changes nothing in the current run — the pairs are purely
the dataset if/when weight fine-tuning becomes available, at which point the recipe is LoRA + low LR
+ mixed-in general instruction data, to avoid eroding base reasoning (the catastrophic-forgetting
tradeoff).

---

## 6. Execution plan (sessions)

The build is **8 sessions across three builders + an operator**, governed by the three frozen
contracts (§4). Fixtures come first, so the agent is runnable before any real upstream agent exists;
the offline tests and the eval are folded in as their own sessions rather than a separate workstream.

**S0 · Prerequisite** (operator + team, not a build session). Freeze the three contracts; resolve the
two open binding decisions — `Paper.resolvable_id` type and ordinal `EvidenceScores.grade` — with the
upstream owners, or stub them in the test-data contract for now.

1. **S1 · Fixtures** — *builder 2*, `test_data_contract.md`. The five `Fixture` scenarios
   (`clean_high_grade`, `thin_corpus`, `low_grade_bait`, `fabrication_bait`, `unscored_claim`) +
   `validate()`. Standalone; unblocks everyone.
2. **S2 · Agent skeleton** — *builder 1*, `contracts.md` §1.3–1.6, §1.11. Orchestrator loop +
   deterministic Grounding/Citation, end-to-end on fixtures with LLM roles stubbed; emits
   Proposal/Trace/Audit. *Depends on S1.*
3. **S3 · Offline invariants** — *builder 3*, `test_review_contract.md` part A. The three hard
   invariants + each fixture's `Expectations`. *Depends on S1; develops in parallel with S2.*
4. **S4 · Writer roles** — *builder 1*, `contracts.md` §1.5–1.6, §2.2. Blueprint Planner, Argument
   Synthesizer, Aim Architect, and the Selection Scorer (best-of-N for the Synthesizer; `log_pairs`
   on). *Depends on S2.*
5. **S5 · Critic + Reviser** — *builder 1*, `contracts.md` §1.5, §1.7. Closes the revise loop.
   *Depends on S4.*
6. **S6 · Integrate & iterate** — *operator*. Run the agent on all fixtures → S3 invariants → fix
   until green across every scenario (the `fabrication_bait` / `low_grade_bait` negatives must
   fail-as-expected first, then pass). May span several passes. *Depends on S5 + S3.*
7. **S7 · Eval & calibration** — *builder 3*, `test_review_contract.md` part B. RePORTER reference
   set, blinded judge, **critic calibration** (MAE / rank-corr). This is the single coupling point:
   the eval's scores are the ground truth the Critic is calibrated against — which is what licenses
   the Critic as a trustworthy reward / measurement signal. *Depends on a running agent (S5).*
8. **S8 · Competitiveness & review** — *builder 3*, `test_review_contract.md` part B–C. AI vs matched
   funded human grants; the `ReviewReport` go/no-go. *Depends on S7.*

**Concurrency.** S1 first, unblocks all; S2 and S3 run in parallel once fixtures exist; S4→S5 are
sequential (builder 1); S7–S8 wait on a running agent (after S5). Weight fine-tuning is **not** a
session — parked, not available on these models (§5).

**Allowed v1 simplification.** No roles fuse. If time collapses, leave Blueprint near-deterministic
(templated obligations). **Never** fuse the Critic into a writer — that collapse destroys the
credibility story (principle 2).

### Gaps — work without an explicit spec yet

Needed by the sessions above but not pinned in any contract; flagged so they're assigned, not
discovered mid-build:

- **Upstream type shapes** (S1) — `GrantCall`, `subgroups`, `treatments`, `CommercialLandscape`
  aren't pinned by their owners. Builder 2 defines minimal stand-in shapes and flags them; the
  *real* upstream output contracts are owned by teammates and still missing.
- **NIH obligation set** (S4, Blueprint) — first-pass set authored in
  `conclusion_update_agent_nih_obligations.md` (the NIH rubric → concrete, checkable
  `RubricObligation`s). Remaining: topic specialization at plan time and the Critic's scoring rubric
  for the qualitative (`critic`) rows. This is the heart of principle 1.
- **Selection Scorer scoring prompt** (S4) — its signature is frozen, but how it scores F1/F2 on a
  fragment (its rubric/prompt) is unspecified.
- **Overclaim `level()` classifier** (S2/S4) — the assertiveness rule is specified (contract §1.12),
  but the hedge-cue lexicon + Haiku@0 classifier that *measures* level isn't built or specced.
- **Critic calibration anchors** (S5/S7) — the deferred "scored drafts spanning the 1–9 range"
  artifact (§5); how and when it's produced isn't specified, and it gates S7.
- **Few-shot exemplar curation** (S4) — approved proposals must be abstracted to structure and kept
  disjoint from the eval reference set; the curation process and its owner aren't a contract.
- **Eval methodology** (S7) — RePORTER "same-domain / matched" sampling criteria and the
  blinded-judge scoring prompt aren't specified.
- **Stopping thresholds** (S6) — `RunConfig.dimension_thresholds` values are unset. These are sweep
  hyperparameters (TBD is acceptable), but someone picks the starting bar.

## 7. v1.0 as-built — the data pipeline (Ingestion Layer) + its tuning surface

> Added post-freeze (2026-06-03, owner-authorized) to record what v1.0 actually ships. §1–6 are the original
> pre-build design; this section documents the as-built additions — chiefly the corpus **data pipeline** and its
> **tuning surface**. Ratified in `build/decisions/2026-06-02-ingestion-layer-rank-and-bound.md` +
> `…-ingestion-keyfinding-clustering-amendment.md`.

### The Ingestion Layer (`cua/nih/ingestion.py` — binding-side, rule-based, deterministic)
Between the read-only upstream adapter and the agent loop, v1.0 inserts a deterministic **rank-and-bound** corpus
intake — **NOT retrieval** (upstream already retrieved); it reranks-and-bounds the in-hand corpus.
Pipeline: `cluster-by-key_finding → relevance-score → diversity-bounded top-K → writer view`.

*Why:* at full scale (~400 papers) a single writer call serializing every finding exceeds its output budget
(truncation + the 10-min non-streaming wall). The bound hands the writer a diversified top-K — representatives +
corroboration counts — that is denser and breadth-preserving. **Closed-world (principle 6) intact:** this is
pre-loop reorganization of the *fixed* corpus, not gathering.

*Guarantees (ratified):* **ID-PRESERVING** — clustering shapes the writer's VIEW only; the *full* corpus stays the
citation gate's referent, so **inv-1 is unchanged** (cited ⊆ full corpus). **COUNT ≠ GRADE** — a cluster's
corroboration `count` is an integer; the skeptic grades, ingestion counts (never bucket a count into a grade).
**CONTRADICTION-MERGE is mitigated, not solved** — corroborators are retained; a `possible_contradiction`
mixed-polarity flag is the real safety net; the negation penalty is cheap *partial* mitigation. The bound, the
cluster selection, and any swallowed contradiction are emitted to `<run>.ingestion.json` — **the honesty
mechanism while grades are flat** (it makes a one-sided selection or a merged contradiction visible, not silent).

### The corpus data reality (what actually reaches the agent)
Verified against the adapter + the upstream schema: each corpus `Paper` carries only bibliographic fields +
`key_finding` text + `source_type` (literature/trial/grant). **Per-paper subgroup/mechanism/treatment tags and
per-paper grades do NOT reach the agent** — the upstream Subgroup / Treatment / Evidence-Scoring agents
(NeuroDiscover Agents 2–4) are unbuilt (only Agent 1, Literature Synthesis, is agentic; subgroups/connections
exist only as seeded demo rows, and the connection-keyed tables are empty). Consequence: evidence grades are
empty → all `minimal` (an uncalibrated surrogate, decision B) → the overclaim ladder permits only L1 — **the
ungraded-evidence ceiling**, the standing inv-3 residual. The Ingestion Layer's diversity axis is therefore
`key_finding` clustering (a *findings* axis, not a stance/grade axis); a real anti-confirmation guardrail awaits
the skeptic (Agent 4).

### Tuning surface — `IngestionConfig` (complements §5's `RoleConfig`)
The Ingestion Layer is a deterministic *stage*, not an LLM role, so its knobs are a **binding-side
`IngestionConfig`** — **NOT** §5 `RoleConfig` (which is LLM-scoped: model/temperature/effort/n_samples):
`top_k`, `cluster_similarity_threshold`, `per_cluster_cap`, `polarity_aware`. The grade key is a documented
**extension point** — inert until a real per-*source* skeptic grade exists, then it becomes the primary rank key.

### Live demo (`outputs/full2.*`)
The full pipeline runs live on the real 400-paper corpus: ingestion **400 → 60** (382 clusters, 0
`possible_contradiction`), all six roles + best-of-N + **2 revise rounds**; **inv-1 PASS** (16 real cites, 0
fabrication), **inv-2 PASS**, **inv-3 = 1 honest flag** (`aim-2::hypothesis` L3 vs permitted L1 = the
ungraded-evidence ceiling). Writer `max_tokens` is 16384 on the bounded view (under the streaming ceiling that
tripped the unbounded run). A self-contained visual report of the run ships at `outputs/full2.html`.