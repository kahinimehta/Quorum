# Quorum — NeuroDiscover AI

Hackathon project: continuous discovery of Parkinson's disease patient subgroups and treatment connections.

## Start here

| Audience | Document |
|----------|----------|
| Cursor / coding agents | [`AGENTS.md`](AGENTS.md) |
| Humans onboarding | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| **Project docs (web)** | **[neurodiscover.github.io](https://neurodiscover.github.io)** — Jekyll + Just the Docs ([source](docs/index.md)) |
| Database contract | [`docs/developer-reference/database.md`](docs/developer-reference/database.md) |

**Storage:** SQLite locally, or **Supabase Postgres** for the team shared DB (`SUPABASE_DATABASE_URL`). Not MongoDB — the working doc's `papers` collection maps to **`evidence`**. See [`docs/developer-reference/database.md`](docs/developer-reference/database.md) and [`docs/developer-reference/supabase.md`](docs/developer-reference/supabase.md).

## Build the database

```bash
cd neurodiscover
pip install -r requirements.txt
cp .env.example .env
python3 cli.py build
python3 cli.py validate
python3 cli.py demo    # safe offline demo
make dashboard       # local demo + API + UI (http://127.0.0.1:8080)
```

## Repo layout

```
Quorum/
  AGENTS.md
  docs/                  # Jekyll site (Just the Docs) → neurodiscover.github.io
  queries.sql
  neurodiscover/
    cli.py               # entry point — run all commands from here
    schema.sql, schema.pg.sql, seed_data.json
    db.py, seed.py, paths.py, db_validate.py
    agents/
      literature_agent.py    # Agent 1 (literature synthesis)
    ingestion/
      grants_pull.py         # NIH RePORTER grants
    validation/
      consistency.py, pubtator.py, spot_check.py, report.py
    scripts/
      export_team_keys.py
    models/
      schemas.py             # Person 2 API DTOs (not DB schema)
    api_server.py            # FastAPI dashboard backend (:5000)
    orchestrator.py          # Agents 1→6 pipeline for POST /api/run-discovery
    frontend/
      index.html             # Dashboard UI
```

Dashboard docs: [`docs/dashboard.md`](docs/dashboard.md) (UI) · [`docs/developer-reference/dashboard-api.md`](docs/developer-reference/dashboard-api.md) (API contract).

## Team

See the Quorum working doc for role assignments (Person 1–5).
