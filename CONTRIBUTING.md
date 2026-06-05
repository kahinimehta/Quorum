# Contributing to Quorum / NeuroDiscover

## File naming (capitalization)

All **documentation** uses **lowercase kebab-case** filenames:

| OK | Not OK |
|----|--------|
| `docs/input.md` | `docs/INPUT.md`, `docs/Input.md` |
| `docs/developer-reference/agent-io.md` | `docs/AGENT_IO.md` |
| `neurodiscover/frontend/quickstart.md` | `QUICKSTART.md` |

**Exceptions (do not rename — tools depend on exact names):**

| File | Why |
|------|-----|
| `README.md` | GitHub repo homepage |
| `AGENTS.md` | Cursor / agent context |
| `CONTRIBUTING.md` | GitHub contributing guide |
| `docs/Gemfile`, `docs/Gemfile.lock` | Ruby Bundler |
| `neurodiscover/Makefile` | GNU Make |
| `neurodiscover/**/*.py` | Python imports (snake_case modules) |

When adding docs, use `docs/` or `docs/developer-reference/` with lowercase names. Update links if you rename a page.

---

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
| Database / schema | [`docs/developer-reference/database.md`](docs/developer-reference/database.md) |
| Agent authors (Person 4) | [`docs/developer-reference/agent-io.md`](docs/developer-reference/agent-io.md) — new agents under `neurodiscover/agents/` |
| Backend (Person 2) | [`docs/developer-reference/backend-queries.md`](docs/developer-reference/backend-queries.md), [`docs/developer-reference/person2-backend.md`](docs/developer-reference/person2-backend.md), [`queries.sql`](queries.sql) |
| Dashboard | [`docs/dashboard.md`](docs/dashboard.md), [neurodiscover.github.io](https://neurodiscover.github.io) |
| Shared Supabase | [`docs/developer-reference/supabase.md`](docs/developer-reference/supabase.md) |

## Database rules

- **In git:** `schema.sql`, `schema.pg.sql`, `seed_data.json` — reproducible contract.
- **Not in git:** `neurodiscover.db`, `.env`, `SUPABASE_DATABASE_URL` — never commit secrets or `.db` files.
- **Team live DB:** Supabase when `SUPABASE_DATABASE_URL` is set — see [`docs/developer-reference/supabase.md`](docs/developer-reference/supabase.md).
- **Parallel testing (local):** `export NEURODISCOVER_DB=/tmp/yourname.db` then `python3 cli.py build`.

## Before opening a PR

1. `python3 cli.py validate` passes from `neurodiscover/`.
2. If you changed columns, update `docs/developer-reference/database.md` and `docs/developer-reference/agent-io.md`.
3. Do not commit API keys or `.db` files.

## Team channel blurb (copy-paste)

> DB contract is in **Quorum/docs/developer-reference/database.md**. Build with `cd neurodiscover && python3 cli.py build`. Table is **evidence**, not papers. Do not commit `.db` files. Agent I/O: **docs/developer-reference/agent-io.md**.
