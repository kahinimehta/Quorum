# Person 2 — Backend API on Supabase

Quick handoff for Kahii / Alia building the Express/Flask API.

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

Full column list: [`DATABASE.md`](DATABASE.md).

## Endpoints → SQL

Copy from [`BACKEND_QUERIES.md`](BACKEND_QUERIES.md) and [`queries.sql`](../queries.sql).

Example discover payload shape:

```json
{
  "disease": "Parkinson's Disease",
  "subgroups": [],
  "treatmentConnections": [],
  "recommendation": {}
}
```

## Pydantic models

`neurodiscover/models/schemas.py` is for **API JSON** only. Map fields to SQL columns (e.g. `defining_features` in DB vs `description` in Pydantic) in your route handlers.

## Setup steps

1. Get `SUPABASE_DATABASE_URL` from Person 3 (Ayelet).
2. Confirm tables exist (Supabase Table Editor or run `cli.py validate`).
3. Implement four routes from the working doc using `queries.sql`.
4. Optional: Supabase Realtime on `agent_outputs` for live UI.

See [`SUPABASE.md`](SUPABASE.md) for project creation and schema apply.
