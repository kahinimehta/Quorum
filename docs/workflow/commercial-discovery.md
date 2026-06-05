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

Estimate **commercial potential** (0–10) for each scored connection using **in-memory heuristics** — subgroup keywords, mechanism class, treatment presence, and evidence count.

{: .highlight }
**Current code:** no Tavily or live web search. Grants enter the DB via `cli.py pull-grants` or **full** mode (`pull_grants=true`), not inside this agent.

## Reads

In-memory output from Agent 4 (`scored_connections`).

## Writes (via orchestrator)

```sql
UPDATE treatment_connections SET commercial_potential = ? WHERE connection_id = ?;
```

The orchestrator calls `_scale_score()` (×10) before UPDATE, so the DB column holds **0–100**.

## Heuristic signals (code)

| Signal | Effect |
|--------|--------|
| Subgroup mentions `gba` or `lrrk2` | +1.0 |
| Mechanism mentions `alpha` / `synuclein` | +0.7 |
| Mechanism mentions `lysosomal` / `kinase` | +0.8 |
| Non-empty treatment | +0.7 |
| `evidence_count` ≥ 5 | +0.5 |

Base score 6.0, capped at 10.0 before scaling.

## Example (agent output, pre-scale)

| Connection | commercial_potential |
|------------|---------------------|
| GBA subgroup → GCase activation | 7.8 |
| LRRK2 subgroup → LRRK2 inhibition | 8.1 |

Agent 6 combines scaled DB scores into `recommendations.confidence`.
