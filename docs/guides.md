---
layout: default
title: Guides
nav_order: 8
description: "CLI, API verification, and developer setup"
---

# Developer guides

Run, verify, and extend NeuroDiscover.

---

## Dashboard

```bash
cd neurodiscover && make dashboard
```

## CLI (data & agents)

```bash
python3 cli.py build          # local DB only — truncates tables
python3 cli.py validate       # FK / schema checks
python3 cli.py demo             # offline literature agent
python3 cli.py scan --max 5     # incremental scan
python3 cli.py pull --max 150   # published papers
python3 cli.py pull-grants      # NIH RePORTER
```

{: .warning }
On the **team Supabase** database, do **not** run `build`. Set `SUPABASE_DATABASE_URL` and use `scan` / `pull` only.

## API verify

```bash
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/recommendations
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"demo","max_papers":5}'
```

## Environment

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `SUPABASE_DATABASE_URL` | Team Postgres (Session pooler) |
| `EXTRACT_BACKEND` | `nebius` \| `ollama` \| `none` |
| `NEBIUS_*` / `OLLAMA_*` | LLM extraction credentials |

See [Supabase setup](SUPABASE) and [Team env sharing](TEAM_ENV_SHARING).

## Contract documents

Developer reference pages (schema, agent I/O, validation):

- [Database schema](DATABASE)
- [Agent I/O](AGENT_IO)
- [Backend queries](BACKEND_QUERIES)
- [Validation](VALIDATION)
- [Literature pull](LITERATURE_PULL)

## Site publishing

How to publish this docs site to **https://neurodiscover.github.io** — see [Site publishing](pages-setup).
