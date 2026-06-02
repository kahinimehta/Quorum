# Contributing to Quorum / NeuroDiscover

## Quick start

```bash
git clone <repo-url>
cd Quorum/neurodiscover
pip install -r requirements.txt
cp .env.example .env          # add keys for your role
python3 cli.py build
python3 cli.py validate
```

## What to read by role

| Role | Document |
|------|----------|
| Everyone | [`AGENTS.md`](AGENTS.md) |
| Database / schema | [`docs/DATABASE.md`](docs/DATABASE.md) |
| Agent authors (Person 4) | [`docs/AGENT_IO.md`](docs/AGENT_IO.md) — new agents under `neurodiscover/agents/` |
| Backend (Person 2) | [`docs/BACKEND_QUERIES.md`](docs/BACKEND_QUERIES.md), [`docs/PERSON2_BACKEND.md`](docs/PERSON2_BACKEND.md), [`queries.sql`](queries.sql) |
| Shared Supabase | [`docs/SUPABASE.md`](docs/SUPABASE.md) |

## Database rules

- **In git:** `schema.sql`, `schema.pg.sql`, `seed_data.json` — reproducible contract.
- **Not in git:** `neurodiscover.db`, `.env`, `SUPABASE_DATABASE_URL` — never commit secrets or `.db` files.
- **Team live DB:** Supabase when `SUPABASE_DATABASE_URL` is set — see [`docs/SUPABASE.md`](docs/SUPABASE.md).
- **Parallel testing (local):** `export NEURODISCOVER_DB=/tmp/yourname.db` then `python3 cli.py build`.

## Before opening a PR

1. `python3 cli.py validate` passes from `neurodiscover/`.
2. If you changed columns, update `docs/DATABASE.md` and `docs/AGENT_IO.md`.
3. Do not commit API keys or `.db` files.

## Team channel blurb (copy-paste)

> DB contract is in **Quorum/docs/DATABASE.md**. Build with `cd neurodiscover && python3 cli.py build`. Table is **evidence**, not papers. Do not commit `.db` files. Agent I/O: **docs/AGENT_IO.md**.
