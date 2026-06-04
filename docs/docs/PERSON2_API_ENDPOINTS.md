# Person 2 API Endpoints

Backend: `neurodiscover/api_server.py` (FastAPI, port **5000**).

Connects the dashboard to **SQLite** (default, no keys) or **Supabase Postgres** when `SUPABASE_DATABASE_URL` is set in `.env`.

## Safety

- **Never** call `cli.py build` when `.env` points at the team Supabase DB (truncates all tables).
- `POST /api/run-discovery` runs the orchestrator and **writes** scores, recommendations, and `agent_outputs`.
- All other routes are read-only.

## Environment

| Variable | Required? | Purpose |
|----------|-----------|---------|
| `SUPABASE_DATABASE_URL` | No | Team Postgres (Session pooler URI). Omit for local `neurodiscover.db`. |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | No | Browser-only direct reads; API mode works without them. |

## Contract routes

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | DB label + `supabaseConfigured` |
| GET | `/api/discover/parkinsons` | Subgroups + treatment connections |
| GET | `/api/recommendations` | Ranked list |
| GET | `/api/agents` | Latest trace; `?run_id=` for a specific run |
| POST | `/api/run-discovery` | Body: `{ mode, query?, max_papers? }` |

## Dashboard helpers (no browser Supabase keys)

| Method | Path |
|--------|------|
| GET | `/api/stats` |
| GET | `/api/evidence?offset=&limit=` |
| GET | `/api/runs?limit=` |

JSON shapes: [`BACKEND_QUERIES.md`](../BACKEND_QUERIES.md).

## Quick verify

```bash
cd neurodiscover
pip install -r requirements.txt
python3 cli.py build    # local only — skip if using team Supabase URI
python3 cli.py validate
python3 api_server.py
```

```bash
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/recommendations
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":10}'
```

Dashboard UI: [`neurodiscover/frontend/QUICKSTART.md`](../../neurodiscover/frontend/QUICKSTART.md).
