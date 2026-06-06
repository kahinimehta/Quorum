---
layout: default
title: Conclusion Update
parent: Workflow
nav_order: 6
description: "Agent 6 — dashboard rankings and CUA NIH grant proposal"
---

# Agent 6 — Conclusion Update

Agent 6 has **two implementations**. They share the name and read the same upstream blackboard, but they serve different purposes and do not replace each other.

| | **Dashboard pipeline** | **CUA package** (`cua/`) |
|---|---|---|
| **Purpose** | Rank treatments for the dashboard | Write a full **NIH R01 grant proposal** from the evidence |
| **Module** | `neurodiscover/orchestrator.py` | `cua/src/cua/` (standalone package) |
| **Owner** | Amy He (orchestrator) | Alia Merchant (CUA) |
| **Runs when** | Every `demo` / `scan` / `full` / `agents-only` pipeline run | **Manually** — not part of the dashboard pipeline |
| **Uses LLMs** | No | Yes — Blueprint, Synthesizer, Critic, Reviser, etc. |
| **Writes DB** | `recommendations` + `agent_outputs` | **Nothing** — read-only consumer |
| **Output** | Ranked Prioritize / Monitor / Reject cards | Local files: proposal, trace, audit, ingestion (+ HTML report) |

The dashboard pipeline run uses the **orchestrator path** for ranked recommendations. **CUA** is the grant-proposal path for Agent 6 — bundled on **Step 3 — Grant Proposal** (`graded6`) and runnable live via CLI after the pipeline has populated evidence.

---

## Dashboard pipeline (what the demo runs)

**Module:** logic in `neurodiscover/orchestrator.py`  
**Step order:** 6 (in-process after agents 2–5)

### Role

Combine evidence and commercial scores into **ranked recommendations** with Prioritize / Monitor / Reject tiers and a short rationale string.

### Reads

```sql
SELECT tc.connection_id, s.name AS subgroup, tc.treatment,
       tc.evidence_strength, tc.commercial_potential
FROM treatment_connections tc
JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
WHERE tc.evidence_strength IS NOT NULL AND tc.commercial_potential IS NOT NULL;
```

### Writes

```sql
INSERT INTO recommendations (run_id, connection_id, subgroup, treatment, confidence, tier, rationale)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

Plus final `agent_outputs` row.

### Confidence formula

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Field | Minimum | Maximum |
|-------|---------|---------|
| Agent 4/5 heuristics (pre-scale) | 0 | 10 |
| `evidence_strength` / `commercial_potential` (stored) | 0 | 100 |
| `confidence` (API + dashboard) | 0 | 100 |

### Tier rules

| Tier | Condition |
|------|-----------|
| **Prioritize** | confidence ≥ 80 |
| **Monitor** | 65 ≤ confidence < 80 |
| **Reject** | confidence < 65 |

### Example recommendation

```json
{
  "subgroup": "GBA-mutation PD",
  "treatment": "GCase activation",
  "mechanism": "lysosomal dysfunction",
  "confidence": 82.5,
  "tier": "Prioritize",
  "rationale": "GBA-mutation PD → GCase activation via lysosomal dysfunction. Confidence 82.5 (Prioritize)."
}
```

### Downstream

- Dashboard **Ranked treatments** panel reads `recommendations`
- **Synthetic cohort** (Patients A–E) generated from top recommendations — not persisted

See [Output examples](../output) for full JSON shapes.

---

## CUA package — NIH grant proposal

**Package:** `cua/` at repo root  
**Entrypoint:** `python -m cua.nih.run_db`  
**Design docs:** `cua/files/conclusion_update_agent_design.md`, `cua/README.md`

CUA (Conclusion Update Agent) reads the NeuroDiscover blackboard and produces a **written NIH R01 grant proposal** with citation grounding, multi-round self-correction, and a full audit trail. The dashboard **Step 3 — Grant Proposal** tab shows the bundled `graded6` output; live runs use the CLI below. CUA does **not** write to `recommendations` or run inside the Steps 1–2 pipeline (`make dashboard` / `cli.py demo`).

### What it does (step by step)

1. **Reads** the shared DB read-only — `evidence`, `subgroups`, `treatment_connections`, `connection_evidence`
2. **Ingestion** — clusters by similar `key_finding`, ranks by topic relevance, and selects **verified papers** (`top_k`, e.g. 60) for drafters; the **full corpus** (e.g. 400) stays available for citation checks (inv-1). See [Dashboard — Corpus vs verified papers](../dashboard#corpus-vs-verified-papers).
3. **Plans** — Blueprint Planner sets NIH rubric obligations (F1/F2/F3)
4. **Writes** — Synthesizer drafts the argument (best-of-N), Aim Architect structures specific aims
5. **Grounds** — hard gate: every citation must exist in the corpus
6. **Critiques** — blind Critic scores against NIH criteria; flags overclaims vs evidence grades
7. **Revises** — Reviser fixes problems; **F2 Rigor Booster** (when enabled) injects papers the writer did not see
8. **Outputs local files** (not DB rows):
   - `<run>.proposal.json` — grant text
   - `<run>.trace.jsonl` — per-subagent calls
   - `<run>.audit.json` — citation integrity, critic scores, overclaim check
   - `<run>.ingestion.json` — corpus rank-and-bound report
   - `<run>.content.json` + HTML visual report when `--capture-content` is set (`cua/outputs/graded6.html` ships pre-rendered for the dashboard)

Evidence grades come from Agent 4 logic replayed into a **local read-only SQLite snapshot** — CUA never writes to the shared Supabase/SQLite blackboard.

### Critic score scale (F1 / F2 / F3)

The Internal Critic scores **F1**, **F2**, and **F3** on an integer **1–9** scale (minimum **1**, maximum **9**) — shown in Tab 3 as `n/9`:

| Range | Meaning |
|-------|---------|
| 1–4 | Needs revision |
| 5–6 | Meets typical revise-loop threshold |
| 7–9 | Strong |

The revise loop typically stops when **F1 ≥ 5** and **F2 ≥ 5**. Bundled `graded6` final scores: **F1 = 7**, **F2 = 5**, **F3 = 6**. See [Dashboard — Critic score scale](../dashboard#critic-score-scale-f1--f2--f3).

### How to run

```bash
cd cua
pip install -e .

# Offline demo — deterministic surrogates, no API, no DB:
python -m cua.nih.run

# Live against team Supabase (or local neurodiscover.db):
export ANTHROPIC_API_KEY=...
export CUA_LIVE=1
python -m cua.nih.run_db --db "$SUPABASE_DATABASE_URL" --run-id demo-1 --capture-content
```

Set `SUPABASE_DATABASE_URL` from [Supabase setup](../developer-reference/supabase). Use a local path instead of the URL for SQLite.

### Integration posture

- CUA is a **read-only downstream consumer** of the same data the dashboard pipeline writes
- PR #12 added `neurodiscover/frontend/supabase_dashboard.html` for viewing Supabase evidence/connections/recommendations — that page does not invoke CUA
- Full CUA architecture, contracts, and honest limits: `cua/README.md`
- **Dashboard:** Step 3 **Grant Proposal** tab inlines the static bundled `graded6` report — **The proposal** expanded at top (above data loop), then one collapsed **Pipeline trace & audit** group (single click, no nested collapses); **Jump to** scrolls to Proposal or opens supporting details — not tied to Step 1/2 `run_id` (see [Dashboard — Step 3 report structure](../dashboard#step-3--report-structure))
