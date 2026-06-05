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

Act as a **skeptic** — score how strong the evidence is for each treatment connection from **evidence count** and **source types** (literature, trial, grant) on matching evidence rows.

## Reads

In-memory `connections` from Agent 3 plus matching rows from the evidence list passed by the orchestrator (same subgroup name).

{: .highlight }
**Not used in current code:** per-row `study_type`, `sample_size`, or `access_status` (those columns exist on `evidence` for future weighting).

## Writes (via orchestrator)

```sql
UPDATE treatment_connections SET evidence_strength = ? WHERE connection_id = ?;
```

The orchestrator calls `_scale_score()` (×10) before UPDATE, so the DB column holds **0–100**.

## Scoring heuristics (code)

| Signal | Effect |
|--------|--------|
| Base | 5.0 |
| `evidence_count` ≥ 3 | +1.0 |
| `evidence_count` ≥ 8 | +1.0 |
| Has `literature` source | +0.8 |
| Has `trial` source | +1.0 |
| Has `grant` source | +0.5 |

Capped at 10.0 before orchestrator scaling.

## Example (agent output, pre-scale)

| Connection | evidence_strength |
|------------|-------------------|
| GBA → GCase activation | 8.5 |
| Rapid progressors → combination strategy | 5.2 |

Agent 5 adds `commercial_potential`; Agent 6 combines scaled DB values into `confidence`.
