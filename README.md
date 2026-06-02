# Quorum — NeuroDiscover AI

Hackathon project: continuous discovery of Parkinson's disease patient subgroups and treatment connections.

## Start here

| Audience | Document |
|----------|----------|
| Cursor / coding agents | [`AGENTS.md`](AGENTS.md) |
| Humans onboarding | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| Database contract | [`docs/DATABASE.md`](docs/DATABASE.md) |

**Storage:** SQLite locally, or **Supabase Postgres** for the team shared DB (`SUPABASE_DATABASE_URL`). Not MongoDB — the working doc's `papers` collection maps to **`evidence`**. See [`docs/DATABASE.md`](docs/DATABASE.md) and [`docs/SUPABASE.md`](docs/SUPABASE.md).

## Build the database

```bash
cd neurodiscover
pip install -r requirements.txt
cp .env.example .env
python3 cli.py build
python3 cli.py validate
python3 cli.py demo    # safe offline demo
```

## Repo layout

```
Quorum/
  AGENTS.md              # agent instructions (read first)
  docs/                  # DATABASE, AGENT_IO, SUPABASE, BACKEND_QUERIES
  queries.sql            # SQL for Person 2
  neurodiscover/         # Python package: schema, cli, agents
    schema.sql
    cli.py
    literature_agent.py
    agents/              # Person 4 agent modules
    models/schemas.py    # API DTOs (not the DB schema)
```

## Team

See the Quorum working doc for role assignments (Person 1–5).
