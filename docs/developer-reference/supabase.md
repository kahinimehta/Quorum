---
layout: default
title: Supabase
parent: Developer reference
nav_order: 8
---

# Supabase setup — shared live database (free tier)

Use this when the team needs **one database** that updates from multiple laptops until and during the hackathon.

**Person 2 (backend)** connects with the same `SUPABASE_DATABASE_URL` (Node `pg`, Python `psycopg`).

**Person 5 (Next.js)** uses the **Framework** tab keys (`NEXT_PUBLIC_SUPABASE_*`) — not this Postgres URI.

## 1. Create project (free)

1. Sign up at [supabase.com](https://supabase.com) → **New project**.
2. Save the database password.
3. **Connect → Direct → Connection string** (in the UI).
4. Under **Connection method**, choose **Session pooler** (not Direct, not Transaction pooler).

| Method | Use for NeuroDiscover? |
|--------|-------------------------|
| **Session pooler** (port 5432, `aws-*-*.pooler.supabase.com`) | **Yes** — IPv4-friendly on free tier |
| Transaction pooler (port 6543) | No if UI says IPv6-only without paid add-on |
| Direct (`db.*.supabase.co`) | No on IPv4-only networks without paid IPv4 add-on |

Example shape (your region/ref will differ):

```bash
postgresql://postgres.brfjrctbzuwcpkdnaagf:[YOUR-PASSWORD]@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```

- User must be `postgres.<project-ref>` (not `postgres` alone).
- Host must be `*.pooler.supabase.com` (not `db.*.supabase.co`).
- URL-encode special characters in the password (`@` → `%40`, etc.).

Share the URI via **Discord / 1Password** — **never commit** `.env`.

## 2. Apply schema (once)

**Option A — SQL Editor**

1. Supabase dashboard → **SQL Editor** → New query.
2. Paste [`neurodiscover/schema.pg.sql`](../../neurodiscover/schema.pg.sql) → Run.

**Option B — CLI**

```bash
cd neurodiscover
cp .env.example .env   # paste Session pooler SUPABASE_DATABASE_URL
pip install -r requirements.txt
python3 cli.py init-supabase
python3 cli.py build
python3 cli.py validate
```

## 3. Team `.env`

```bash
# Python agents + cli.py + Person 2 backend
SUPABASE_DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-1-<region>.pooler.supabase.com:5432/postgres

# Next.js dashboard only (Framework tab / API Keys)
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
```

Unset `SUPABASE_DATABASE_URL` to use local `neurodiscover.db` offline.

## 4. Day-to-day commands

```bash
cd neurodiscover
python3 cli.py scan --max 5
python3 cli.py pull --max 10
python3 cli.py show evidence
python3 cli.py validate
```

Initial real evidence is loaded by the data engineer before demo; use `scan` for incremental updates.

## 5. Person 2 — backend connection

```javascript
import pg from 'pg';
const pool = new pg.Pool({
  connectionString: process.env.SUPABASE_DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});
```

```python
import psycopg
from psycopg.rows import dict_row
conn = psycopg.connect(os.environ["SUPABASE_DATABASE_URL"], row_factory=dict_row)
```

See [`queries.sql`](../../queries.sql) and [Backend queries](backend-queries). Table is **`evidence`**, not `papers`.

## 6. What to ignore in the Supabase UI

| UI item | For NeuroDiscover |
|---------|-------------------|
| **MCP** / “Connect your agent” / Copy prompt | Optional Cursor tooling only — not `agents/literature_agent.py` |
| `npx skills add supabase/agent-skills` | Optional — not required for the pipeline |
| **Enable IPv4 add-on** | Not needed if you use **Session pooler** |

## 7. Free tier notes

- Project may **pause after inactivity** — open the dashboard before demo day.
- **`cli.py build` truncates all tables** on Supabase — coordinate with the team; use `pull`/`scan` on a live DB.
