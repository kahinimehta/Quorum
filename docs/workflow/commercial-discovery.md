---
layout: default
title: Commercial Discovery
parent: Workflow
nav_order: 5
description: "Agent 5 — commercial potential heuristics"
---

# Agent 5 — Commercial Discovery

**Module:** `neurodiscover/agents/commercial_discovery_agent.py`  
**Owner:** Alia Merchant / Amy He  
**Step order:** 5 (orchestrator logs trace)

---

## Role

Estimate **commercial potential** (0–10) for each scored connection using **in-memory heuristics** — subgroup keywords, mechanism class, treatment presence, and **evidence count** (continuous, not a single ≥5 threshold).

{: .highlight }
**Current code:** no Tavily or live web search. **NIH grants** are ingested via `pull-grants` / full mode (`pull_grants=true`); grant rows infer subgroup/mechanism/treatment from title keywords so they can enter agents 2–6.

## Reads

In-memory output from Agent 4 (`scored_connections`).

## Writes (via orchestrator)

```sql
UPDATE treatment_connections SET commercial_potential = ? WHERE connection_id = ?;
```

The orchestrator calls `_scale_score()` (×10) before UPDATE, so the DB column holds **0–100**.

| Stage | Minimum | Maximum |
|-------|---------|---------|
| Agent output (`commercial_potential` heuristic) | 0 | 10 |
| Stored on `treatment_connections` | 0 | 100 |

## Heuristic signals (code)

| Signal | Effect |
|--------|--------|
| Volume | `5.5 + min(2.5, evidence_count × 0.12)` |
| Subgroup mentions `gba` or `lrrk2` | +0.9 |
| Mechanism mentions `alpha` / `synuclein` | +0.6 |
| Mechanism mentions `lysosomal` / `kinase` | +0.7 |
| Non-empty treatment | +0.6 |

Capped at 10.0 before orchestrator scaling (×10 → stored 0–100).

## Example (agent output, pre-scale)

| Connection | commercial_potential |
|------------|---------------------|
| GBA subgroup → GCase activation | 7.8 |
| LRRK2 subgroup → LRRK2 inhibition | 8.1 |

Agent 6 combines scaled DB scores into `recommendations.confidence`.
