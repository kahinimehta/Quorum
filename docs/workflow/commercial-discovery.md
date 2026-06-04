---
layout: default
title: Commercial Discovery
parent: Workflow
nav_order: 5
description: "Agent 5 — market and funding signals"
---

# Agent 5 — Commercial Discovery

**Module:** `neurodiscover/agents/commercial_discovery_agent.py`  
**Owner:** Alia Merchant / Amy He  
**Step order:** 5

---

## Role

Estimate **commercial potential** for each treatment connection using web search, grant landscape, and competitive context.

## Reads

- `treatment_connections` (mechanism, treatment, subgroup_id)
- Linked evidence via `connection_evidence`

## External tools

| Tool | Purpose |
|------|---------|
| **Tavily** | Live web search — market size, competitors, white space |
| **NIH RePORTER** | Already-funded? grant density for mechanism/treatment |

## Writes

```sql
UPDATE treatment_connections SET commercial_potential = ? WHERE connection_id = ?;
```

Optional: INSERT grant rows into `evidence` with `source_type = 'grant'`.

Plus `agent_outputs`.

## Scoring signals

| Signal | Effect |
|--------|--------|
| Active Phase 2/3 trials | Higher potential |
| Crowded competitive landscape | Lower white-space score |
| Strong NIH funding | Validates interest; may lower novelty |
| Orphan / unmet need subgroup | Higher potential |

Scores on **0–10** scale, paired with `evidence_strength` in Agent 6.

## Example

| Connection | commercial_potential |
|------------|---------------------|
| GBA → GCase activation | 7.8 |
| LRRK2 → LRRK2 inhibition | 8.1 |
