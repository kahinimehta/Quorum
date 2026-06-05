---
layout: default
title: Backend queries
parent: Developer reference
nav_order: 3
---

# Backend queries

**Database file:** `neurodiscover/neurodiscover.db` (SQLite, inside `neurodiscover/` package dir — see `paths.py`)  
**Full SQL:** [`queries.sql`](../../queries.sql)  
**Schema:** [Database schema](database)

## Connection (Python example)

```python
import sqlite3
conn = sqlite3.connect("neurodiscover/neurodiscover.db")
conn.row_factory = sqlite3.Row
```

Implemented server: `neurodiscover/api_server.py` (FastAPI). See [API endpoints](api-endpoints).

No MongoDB required. If you mirror to Atlas, use field names from the MongoDB mapping table in [Database schema](database). Collection: **`evidence`**, not `papers`.

---

## GET /api/discover/parkinsons

{: .highlight }
**Legacy route name** — returns subgroups and connections from the current database regardless of configured indication.

Returns disease overview, subgroups, and treatment connections.

### JSON shape

```json
{
  "disease": "Parkinson's Disease",
  "subgroups": [
    {
      "subgroupId": 1,
      "name": "GBA-mutation PD",
      "definingFeatures": "...",
      "evidenceCount": 2
    }
  ],
  "treatmentConnections": [
    {
      "connectionId": 1,
      "subgroup": "GBA-mutation PD",
      "mechanism": "lysosomal dysfunction",
      "treatment": "GCase activation",
      "evidenceStrength": null,
      "commercialPotential": null,
      "confidence": null
    }
  ],
  "recommendation": {}
}
```

### SQL — subgroups

```sql
SELECT s.subgroup_id, s.name, s.defining_features, s.notes,
       COUNT(DISTINCT se.evidence_id) AS evidence_count
FROM subgroups s
LEFT JOIN subgroup_evidence se ON se.subgroup_id = s.subgroup_id
GROUP BY s.subgroup_id;
```

### SQL — treatment connections

```sql
SELECT tc.connection_id, s.name AS subgroup, tc.mechanism, tc.treatment,
       tc.evidence_strength, tc.commercial_potential
FROM treatment_connections tc
JOIN subgroups s ON s.subgroup_id = tc.subgroup_id;
```

---

## GET /api/agents

Agent trace for the dashboard pipeline cards.

### JSON shape

```json
{
  "runId": "a1b2c3d4",
  "steps": [
    {
      "agentName": "Literature Synthesis Agent",
      "stepOrder": 1,
      "summary": "Pulled 10 raw sources via BioMCP for configured disease query.",
      "payload": { "since_year": 2022, "incremental": false },
      "createdAt": "2026-06-01 12:00:00"
    }
  ]
}
```

### SQL — latest run trace

```sql
SELECT run_id, agent_name, step_order, summary, payload, created_at
FROM agent_outputs
WHERE run_id = (SELECT run_id FROM agent_outputs ORDER BY output_id DESC LIMIT 1)
ORDER BY output_id;
```

---

## GET /api/recommendations

Ranked recommendations from Agent 6.

### JSON shape

```json
{
  "recommendations": [
    {
      "subgroup": "GBA-mutation PD",
      "treatment": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "tier": "Prioritize",
      "rationale": "..."
    }
  ]
}
```

### SQL

```sql
SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
       tc.mechanism, tc.evidence_strength, tc.commercial_potential
FROM recommendations r
LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
ORDER BY r.confidence DESC;
```

---

## POST /api/run-discovery

Trigger the agent pipeline (`orchestrator.py`).

**Request:**

```json
{ "mode": "demo", "query": null, "max_papers": 150 }
```

`mode`: `demo` | `scan` | `full` | `agents-only`

**agents-only** — skip literature pull; run agents 2–6 on existing evidence. Used automatically by `make dashboard` when `SUPABASE_DATABASE_URL` is set. Optional `max_papers` cap (API minimum 10; orchestrator accepts `0` = all rows).

**Response:**

```json
{
  "run_id": "a1b2c3d4",
  "recommendations": [{ "subgroup": "...", "treatment": "...", "mechanism": "...", "confidence": 75.7, "tier": "Monitor", "rationale": "..." }],
  "agent_outputs": [{ "agentName": "Literature Synthesis Agent", "stepOrder": 1, "summary": "...", "createdAt": "..." }],
  "steps": [],
  "synthetic_cohort": [{ "patient_id": "Patient A", "subgroup": "...", "confidence": 82.5, "is_synthetic": true }],
  "runStats": {
    "mode": "demo",
    "maxPapersRequested": 10,
    "processed": { "literature": 5, "trial": 4, "grant": 0, "total": 9 },
    "databaseTotals": { "literature": 228, "trial": 39, "grant": 40, "total": 307 },
    "added": { "literature": 0, "trial": 0, "grant": 0, "total": 0 }
  }
}
```

`steps` is an alias of `agent_outputs`.

---

## Dashboard read helpers (API-only mode — no browser Supabase keys)

Used when the frontend does not set `SUPABASE_URL` / `SUPABASE_ANON_KEY`.

### GET /api/stats

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

### GET /api/run-stats?run_id=a1b2c3d4

Same `runStats` object shape as in `POST /api/run-discovery` (for revisiting a past run in the UI).

### GET /api/evidence?offset=0&limit=15

```json
{ "items": [{ "sourceType": "literature", "title": "...", "accessStatus": "open" }], "total": 307, "offset": 0, "limit": 15 }
```

### GET /api/runs?limit=5

```json
{
  "runs": [{
    "runId": "abc123",
    "steps": 6,
    "startedAt": "...",
    "mode": "demo",
    "recommendations": 5,
    "syntheticProfiles": 5,
    "status": "Complete",
    "evidenceNote": "5 papers (demo)"
  }]
}
```

### GET /api/agents?run_id=abc123

Same shape as **GET /api/agents** below; optional `run_id` query param.

### GET /api/synthetic-cohort?run_id=abc123

Ephemeral Synthea-style demo profiles (not stored in DB).

```json
{
  "run_id": "abc123",
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
  ]
}
```

`POST /api/run-discovery` returns the same `synthetic_cohort` array plus `agent_outputs` (alias of `steps`).

---

## Quick verify

**Local (no Supabase keys):**

```bash
cd neurodiscover
python3 cli.py build          # local neurodiscover.db only
python3 cli.py validate
python3 api_server.py         # port 5000
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/recommendations
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":10}'
```

**Team Supabase:** set `SUPABASE_DATABASE_URL` in `.env`, **do not** run `build`, then `validate`, `api_server.py`, and the same `curl` lines.

See [`neurodiscover/frontend/quickstart.md`](../../neurodiscover/frontend/quickstart.md).

---

## Evidence detail (optional endpoint)

For citation panels on the dashboard:

```sql
SELECT source_type, source_id, title, evidence_snippet, url, access_status
FROM evidence
WHERE evidence_id = ?;
```

`access_status` values: `open`, `abstract_only`, `restricted` — show a badge in the UI.
