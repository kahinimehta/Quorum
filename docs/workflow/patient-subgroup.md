---
layout: default
title: Patient Subgroup
parent: Workflow
nav_order: 2
description: "Agent 2 — cluster evidence into patient subgroups"
---

# Agent 2 — Patient Subgroup

**Module:** `neurodiscover/agents/patient_subgroup_agent.py`  
**Owner:** Alia Merchant  
**Step order:** 2

---

## Role

Read distilled evidence rows and refine **patient subgroup** definitions — grouping by `subgroup` name, aggregating mechanisms and treatments, and writing canonical definitions to `subgroups`.

## Reads

```sql
SELECT evidence_id, subgroup, mechanism, treatment, key_result, study_type, sample_size
FROM evidence
WHERE subgroup IS NOT NULL;
```

## Writes

| Table | Action |
|-------|--------|
| `subgroups` | INSERT new names or UPDATE `defining_features` / `notes` |
| `agent_outputs` | Trace with subgroup count and names |

## Logic (summary)

1. Group evidence rows by `subgroup` string
2. Collect distinct mechanisms and treatments per subgroup
3. Build defining features from aggregated evidence snippets
4. Emit structured subgroup objects for Agent 3

## Seed vocabulary

Prefer exact match to these five names:

- GBA-mutation PD
- LRRK2 PD
- Alpha-synuclein-high PD
- Inflammation-high PD
- Rapid motor progressors

## Rules

- **Do not** duplicate evidence rows — tag in evidence, refine in `subgroups`
- Literature Agent auto-links via `subgroup_evidence` when names match exactly

## Example output shape (in-memory)

```json
{
  "subgroups": [
    {
      "name": "GBA-mutation PD",
      "defining_features": "GBA1 variant carriers; reduced GCase activity",
      "mechanisms": ["lysosomal dysfunction"],
      "treatments": ["GCase activation"],
      "evidence_count": 2
    }
  ]
}
```
