# Conclusion Update Agent (CUA)

CUA is the terminal agent (**Agent 6 — Conclusion Update**) of the NeuroDiscover multi-agent pipeline.
It turns **upstream evidence** (a literature corpus from the Literature Synthesis agent + a grant call)
into a written **NIH proposal**, with a **Trace** (internal, per-subagent calls), an **Audit**
(judge-facing: citation integrity, the rubric-obligation ledger, critic scores, overclaim check), and an
**Ingestion report** (the corpus rank-and-bound).

The engine is **task-agnostic** — a *conditioned generator with self-correction, steerability, and
test-time-compute scaling*. v1.0 instantiates it for one `Task`: an NIH R01 grant, with the NIH Simplified
Review Framework as its `Condition`. See `files/conclusion_update_agent_design.md` (§1–3 design, **§7 as-built**).

## Status: v1.0 — full pipeline live

All six LLM roles + two code roles are built and run live; the deterministic offline path is byte-identical.
Proven end-to-end on the real **400-paper** Parkinson's corpus (`outputs/full2.*`): **inv-1 / inv-2 PASS**, and
inv-3 honestly flags the one residual overclaim (see **Residuals**).

## Architecture (design §2–3)

A deterministic spine carries the trust-critical logic; the judgement-heavy roles are LLMs.

| Stage | Role | Kind |
|---|---|---|
| **Ingestion** (data pipeline) | rank-and-bound corpus intake — `key_finding` clustering | code |
| Condition | Blueprint Planner (Haiku) — topic-specialized obligations | LLM |
| Generate · F1 | Argument Synthesizer (Opus, **best-of-N**) + Selection Scorer (Sonnet) | LLM |
| Generate · F2 | Aim Architect (Opus) | LLM |
| Ground | Grounding & Citation — the **inv-1** hard gate | code |
| Critique | Internal Critic (Opus, blind) — the reward engine | LLM |
| Revise | Reviser (Sonnet) — overclaim resister | LLM |
| Orchestrate | the loop + the §1.11 stopping rule | code |

Two test-time-compute axes: **parallel** (best-of-N, Selection-Scorer-ranked) and **sequential** (the revise loop).

## Data pipeline — the Ingestion Layer

`neurodiscover` (the team blackboard) → read-only adapter (`cua/nih/adapters/neurodiscover.py`) →
**Ingestion Layer** (`cua/nih/ingestion.py`) → the agent loop.

The Ingestion Layer is a deterministic, rule-based **rank-and-bound** stage (no LLM, no embeddings): it
clusters the corpus by `key_finding`, ranks by topic relevance + recency, and hands the writer a
**diversity-bounded top-K view** (representatives + corroboration counts) instead of all ~400 findings —
fixing the writer output-budget overruns at full scale. It is **id-preserving**: the *full* corpus stays the
citation gate's referent, so inv-1 is unchanged. The bound + cluster selection (+ any swallowed contradiction)
are emitted to `<run>.ingestion.json` — the honesty mechanism while evidence grades are flat. See design **§7**.

## Tuning surface (design §5, §7)

- **`RoleConfig`** (per LLM role): `model_id`, `temperature`/`effort`, `system_prompt_template`,
  `few_shot_exemplars`, `n_samples` (best-of-N), `reward_source`.
- **`IngestionConfig`** (the deterministic intake stage): `top_k`, `cluster_similarity_threshold`,
  `per_cluster_cap`, `polarity_aware`.
- **`RunConfig`**: `max_rounds`, `dimension_thresholds` (the stopping bar).

## How to run

```bash
pip install -e .                       # anthropic, pydantic, httpx, pytest
pytest                                 # offline hard invariants (deterministic, byte-identical)

# offline demo — deterministic surrogates, no API, no DB:
python -m cua.nih.run                  # → outputs/<fixture>.{proposal,trace,audit}.json

# live demo — real models + the neurodiscover DB (read-only):
export ANTHROPIC_API_KEY=...           # the 6 LLM roles
export CUA_LIVE=1
export SUPABASE_DATABASE_URL=...       # read-only Session-pooler URL (see neurodiscover/docs/SUPABASE.md)
python -m cua.nih.run_db --db "$SUPABASE_DATABASE_URL" --run-id full2
# → outputs/full2.{proposal,trace,audit,ingestion}.json
```

Surrogates are the **default** (offline byte-identical); the live path is behind `CUA_LIVE` + `ANTHROPIC_API_KEY`.

## The v1.0 demo (`outputs/full2.*`)

A live Opus-written NIH proposal on the 400 real PD papers: ingestion **400 → 60**, all 6 roles live,
best-of-N + 2 revise rounds; **inv-1 PASS** (16 real cites, 0 fabrication), **inv-2 PASS**, **inv-3 = 1 honest
flag**. Open **`outputs/full2.html`** — a self-contained visual report of this run (pipeline timeline, proposal,
audit, ingestion).

## Residuals (the honest ceiling)

- **Ungraded evidence** — the upstream skeptic (NeuroDiscover **Agent 4, Evidence Scoring**) is unbuilt → every
  evidence grade is `minimal` → the overclaim ladder permits only L1 → any ambitious aim hypothesis is flagged by
  inv-3 (a **flag, not a gate**). This is the single inv-3 flag in the demo; it clears when real grades arrive.
- **No per-paper subgroup/mechanism tags** — those upstream tables (Agents 2/3) are seeded/empty, not
  agent-produced, and don't reach per-paper. The Ingestion Layer's diversity axis is therefore `key_finding`
  clustering (a *findings* axis, not a stance/grade axis) + an honest drop-audit.
- **Steering + few-shot curation** — deferred by design.

## Layout

```
files/        design + frozen contracts (source of truth; §7 = as-built)
src/cua/      the agent — engine + NIH binding + 6 LLM roles + Ingestion Layer
testdata/     fixtures
tests/        invariants + eval
outputs/      run artifacts: Proposal / Trace / Audit / Ingestion
```

## Source of truth

`files/conclusion_update_agent_contracts.md` (interfaces) · `…_design.md` (rationale + **§7 as-built**) ·
`…_nih_obligations.md` (the F1/F2/F3 rubric) · `…_test_*` (fixtures, tester/reviewer).
