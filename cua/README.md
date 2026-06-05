# Conclusion Update Agent (CUA)

CUA is the terminal agent (**Agent 6 — Conclusion Update**) of the NeuroDiscover multi-agent pipeline.
It turns **upstream evidence** (a literature corpus from the Literature Synthesis agent + a grant call)
into a written **NIH proposal**, with a **Trace** (internal, per-subagent calls), an **Audit**
(judge-facing: citation integrity, the rubric-obligation ledger, critic scores, overclaim check), and an
**Ingestion report** (the corpus rank-and-bound).

The engine is **task-agnostic** — a *conditioned generator with self-correction, steerability, and
test-time-compute scaling*. It instantiates here for one `Task`: an NIH R01 grant, with the NIH Simplified
Review Framework as its `Condition`. See `files/conclusion_update_agent_design.md` (§1–3 design, **§7 as-built**).

## Status: v1.1 — grades bound · the F2 information-integration seam · full content capture

All LLM roles + the code spine run live; the deterministic offline path is **byte-identical**
(`sha256(python -m cua.nih.run)` is fixed across hash seeds — the load-bearing test for every change).
**New since v1.0:**
- **Evidence grades are bound.** The upstream skeptic's grades now reach the claims (lifting the overclaim cap) —
  consumed via a **local read-only snapshot** (no shared-DB write). *Heuristic, uncalibrated — see Honest limits.*
- **The F2 Rigor Booster** — an in-loop **information-integration seam** that mines the un-selected corpus.
- **Content capture** — `<run>.content.json` records every subagent's message; a self-contained HTML report renders it.
- **Compute knobs** — `--capture-content`, `--no-booster`, `--force-rounds`, `--max-rounds`, `--bar`.

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
| **Harden** (revise path) | **F2 Rigor Booster** (Opus, live-only) — mines the un-selected corpus | LLM |
| Revise | Reviser (Sonnet) — overclaim resister | LLM |
| Orchestrate | the loop + the §1.11 stopping rule | code |

Two test-time-compute axes: **parallel** (best-of-N, Selection-Scorer-ranked) and **sequential** (the revise loop).

## Data pipeline — ingestion + bound evidence grades

`neurodiscover` (the team blackboard) → read-only adapter (`cua/nih/adapters/neurodiscover.py`) →
**Ingestion Layer** (`cua/nih/ingestion.py`) → the agent loop.

**Ingestion** is a deterministic, rule-based **rank-and-bound** stage (no LLM, no embeddings): it clusters by
`key_finding`, ranks by topic relevance + recency, and hands the writer a **diversity-bounded top-K view** instead of
all ~400 findings. **id-preserving** — the *full* corpus stays the citation gate's referent, so inv-1 is unchanged.

**Evidence grades (the skeptic).** The skeptic's `evidence_strength` grades set the overclaim ladder's *permitted
level* per claim (`moderate` → L3, etc.), which the Critic uses to flag overclaims (inv-3). The grades are produced by
running the upstream **Agent-4 (Evidence Scoring)** logic **read-only over the real evidence into a local SQLite
snapshot** (no write to the shared DB); the adapter then binds each claim to its connection's grade. See design **§7**.

## The F2 Rigor Booster — in-loop information integration

