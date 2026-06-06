---
layout: default
title: Guides
nav_order: 12
description: "CLI, API verification, and developer setup"
---

# Developer guides

Run, verify, and extend NeuroDiscover.

---

## Dashboard

**pip:**

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
python3 --version          # must be 3.10.x – 3.12.x
pip install -r requirements.txt
cp .env.example .env
make dashboard    # same as: python3 cli.py dashboard
```

**conda (empty environment):**

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
conda env create -f environment.yml
conda activate neurodiscover
cp .env.example .env
make dashboard
```

**Local SQLite:** builds seed DB if needed, runs demo pipeline (`max_papers=10`).  
**Team Supabase:** skips build, runs **agents-only** on existing evidence (connections + recommendations written automatically).

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

Use the API port from launcher output (default 5000).

```bash
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/recommendations
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"demo","max_papers":10,"wait":true}'
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
| `ANTHROPIC_API_KEY` | Optional — live CUA runs only (`cua/`) |
| `CUA_LIVE=1` | Optional — enable live LLM roles in CUA |

## CUA (optional grant proposal)

Dashboard **Step 3** shows a **static** bundled demo (`graded6`) with hero KPIs, audit status chips, jump-to nav, and a collapsible inlined report (Proposal open by default). To generate a new proposal from your DB:

```bash
cd cua && pip install -e .
export ANTHROPIC_API_KEY=... CUA_LIVE=1
python -m cua.nih.run_db --db "$SUPABASE_DATABASE_URL" --run-id my-run --capture-content
```

See [Conclusion Update](workflow/conclusion-update#cua-package-optional--nih-grant-proposal) and `cua/README.md`.

See [Supabase setup](developer-reference/supabase) and [Team env sharing](developer-reference/team-env-sharing).

See [Developer reference](developer-reference/) for schema, agent I/O, and API docs.

## Site publishing

How to publish this docs site to **https://neurodiscover.github.io** — see [Site publishing](pages-setup).
