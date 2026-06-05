---
layout: default
title: Person 2 backend
parent: Developer reference
nav_order: 5
---

# Person 2 — Backend API on Supabase

Quick handoff for the dashboard API (`neurodiscover/api_server.py`, FastAPI).

## Connection

```bash
# .env (not in git)
SUPABASE_DATABASE_URL=postgresql://...
```

## Tables (not MongoDB `papers`)

| API concept | SQL table |
|-------------|-----------|
| Papers / sources | `evidence` |
| Subgroups | `subgroups` |
| Opportunities | `treatment_connections` |
| Agent trace | `agent_outputs` |
| Final ranking | `recommendations` |

Full column list: [Database schema](database).

## Endpoints → SQL

Copy from [Backend queries](backend-queries) and [`queries.sql`](../../queries.sql).

Example discover payload shape:

```json
{
  "disease": "Configured indication (from seed or pull)",
  "subgroups": [],
  "treatmentConnections": [],
  "recommendation": {}
}
```

## Pydantic models

`neurodiscover/models/schemas.py` is for **API JSON** only. Map fields to SQL columns (e.g. `defining_features` in DB vs `description` in Pydantic) in your route handlers.

## Setup steps

1. **Local / no keys:** omit `SUPABASE_DATABASE_URL`, run `python3 cli.py build`, then `python3 api_server.py`.
2. **Team Supabase:** get `SUPABASE_DATABASE_URL` from Person 3 — **do not** run `build` on shared DB.
3. Confirm tables: `python3 cli.py validate`.
4. Routes in `neurodiscover/api_server.py` — see [Backend queries](backend-queries) and [API endpoints](api-endpoints).

## Quick verify

```bash
cd neurodiscover
python3 api_server.py
curl -s http://127.0.0.1:5000/api/stats
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":10}'
```

Dashboard: [`../../neurodiscover/frontend/quickstart.md`](../../neurodiscover/frontend/quickstart.md). Architecture: [Dashboard API](dashboard-api).

See [Supabase](supabase) for project creation and schema apply.
