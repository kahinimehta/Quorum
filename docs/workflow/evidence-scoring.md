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
**Step order:** 4

---

## Role

Act as a **skeptic** — score how strong the evidence is for each treatment connection based on study type, sample size, access status, and result quality.

## Reads

```sql
SELECT tc.connection_id, e.study_type, e.sample_size, e.access_status, e.key_result
FROM treatment_connections tc
JOIN connection_evidence ce ON ce.connection_id = tc.connection_id
JOIN evidence e ON e.evidence_id = ce.evidence_id;
```

## Writes

```sql
UPDATE treatment_connections SET evidence_strength = ? WHERE connection_id = ?;
```

Plus `agent_outputs` with scoring summary.

## Scoring heuristics

| Signal | Effect |
|--------|--------|
| RCT / Phase 2 / Phase 3 | Higher weight |
| Large `sample_size` | Higher weight |
| `access_status = abstract_only` | Down-weight |
| Preclinical / mouse only | Moderate weight |
| Multiple supporting sources | Boost |

Scores are stored on a **0–10** scale internally.

## Example

| Connection | evidence_strength |
|------------|-------------------|
| GBA → GCase activation | 8.5 |
| Rapid progressors → combination strategy | 5.2 |

Agent 5 adds `commercial_potential`; Agent 6 combines both into `confidence`.
