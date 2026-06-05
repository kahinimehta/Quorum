# Conclusion Update Agent — Contracts (executable spec)

**This file is the source of truth for interfaces.** Code agents implement against it. The
*work plan* (`conclusion_update_agent_design.md`) holds the rationale, principles, and context —
read it for *why*, read this for *what*. Changing any signature here needs team sign-off; it
ripples across role owners.

**Conventions.** Pseudo-schema, not a language. `?` = optional. `Grade`/`level` types are
*ordinal* (ordered, not numeric). `map K -> V` = keyed lookup. `model_id` values are Anthropic
API strings. Two tiers below: **generic engine** (task-agnostic) and the **NIH-grant binding**.

---

## 1. Generic engine (task-agnostic)

### 1.1 Value types
```
Source         : { id, metadata, resolvable_id? }       # resolvable_id is binding-specific (DOI|PMID)
SourceSet      : { sources: list[Source] }
Grade          : ordinal { strong > moderate > weak > minimal }   # evidence strength — NOT a probability
EvidenceScores : map claim_id -> { grade: Grade, evidence_features, support_source_ids[], caveats }
InputDelta     : { target: ref, change }                # a mutation to a Task input
SectionSpec    : { name, serves_dimension, target_words }
Budget         : { sections: map name -> word_limit, total_word_limit }
RunConfig      : { max_rounds: int, dimension_thresholds: map dimension -> int }
```

### 1.2 Condition & obligations
```
Condition (abstract):
    compile(task) -> (list[Obligation], Budget)

Obligation:
    id           : str
    dimension    : str                            # a scored axis of the Condition
    requirement  : str                            # CONCRETE, checkable predicate (countable / presence / structural)
    satisfied_by : list[ref]                      # section/segment ids that fulfill it
    evidence_ids : list[str]                      # Source ids / EvidenceScores keys backing it
    self_score   : int | {sufficient, insufficient}   # writer's self-assessment
    status       : {unsatisfied, at_risk, satisfied}

ObligationPublic = Obligation MINUS { self_score, notes }   # the view passed to the Critic (see 1.5)
```

### 1.3 Task
```
Task (abstract):
    artifact_type    : type                       # what the Generator produces
    condition        : Condition
    input_contract   : { required: list[slot], optional: list[slot] }
    sections         : list[SectionSpec]
    source_set       : SourceSet
    generator        : list[GenerationStage]      # the staged writer pipeline (1.6)
    steering_sources : list[SteeringSource]
```

### 1.4 Drafts
```
DraftFragment : partial artifact content emitted by one GenerationStage
Draft         : artifact-in-progress (sections + segments), pre-grounding
GroundedDraft : Draft after the Grounder binds references; carries a GroundingReport
Artifact      : the finished, grounded deliverable (binding defines the concrete type)
```

### 1.5 Role signatures
```
Orchestrator [code]     : (Task, RunConfig) -> (Artifact, Trace, Audit)
Conditioner  [LLM]      : (Task) -> (list[Obligation], Budget)
Generator    [code+LLM] : (obligations, task.inputs) -> Draft          # drives task.generator (1.6)
Grounder     [code]     : (Draft, SourceSet) -> (GroundedDraft, GroundingReport)
Critic       [LLM]      : (GroundedDraft, list[ObligationPublic], EvidenceScores, external_critiques) -> CritiqueReport
Reviser      [LLM]      : (prior_draft, CritiqueReport, external_critiques, flagged_obligations) -> Draft
SelectionScorer [LLM, light] : (candidates: list[DraftFragment], dimension) -> list[{ fragment, score }]
```
- **Critic receives `ObligationPublic`** (no `self_score`/`notes`) — required for scoring independence.
- `external_critiques` enter via the Orchestrator as inputs (skeptic, commercial). Never tool calls.
- **`SelectionScorer`** ranks best-of-N candidates inside a `GenerationStage` (1.6) on a single
  dimension, **pre-grounding**. It is a *cheap, separate* judge — **not** the Critic, and **not** an
  eval-calibrated reward signal. Its only quality bar: its top pick should survive the Critic. Kept
  out of the writer's lineage (principle 2).

### 1.6 Generator (staged pipeline)
```
GenerationStage (abstract):
    name     : str
    config   : RoleConfig                         # 1.8
    map_over : ref | None                         # None => run once; else run once per item at this ref in draft-so-far
    produce(obligations, inputs, draft_so_far [, item]) -> DraftFragment

# A deterministic code driver runs stages in order, fans out where map_over is set, and merges
# each DraftFragment into the Draft. Only produce() is an LLM call.
# Best-of-N: when config.n_samples > 1, the driver calls produce() N times and keeps the candidate
# the SelectionScorer (1.5) ranks highest on the stage's reward dimension — pre-grounding, cheap.
```

### 1.7 Critic output
```
CritiqueReport:
    dimension_scores    : map dimension -> { score, justification, spans[] }     # whole-draft; drives stopping rule
    segment_scores      : map segment_ref -> { dimension, score, justification }  # per fan-out item; validated per-aim quality (audit; future per-stage reward)
    decision            : pass | revise
    flagged_obligations : list[obligation_id]
```

