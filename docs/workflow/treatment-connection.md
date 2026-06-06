---
layout: default
title: Treatment Connection
parent: Workflow
nav_order: 3
description: "Agent 3 — map subgroup to mechanism to treatment"
---

# Agent 3 — Treatment Connection

**Module:** `neurodiscover/agents/treatment_connection_agent.py`  
**Owner:** Alia Merchant  
**Step order:** 3 (orchestrator logs trace)

---

## Role

Map **subgroup → mechanism → treatment** triples from in-memory evidence rows and return deduplicated connections with supporting `source_id` lists.

## Reads

In-memory evidence rows (from orchestrator) with `subgroup`, `mechanism`, and `treatment` populated — not a live SQL join at agent runtime.

## Writes (via orchestrator)

```sql
INSERT INTO treatment_connections (subgroup_id, mechanism, treatment) VALUES (?,?,?);
INSERT OR IGNORE INTO connection_evidence (connection_id, evidence_id) VALUES (?,?);
```

The orchestrator resolves `subgroup` name → `subgroup_id`, upserts connections, and links `evidence_sources` to `connection_evidence`.

## Logic (summary)

1. Group evidence by `(subgroup, mechanism, treatment)`
2. Count supporting rows and collect `source_id`s
3. Return connection objects for orchestrator persistence

## Example connection

| Field | Value |
|-------|-------|
| subgroup | GBA-mutation PD (demo seed name) |
| mechanism | lysosomal dysfunction |
| treatment | GCase activation |
| supporting sources | DEMO-PMID-001, DEMO-NCT-001 |

**Rapid motor progressors** use the slug `combination strategy`, displayed as **Combination neuroprotection** on the dashboard — a multi-agent neuroprotection stack for fast UPDRS trajectories (see [Output — treatment labels](../output#treatment-labels)).

## Output shape (in-memory)

```json
{
  "connections": [
    {
      "subgroup": "GBA-mutation PD",
      "mechanism": "lysosomal dysfunction",
      "treatment": "GCase activation",
      "evidence_sources": ["DEMO-PMID-001", "DEMO-NCT-001"],
      "evidence_count": 2
    }
  ]
}
```

Scores (`evidence_strength`, `commercial_potential`) are **null** until Agents 4 and 5 run.
