# src/cua/ — the agent (builder 1)

The task-agnostic **engine** plus the **NIH binding**. Two layers, kept strictly separate (design §2
"Design rule"): engine files name nothing domain-specific; everything NIH lives under `nih/`.

> Status: the engine spine + NIH binding landed at S2; the writer roles (`roles/blueprint.py`,
> `synthesizer.py`, `aim_architect.py`, `selection_scorer.py`) + the obligation loader
> (`nih/obligations.py`) landed at S4; the Critic + Reviser (`roles/critic.py`, `roles/reviser.py`)
> landed at S5 — **closing the revise loop** (the S2 `nih/stubs.py` was removed). The table is the
> **file → contract-section map**: each file's top header (CONVENTIONS rule 1) names the contract
> section listed here. Owners are the sessions from design §6. (The S2 deviation-2 note —
> `CritiqueReport`/`Level` live in `types.py` — and the full nih/ row list, e.g. `task.py` / `run.py` /
> `calibration_anchors.py`, are folded into the S6 doc-sync cleanup.)

## Engine layer (must NOT name NIH/proposal/factor/aim/citation)

| File | Generic role | Implements (contract §) | Owner |
|---|---|---|---|
| `types.py` | value types | §1.1–§1.4 (Source, SourceSet, Grade, EvidenceScores, Obligation, Task, Draft…) | S2 |
| `config.py` | `RoleConfig` + role table | §1.8 (RoleConfig); NIH role table §2.4 lives in `nih/` | S2 |
| `orchestrator.py` `[code]` | Orchestrator | §1.5, §1.11 (loop + stopping rule), §1.10 (Trace/Audit assembly) | S2 |
| `generation.py` | Generator driver | §1.6 (staged pipeline, `map_over` fan-out, best-of-N driver) | S2 (driver) → S4 (stages) |
| `grounding.py` `[code]` | Grounder | §1.5, §1.10 (GroundingReport), §3 inv-1 (citation-integrity HARD gate) | S2 |
| `trace.py` `[code]` | Trace/Audit | §1.10 (TraceEvent/Trace, Audit assembly) | S2 |

## roles/ — the LLM roles (engine signatures; configured per §2.4)

| File | Generic role | Implements (contract §) | Owner |
|---|---|---|---|
| `roles/blueprint.py` | Conditioner | §1.5, §1.2; emits the `nih_obligations.md` set | S4 |
| `roles/synthesizer.py` | Generator stage 1 | §1.6, §2.2 (ArgumentSynthesizer); reward F1 | S4 |
| `roles/aim_architect.py` | Generator stage 2 | §1.6, §2.2 (AimArchitect, `map_over=aim_stubs`); reward F2 | S4 |
| `roles/selection_scorer.py` | SelectionScorer `[light]` | §1.5 (best-of-N ranker; separate from Critic) | S4 |
| `roles/critic.py` | Critic | §1.5, §1.7 (CritiqueReport); blind to `self_score` | S5 |
| `roles/reviser.py` | Reviser | §1.5 (targeted edit) | S5 |

## nih/ — the NIH-grant binding (the ONLY place domain nouns live)

| File | Implements (contract §) | Owner |
|---|---|---|
| `nih/framework.py` | §2.1 (NIHReviewFramework `Condition`, F1/F2/F3) | S4 |
| `nih/obligations.py` | obligation loader reading `files/conclusion_update_agent_nih_obligations.md` | S4 |
| `nih/proposal.py` | §2.1 (Proposal, ProposalSection, ExpandedAim, RubricObligation) | S2 (type) → S4 (fill) |

## Boundary reminders

- **Closed-world** (design principle 6): no role takes a search/retrieval tool. Only the Grounder
  reaches the network, and only to *verify* references (resolve), never to gather.
- **Trust-critical logic in code** (design principle 3): the loop, stopping rule, intake gate, and
  citation-integrity gate are deterministic — never delegated to a model.
- Two open binding decisions affect this layer (`Paper.resolvable_id` type → `grounding.py`;
  ordinal `EvidenceScores.grade` → `types.py`). See `build/decisions/OPEN.md`.