### 1.8 Tuning surface (every LLM role/stage carries one)
```
RoleConfig:
    model_id              : str                   # Anthropic API string; the primary lever
    temperature           : float | None          # ONLY where the model accepts it (Sonnet 4.6, Haiku 4.5); None on Opus 4.7/4.8 (else 400)
    effort                : low|medium|high|xhigh|max | None  # Opus 4.x reasoning depth; the Opus analog to temperature
    system_prompt_template: str                   # obligations injected here
    few_shot_exemplars    : list                  # structural exemplars; WRITER roles only (Synthesizer, Aim Architect); ON in v1
    n_samples             : int                   # >1 => best-of-N at inference (SelectionScorer ranks, keep best); no weight change
    reward_source         : list[dimension]       # dimension(s) this stage is scored on — SelectionScorer ranks by it; Critic measures it
    lora_adapter          : path | None           # weight-level FT hook — NOT available on Opus/Claude 4.x (only Claude 3 Haiku/Bedrock); parked, None
    log_pairs             : bool                  # log (chosen, rejected) best-of-N pairs as future-FT data; no effect on the current run
```

### 1.9 Steering
```
SteeringSource (abstract): poll() -> InputDelta | None
# Consumed at PLAN time: an InputDelta mutates Task inputs and triggers a re-Condition (new run).
# Never an in-loop edit of obligations.
```

### 1.10 Trace & Audit
```
TraceEvent : { round, role, model, sampling, input_refs[], output_ref, tokens, ts, decision }
Trace      : list[TraceEvent]                     # one event per role call (JSONL)

Audit:
    grounding_report : GroundingReport
    obligation_ledger: list[Obligation]           # FULL obligations (with self_score, status)
    calibration      : { internal_scores, external_scores?, mae?, rank_corr? }
    overclaim_check  : list[{ claim, claim_level, evidence_grade, permitted_level, ok }]
    unit_tests       : list[{ name, passed, detail }]

GroundingReport:
    n_references      : int
    all_in_source_set : bool                      # HARD gate: every cited id ∈ SourceSet
    orphan_ids        : list[str]                 # cited ids NOT in SourceSet (fabrications); must be empty to pass
    resolve_rate      : float?                    # optional: fraction of resolvable_ids that resolve
```

### 1.11 Loop & stopping rule (Orchestrator)
```
# round: Conditioner (once) -> Generator -> Grounder -> Critic -> decide
decide = pass  IFF  GroundingReport.all_in_source_set
                AND  for every gated dimension: dimension_scores[dim].score >= RunConfig.dimension_thresholds[dim]
         else revise: Reviser -> re-Ground -> Critic ...   while round < RunConfig.max_rounds
```

### 1.12 Calibration / overclaim rule (behavioral contract)
```
level(claim) ∈ { L4 causal, L3 associative, L2 suggestive, L1 exploratory }   # MEASURED independently: hedge-cue lexicon + Haiku@0
permitted(grade): strong→L4, moderate→L3, weak→L2, minimal→L1                  # round DOWN on ties
overclaim ⇔ level(claim) > permitted(grade(claim))                            # => recorded in Audit.overclaim_check (flag, not gate)

# - Every empirical claim carries an evidence id. Unlinked => grade `minimal` and flagged (grounding clause; not re-flagged here).
# - Composite claim binding to no single graded claim_id => LOWEST constituent grade (or `minimal`). Binding fallback, NOT grading.
# - Ownership: the skeptic agent GRADES; this agent only ENFORCES (measure level -> map -> flag). It never produces/revises a Grade.
```

---

## 2. NIH-grant binding (`NIHGrantTask`)

### 2.1 Condition, artifact, evidence
```
NIHReviewFramework(Condition):
    dimensions = { F1 = Significance+Innovation, F2 = Approach, F3 = Investigator+Environment }
    F1, F2 -> score 1..9   ;   F3 -> {sufficient, insufficient}
RubricObligation = Obligation   with dimension ∈ {F1, F2, F3}   # first-pass set: conclusion_update_agent_nih_obligations.md

Paper = Source : { id, authors, year, title, venue, resolvable_id = DOI|PMID, key_finding }
corpus         = SourceSet of Paper
EvidenceAssessment = EvidenceScores   # from the skeptic; Grade ↔ GRADE: strong=high, moderate, weak=low, minimal=very-low

ProposalSection : { name, serves_dimension, evidence_ids[], text }
ExpandedAim     : { id, hypothesis, rationale, approach, expected_outcomes, pitfalls_alternatives, citation_ids[] }
Proposal(Artifact):
    project_title, central_hypothesis
    sections      : list[ProposalSection]
    aims          : list[ExpandedAim]
    references    : list[Paper]                   # citation deck; EVERY ref ∈ corpus
    obligations   : list[RubricObligation]        # the ledger, embedded
    revision_round: int
```

