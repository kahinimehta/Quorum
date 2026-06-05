---
layout: default
title: Conclusion Update
parent: Workflow
nav_order: 6
description: "Agent 6 — ranked recommendations"
---

# Agent 6 — Conclusion Update

**Module:** logic in `neurodiscover/orchestrator.py`  
**Owner:** Amy He  
**Step order:** 6

---

## Role

Combine evidence and commercial scores into **ranked recommendations** with Prioritize / Monitor / Reject tiers and human-readable rationale.

## Reads

```sql
SELECT tc.connection_id, s.name AS subgroup, tc.treatment,
       tc.evidence_strength, tc.commercial_potential
FROM treatment_connections tc
JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
WHERE tc.evidence_strength IS NOT NULL AND tc.commercial_potential IS NOT NULL;
```

## Writes

```sql
INSERT INTO recommendations (run_id, connection_id, subgroup, treatment, confidence, tier, rationale)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

Plus final `agent_outputs` row.

## Confidence formula

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

Displayed as 0–100 in the API (internal 0–10 scores × 10).

## Tier rules

| Tier | Condition |
|------|-----------|
| **Prioritize** | confidence ≥ 80 |
| **Monitor** | 65 ≤ confidence < 80 |
| **Reject** | confidence < 65 |

## Example recommendation

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

## Downstream

- Dashboard **Ranked treatments** panel reads `recommendations`
- **Synthetic cohort** (Patients A–E) generated from top recommendations — not persisted

See [Output examples](../output) for full JSON shapes.
