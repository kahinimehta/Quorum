# Backend Query Guide — Person 2

**Database file:** `neurodiscover.db` (SQLite, repo root)  
**Full SQL:** [`queries.sql`](../queries.sql)  
**Schema:** [`DATABASE.md`](DATABASE.md)

## Connection (Flask example)

```python
import sqlite3
conn = sqlite3.connect("neurodiscover.db")
conn.row_factory = sqlite3.Row
```

No MongoDB required. If you mirror to Atlas, use field names from the MongoDB mapping table in `DATABASE.md`. Collection: **`evidence`**, not `papers`.

---

## GET /api/discover/parkinsons

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
      "summary": "Pulled 10 raw sources via BioMCP for Parkinson disease.",
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

`mode`: `demo` | `scan` | `full`

**Response:**

```json
{
  "run_id": "a1b2c3d4",
  "recommendations": [{ "subgroup": "...", "treatment": "...", "confidence": 75.7, "tier": "Monitor", "rationale": "..." }],
  "steps": [{ "agentName": "Literature Synthesis Agent", "stepOrder": 1, "summary": "...", "createdAt": "..." }]
}
```

---

## Dashboard read helpers (API-only mode — no browser Supabase keys)

Used when the frontend does not set `SUPABASE_URL` / `SUPABASE_ANON_KEY`.

### GET /api/stats

```json
{ "literature": 228, "trial": 39, "grant": 40, "subgroups": 5 }
```

### GET /api/evidence?offset=0&limit=15

```json
{ "items": [{ "sourceType": "literature", "title": "...", "accessStatus": "open" }], "total": 307, "offset": 0, "limit": 15 }
```

### GET /api/runs?limit=5

```json
{ "runs": [{ "runId": "abc123", "steps": 6, "startedAt": "..." }] }
```

### GET /api/agents?run_id=abc123

Same shape as **GET /api/agents** below; optional `run_id` query param.

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

See [`neurodiscover/frontend/QUICKSTART.md`](../neurodiscover/frontend/QUICKSTART.md).

---

## Evidence detail (optional endpoint)

For citation panels on the dashboard:

```sql
SELECT source_type, source_id, title, evidence_snippet, url, access_status
FROM evidence
WHERE evidence_id = ?;
```

`access_status` values: `open`, `abstract_only`, `restricted` — show a badge in the UI.