**Structured-output envelope** *(ratified amendment 2026-06-02 — `build/decisions/2026-06-02-proposal-structured-output-amendment.md`).*
The `Proposal` is emitted **valid-by-construction** against a strict structural schema and **validated at
assembly, before the Grounder** — a malformed `Proposal` cannot reach the citation gate. **Scope =
STRUCTURE ONLY:** required fields present, well-typed, in the PHS 398 Research Plan shape (`project_title`,
`central_hypothesis`, ≥1 `ProposalSection`, ≥1 `ExpandedAim` carrying its required parts, a `references`
deck, the `obligations` ledger). The **semantics are unchanged** — cited-∈-corpus (inv-1, §3.1), overclaim
(inv-3, §1.12/§3.3), and obligation coverage (inv-2, §3.2) still own all meaning; the envelope adds and
removes no semantic check. **Local validation only** (e.g. Pydantic) — deterministic, offline; **not** a
live/model structured-output API call. Grounded in NIH **G.400** (PHS 398 Research Plan, Forms Version I).

### 2.2 Generator stages
```
ArgumentSynthesizer(GenerationStage):
    map_over = None                               # runs once
    produce -> ArgumentSkeleton { gap, central_hypothesis, aim_stubs[], significance, innovation }
               # every claim tagged serves_dimension + evidence_ids
    config: model_id=claude-opus-4-8, effort=xhigh, n_samples>1, log_pairs=true, reward_source=[F1]

AimArchitect(GenerationStage):
    map_over = aim_stubs                          # runs once per aim
    produce(item = aim_stub) -> ExpandedAim
    config: model_id=claude-opus-4-8, effort=high, reward_source=[F2]
```

### 2.3 Task assembly
```
CommercialDiscoverySteering(SteeringSource): poll() emits InputDelta to commercial.* or GrantCall

NIHGrantTask(Task):
    artifact_type    = Proposal
    condition        = NIHReviewFramework
    generator        = [ArgumentSynthesizer, AimArchitect]
    source_set       = corpus
    steering_sources = [CommercialDiscoverySteering]
    sections         = [significance, innovation, aims...]
    input_contract   = required{ GrantCall, corpus, EvidenceAssessment }
                       optional{ subgroups, treatments, commercial }
```

### 2.4 Role configs (NIH, v1)
| role / stage | type | model_id | sampling | reward | v1 |
|---|---|---|---|---|---|
| Conditioner (Blueprint Planner) | LLM | claude-haiku-4-5-20251001 | temp 0.1 | — | knob idle |
| ArgumentSynthesizer | LLM | claude-opus-4-8 | effort xhigh | F1 | **engaged (primary)** |
| AimArchitect | LLM | claude-opus-4-8 | effort high | F2 | knob idle |
| Grounder (Grounding & Citation) | code | — | — | — | n/a |
| Critic (Internal Critic) | LLM | claude-opus-4-8 | effort high | calibrated to eval | **engaged** |
| Reviser | LLM | claude-sonnet-4-6 | temp 0.25 | Δ dimension scores | knob idle |
| Orchestrator | code | — | — | — | n/a |
| Selection Scorer (best-of-N) | LLM, light | claude-sonnet-4-6 | temp 0.0 | — (ranks F1/F2; not reward) | engaged with Synthesizer |

*Sampling is model-dependent: Opus 4.7/4.8 reject `temperature`/`top_p`/`top_k` (400) and use the
`effort` parameter; `temperature` applies only on Sonnet 4.6 / Haiku 4.5. Weight-level fine-tuning
(`lora_adapter`/SFT/DPO) is not available on these models — "engaged" means inference-time
best-of-N + reward wiring, not weight updates.*

### 2.5 Input contract & degradation
- `GrantCall` mechanism + limits **known**, else refuse to start.
- `corpus` non-empty with **stable ids**, else narrow claims and flag an F1 risk.
- `EvidenceAssessment` keyed to claims; an unscored claim is treated as `minimal`.
- `subgroups`, `treatments`, `commercial` are optional (raise the ceiling).

---

## 3. Hard invariants (unit tests)

1. **Citation integrity** — `GroundingReport.all_in_source_set == true` and `orphan_ids == []`. HARD gate.
2. **Obligation coverage** — every `Obligation.status == satisfied` with ≥1 `evidence_id`.
3. **No overclaim** — `level(claim) <= permitted(grade(claim))` for every empirical claim.

(1–3 run offline on any draft. Calibration/competitiveness tests need the eval harness — see work plan §6.)

---

## 4. Open binding decisions (resolve before implementing)

- **`Paper.resolvable_id` type** — PMID (Grounder resolves via NCBI E-utilities) or DOI (via Crossref).
  Owner: Literature Synthesis. Determines the Grounder's resolve step.
- **`EvidenceScores.grade` ordinality** — must be one of {strong, moderate, weak, minimal} with the
  evidence features behind it (was a 0–1 float). Cross-team change to the Evidence Scoring (skeptic)
  agent's output. Grade calibration is the skeptic's burden, validated against expert GRADE labels by
  inter-rater agreement. Owner: Evidence Scoring. (The early `schema.py` prototype still types
  `EvidenceItem.score: float` and is stale on this point.)
