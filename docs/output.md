---
layout: default
title: Output examples
nav_order: 4
description: "API JSON shapes, recommendations, synthetic cohort, and dashboard panels"
---

# Output examples

What NeuroDiscover produces — ranked recommendations, agent trace, synthetic patients, and API response shapes.

---

## POST /api/run-discovery response

Full pipeline response (demo mode, abbreviated):

```json
{
  "run_id": "a1b2c3d4",
  "recommendations": [
    {
      "subgroup": "GBA-mutation PD",
      "treatment": "GCase activation",
      "confidence": 82.5,
      "tier": "Prioritize",
      "rationale": "Strong preclinical and Phase 2 signal for GCase chaperones in GBA carriers."
    }
  ],
  "agent_outputs": [
    {
      "agentName": "Literature Synthesis Agent",
      "stepOrder": 1,
      "summary": "Processed 5 literature rows (demo mode).",
      "createdAt": "2026-06-01T16:00:00Z"
    }
  ],
  "synthetic_cohort": [
    {
      "patient_id": "Patient A",
      "patient_letter": "A",
      "subgroup": "GBA-mutation PD",
      "subgroup_color": "#2563eb",
      "synthetic_age": 68,
      "synthetic_sex": "M",
      "key_feature": "GBA1 variant carriers",
      "top_opportunity": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "is_synthetic": true,
      "phi_free": true
    }
  ],
  "runStats": {
    "mode": "demo",
    "maxPapersRequested": 5,
    "processed": { "literature": 5, "trial": 0, "grant": 0, "total": 5 },
    "databaseTotals": { "literature": 228, "trial": 39, "grant": 40, "total": 307 },
    "added": { "literature": 0, "trial": 0, "grant": 0, "total": 0 }
  }
}
```

`steps` is an alias of `agent_outputs`.

---

## Recommendations (Agent 6)

```json
{
  "recommendations": [
    {
      "subgroup": "GBA-mutation PD",
      "treatment": "GCase activation",
      "confidence": 82.5,
      "tier": "Prioritize",
      "rationale": "Multiple literature and trial sources; strong mechanism alignment."
    },
    {
      "subgroup": "LRRK2 PD",
      "treatment": "LRRK2 inhibition",
      "confidence": 71.2,
      "tier": "Monitor",
      "rationale": "Phase 2 ongoing; evidence strength moderate."
    }
  ]
}
```

Scoring:

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Tier | Condition |
|------|-----------|
| Prioritize | confidence ≥ 80 |
| Monitor | 65 ≤ confidence < 80 |
| Reject | confidence < 65 |

---

## Agent trace

Every run logs one row per agent step in `agent_outputs`:

```json
{
  "runId": "a1b2c3d4",
  "steps": [
    {
      "agentName": "Literature Synthesis Agent",
      "stepOrder": 1,
      "summary": "Pulled 10 raw sources via BioMCP for Parkinson disease.",
      "payload": { "since_year": 2022, "incremental": false },
      "createdAt": "2026-06-01 12:00:00"
    },
    {
      "agentName": "Patient Subgroup Agent",
      "stepOrder": 1,
      "summary": "Identified 5 subgroups from 10 evidence rows.",
      "payload": { "subgroup_count": 5 },
      "createdAt": "2026-06-01 12:00:05"
    }
  ]
}
```

### Run status

| Status | Meaning |
|--------|---------|
| **Complete** | All six agents logged for `run_id` and at least one recommendation exists |
| **Partial** | Stopped early — dashboard shows e.g. `3/6` agents, not `?/6` |
| **Failed** | Exception during orchestration |

---

## Synthetic cohort (Patients A–E)

Generated per `run_id` from recommendations + subgroups. **Not stored in the database.** Every profile is labeled synthetic / no PHI.

```json
{
  "run_id": "abc123",
  "synthetic_cohort": [
    {
      "patient_id": "Patient A",
      "subgroup": "GBA-mutation PD",
      "top_opportunity": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "is_synthetic": true,
      "phi_free": true
    }
  ]
}
```

Route: `GET /api/synthetic-cohort?run_id=abc123`

---

## Database tables written

| Agent | Tables / columns |
|-------|------------------|
| 1 Literature | `evidence`, `subgroup_evidence`, `scan_state`, `agent_outputs` |
| 2 Subgroups | `subgroups`, `agent_outputs` |
| 3 Connections | `treatment_connections`, `connection_evidence`, `agent_outputs` |
| 4 Evidence | `treatment_connections.evidence_strength`, `agent_outputs` |
| 5 Commercial | `treatment_connections.commercial_potential`, `agent_outputs` |
| 6 Conclusion | `recommendations`, `agent_outputs` |

### Literature agent payload example

```json
{
  "new_evidence": 3,
  "skipped_duplicates": 7,
  "touched_existing": 7,
  "rejected_no_id": 1,
  "since_year": 2024,
  "incremental": true
}
```

---

## GET /api/stats

Database overview for dashboard KPI tiles:

```json
{
  "literature": 228,
  "trial": 39,
  "grant": 40,
  "subgroups": 5,
  "connections": 5,
  "totalEvidence": 307,
  "lastScanAt": "2026-06-02T14:32:00",
  "lastRunId": "a1b2c3d4",
  "database": "sqlite",
  "supabaseConfigured": false
}
```

---

## GET /api/discover/parkinsons

Subgroups and treatment connections for the discovery overview panel:

```json
{
  "disease": "Parkinson's Disease",
  "subgroups": [
    {
      "subgroupId": 1,
      "name": "GBA-mutation PD",
      "definingFeatures": "GBA1 variant carriers; reduced GCase activity",
      "evidenceCount": 2
    }
  ],
  "treatmentConnections": [
    {
      "connectionId": 1,
      "subgroup": "GBA-mutation PD",
      "mechanism": "lysosomal dysfunction",
      "treatment": "GCase activation",
      "evidenceStrength": 8.5,
      "commercialPotential": 7.2,
      "confidence": 80.2
    }
  ]
}
```

---

## Dashboard panels

| Panel | Source |
|-------|--------|
| KPI strip | `GET /api/stats` + `runStats` from last run |
| Run status strip | Complete / Partial / Running / Failed |
| Step 1 — Configure & run | `POST /api/run-discovery` |
| Step 2 — Pipeline diagram | Agent trace from `GET /api/agents?run_id=` |
| Synthetic cohort cards | `synthetic_cohort` in run response |
| Ranked treatments | `GET /api/recommendations?run_id=` |
| Evidence table | `GET /api/evidence?offset=&limit=` |
| Recent runs | `GET /api/runs?limit=5` |

See [Dashboard](dashboard) for how to run the UI locally.
