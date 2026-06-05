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
**Step order:** 3

---

## Role

Map **subgroup → mechanism → treatment** triples from evidence and write deduplicated connections with supporting citation links.

## Reads

```sql
SELECT s.subgroup_id, s.name, e.mechanism, e.treatment, e.evidence_id
FROM evidence e
JOIN subgroups s ON s.name = e.subgroup
WHERE e.mechanism IS NOT NULL AND e.treatment IS NOT NULL;
```

Also consumes in-memory output from Agent 2 for subgroup metadata.

## Writes

```sql
INSERT INTO treatment_connections (subgroup_id, mechanism, treatment) VALUES (?,?,?);
INSERT OR IGNORE INTO connection_evidence (connection_id, evidence_id) VALUES (?,?);
```

Plus `agent_outputs` trace.

## Logic (summary)

1. Build a map of `(subgroup, mechanism, treatment)` → supporting evidence rows
2. Rank connections by evidence count
3. Insert unique connections and link each to supporting `evidence_id`s via `connection_evidence`

## Example connection

| Field | Value |
|-------|-------|
| subgroup | GBA-mutation carriers |
| mechanism | lysosomal dysfunction |
| treatment | GCase activation |
| supporting sources | DEMO-PMID-001, DEMO-NCT-001 |

## Output shape (in-memory)

```json
{
  "connections": [
    {
      "subgroup": "GBA-mutation carriers",
      "mechanism": "lysosomal dysfunction",
      "treatment": "GCase activation",
      "source_ids": ["DEMO-PMID-001", "DEMO-NCT-001"],
      "evidence_count": 2
    }
  ]
}
```

Scores (`evidence_strength`, `commercial_potential`) are **null** until Agents 4 and 5 run.