On each revise round, the booster reads the **un-selected corpus** (`corpus.sources − writer_view` — the papers the
Ingestion Layer bounded *out* of the writer's view, "the road not taken") and rewrites each aim's
`pitfalls_alternatives` + `expected_outcomes` from those comparable studies the writer never saw. The point is the
**reusable seam** — injecting new information into the loop *without breaking the invariants*: cites ∈ full corpus
(inv-1); it never re-grades evidence (fixed ladder); it feeds the **Reviser, never the Critic** (which serializes only
approach text + claims), so the **blinded eval judge** stays the independent arbiter. The same seam generalizes to
external critiques, retrieved papers, or steering. *Live-only → the offline oracle is unchanged.*

## Observability — content capture + the visual report

With `--capture-content`, CUA emits `<run>.content.json` (observation-only; the Proposal/Trace/Audit are
**byte-identical** with capture on or off) recording **every subagent's message**: the planner's obligation contract,
the best-of-N candidates + the Selection-Scorer's rationale, the per-round draft, the Grounder's inv-1 gate, the
Critic's per-round scores, the Reviser's hedge diffs, and the booster's road-not-taken provenance. The operator tool
`build/viz/render_full2.py` renders any captured run into a self-contained HTML report (see the demo).

## Compute knobs & tuning surface (design §5, §7)

- **`RoleConfig`** (per LLM role): `model_id`, `temperature`/`effort`, `system_prompt_template`, `n_samples` (best-of-N).
- **`IngestionConfig`**: `top_k`, `cluster_similarity_threshold`, `per_cluster_cap`, `polarity_aware`.
- **`RunConfig`**: `max_rounds`, `dimension_thresholds` (the bar), `force_rounds`.
- **CLI** (`run_db`): `--capture-content` · `--n-samples N` (parallel) · `--max-rounds N` / `--bar N` (sequential) ·
  `--force-rounds N` (exactly N revise rounds, ignoring pass) · `--no-booster` (the matched A/B baseline arm).
  All default-off ⇒ byte-identical to the base run.

## How to run

```bash
pip install -e .                       # anthropic, pydantic, httpx, pytest
pytest                                 # offline hard invariants (deterministic, byte-identical)

# offline demo — deterministic surrogates, no API, no DB:
python -m cua.nih.run                  # → outputs/<fixture>.{proposal,trace,audit}.json

# live demo — real models over a local read-only evidence snapshot:
export ANTHROPIC_API_KEY=...           # the LLM roles
export CUA_LIVE=1
python -m cua.nih.run_db --db local.sqlite --run-id graded --capture-content
# → outputs/graded.{proposal,trace,audit,ingestion,content}.json

# the self-contained visual report ships pre-rendered at outputs/graded6.html
```

Surrogates are the **default** (offline byte-identical); the live path is behind `CUA_LIVE` + `ANTHROPIC_API_KEY`.
`local.sqlite` is the read-only evidence-grade snapshot (built from the upstream evidence; never the shared DB).
The visual report (`outputs/graded6.html`) is rendered from a run's artifacts by the operator tooling.

## The v1.1 demo (`outputs/graded6.*`)

A live Opus-written NIH proposal on the 400 real PD papers with the booster firing: ingestion **400 → 60**, grades
bound (`moderate` → cap lifted, **inv-3 clean**), all roles live, best-of-N + revise rounds, the booster mining the
un-selected corpus (the road-not-taken → aim links). Open **`outputs/graded6.html`** — a self-contained report:
the data loop (with the booster), the obligation contract, the road not taken, the blinded-judge A/B, the round-by-round
gate + scores, the proposal, audit, and ingestion.

## Honest limits

- **Grades are an uncalibrated heuristic.** The skeptic (Agent-4) is rule-based, not a validated grader — every grade
  is flagged `calibrated:False`. We *consume* it (to lift the overclaim cap); we don't *trust* it as calibrated. A
  validated skeptic is upstream work.
- **The booster's measured lift is real but modest — read with a grain of salt.** A matched, blinded A/B (`--no-booster`
  baseline) shows judge-F2 ≈ **5.25 booster vs 4.5 baseline** — but the grades are uncalibrated and the judge's F2 is a
  coarse integer from a single model, so the ~0.75 gap sits within the measurement noise, and the arms overlap. The
  honest claim is *a working information-integration seam that yields judge-creditable rigor content*, not a precise lift.
- **External critiques (the prose path) are unwired.** The `external_critiques` channel is threaded to the Critic but
  unfed — the skeptic emits grades, not prose; commercial is out of scope at v1. It's the seam's obvious next payload.
- **Steering** (the 3rd pillar) — deferred by design.

## Layout

```
files/        design + frozen contracts (source of truth; §7 = as-built)
src/cua/      the agent — engine + NIH binding + LLM roles + Ingestion Layer + F2 booster
testdata/     fixtures
tests/        invariants + eval
outputs/      run artifacts: Proposal / Trace / Audit / Ingestion (+ content.json, .html)
```

## Source of truth

`files/conclusion_update_agent_contracts.md` (interfaces) · `…_design.md` (rationale + **§7 as-built**) ·
`…_nih_obligations.md` (the F1/F2/F3 rubric) · `…_test_*` (fixtures, tester/reviewer).
