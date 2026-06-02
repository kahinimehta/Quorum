# Supabase setup — shared live database (free tier)

Use this when the team needs **one database** that updates from multiple laptops until and during the hackathon.

**Person 2 (backend)** connects with the same `SUPABASE_DATABASE_URL` (Node `pg`, Python `psycopg`, or Supabase JS client).

## 1. Create project (free)

1. Sign up at [supabase.com](https://supabase.com) → **New project**.
2. Save the database password.
3. **Project Settings → Database → Connection string → URI** (mode: Transaction pooler recommended).
4. Copy the `postgresql://...` URL.

Share the URL with the team via **1Password / Discord** — **never commit it to git**.

## 2. Apply schema (once)

**Option A — SQL Editor (easiest)**

1. Supabase dashboard → **SQL Editor** → New query.
2. Paste contents of [`neurodiscover/schema.pg.sql`](../Quorum/neurodiscover/schema.pg.sql) (or `schema.pg.sql` in this repo).
3. Run.

**Option B — CLI**

```bash
cd neurodiscover   # or Quorum/neurodiscover
cp .env.example .env   # paste SUPABASE_DATABASE_URL
pip install -r requirements.txt
python3 cli.py init-supabase
python3 cli.py build
python3 cli.py validate
```

## 3. Team `.env`

```bash
SUPABASE_DATABASE_URL=postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@...
```

Unset `SUPABASE_DATABASE_URL` to fall back to local `neurodiscover.db` for offline work.

## 4. Day-to-day commands (same as SQLite)

```bash
cd neurodiscover
python3 cli.py scan --max 5    # incremental literature (shared DB)
python3 cli.py pull --max 10   # larger backfill
python3 cli.py show evidence
python3 cli.py validate
```

Cron on any machine (keeps data live until Saturday):

```bash
0 */6 * * * cd /path/to/Quorum/neurodiscover && /usr/bin/python3 cli.py scan --max 5
```

## 5. Person 2 — backend connection

**Node (Express):**

```javascript
import pg from 'pg';
const pool = new pg.Pool({ connectionString: process.env.SUPABASE_DATABASE_URL, ssl: { rejectUnauthorized: false } });
```

**Python (Flask):**

```python
import psycopg
from psycopg.rows import dict_row
conn = psycopg.connect(os.environ["SUPABASE_DATABASE_URL"], row_factory=dict_row)
```

Use queries from [`queries.sql`](../queries.sql) and [`BACKEND_QUERIES.md`](BACKEND_QUERIES.md). Table names are identical to SQLite (`evidence`, not `papers`).

**Optional:** Supabase **Realtime** on `agent_outputs` for a live dashboard without polling.

## 6. Free tier notes

- Enough storage/rows for hackathon demo.
- Project may **pause after inactivity** — open the dashboard Friday before Saturday to wake it.
- LLM cost (Nebius) is separate; `scan --max 5` limits Nebius calls.

## 7. Rebuild demo seed on shared DB

**Warning:** `cli.py build` **truncates all tables** on Supabase and reloads `seed_data.json`. Coordinate with the team before running on a live DB everyone uses.

For additive-only literature pulls, use `scan` / `pull` instead of `build`.
