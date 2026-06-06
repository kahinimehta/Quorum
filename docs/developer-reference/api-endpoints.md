---
layout: default
title: API endpoints
parent: Developer reference
nav_order: 4
---

# Person 2 — API endpoints

Backend: `neurodiscover/api_server.py` (**FastAPI**, port **5000**).

The dashboard reads these routes when browser Supabase keys are unset. Full JSON shapes: [Backend queries](backend-queries). UI guide: [Dashboard API](dashboard-api).

## Safety

- **Never** run `cli.py build` when `.env` points at the team Supabase DB (truncates all tables).
- `POST /api/run-discovery` runs the orchestrator and **writes** scores, recommendations, and `agent_outputs`.
- All other routes are read-only.

## Routes

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | Status + `database` label |
| GET | `/api/discover/parkinsons` | Subgroups + treatment connections (legacy path; indication-agnostic) |
| GET | `/api/recommendations` | Ranked list; optional `?run_id=` |
| GET | `/api/agents` | Agent trace; optional `?run_id=` |
| GET | `/api/stats` | Evidence counts + `lastScanAt` |
| GET | `/api/evidence` | Paginated evidence (`offset`, `limit`) |
| GET | `/api/runs` | Recent runs (`limit`) |
| GET | `/api/run-stats` | Per-run processed vs DB totals; requires `run_id` |
| GET | `/api/run-discovery/status` | Poll async pipeline job; requires `run_id` |
| GET | `/api/synthetic-cohort` | Ephemeral profiles; requires `run_id` |
| GET | `/api/cua/demo` | Static bundled CUA summary (`graded6`; not run-scoped) |
| GET | `/cua-demo/graded6.html` | Pre-rendered CUA HTML report (served by API static mount) |
| POST | `/api/run-discovery` | Pipeline run. Default (`wait: false`): `{ "run_id", "status": "running", "accepted": true }`. With `wait: true`: full payload (`recommendations`, `agent_outputs`, `runStats`, `synthetic_cohort`) |

## Quick verify

```bash
cd neurodiscover
make dashboard   # local demo + UI — see frontend/quickstart.md
```

Or manually:

```bash
python3 cli.py build    # local only — skip on team Supabase
python3 cli.py validate
python3 api_server.py
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s 'http://127.0.0.1:5000/api/run-stats?run_id=YOUR_RUN_ID'
```
