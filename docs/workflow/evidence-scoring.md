---
layout: default
title: Evidence Scoring
parent: Workflow
nav_order: 4
description: "Agent 4 — skeptic scores connection evidence strength"
---

# Agent 4 — Evidence Scoring (Skeptic)

**Module:** `neurodiscover/agents/evidence_scoring_agent.py`  
**Owner:** Alia Merchant  
**Step order:** 4 (orchestrator logs trace)

---

## Role

Act as a **skeptic** — score how strong the evidence is for each treatment connection from **per-connection evidence count** and **source types** (literature, trial, grant) on rows matching the same subgroup + mechanism + treatment triple.

## Reads

In-memory `connections` from Agent 3 plus evidence rows passed by the orchestrator that match each connection’s subgroup, mechanism, and treatment (not all rows for the subgroup).

{: .highlight }
**Not used in current code:** per-row `study_type`, `sample_size`, or `access_status` (those columns exist on `evidence` for future weighting).

## Writes (via orchestrator)

```sql
UPDATE treatment_connections SET evidence_strength = ? WHERE connection_id = ?;
```

The orchestrator calls `_scale_score()` (×10) before UPDATE, so the DB column holds **0–100**.

| Stage | Minimum | Maximum |
|-------|---------|---------|
| Agent output (`evidence_strength` heuristic) | 0 | 10 |
| Stored on `treatment_connections` | 0 | 100 |

## Scoring heuristics (code)

Scores **scale with support count** so new pulls that add rows to a connection move the number (not flat buckets only).

| Signal | Effect |
|--------|--------|
| Base + volume | `4.0 + min(4.5, evidence_count × 0.22)` |
| Has `literature` in matching rows | +0.6 |
| Has `trial` in matching rows | +0.8 |
| Has `grant` in matching rows | +0.4 |

Capped at 10.0 before orchestrator scaling (×10 → stored 0–100 on `treatment_connections`).

Adding a few supporting papers or trials to an existing connection typically changes `evidence_strength` by ~0.2–0.5 (pre-scale) per row.

## Example (agent output, pre-scale)

| Connection | evidence_strength |
|------------|-------------------|
| GBA → GCase activation | 8.5 |
| Rapid progressors → combination neuroprotection (`combination strategy`) | 5.2 |

Agent 5 adds `commercial_potential`; Agent 6 combines scaled DB values into `confidence`.
