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

**Pipeline modes (when to use which):** [Inputs — recommended workflow](input#recommended-workflow) · [Demo vs Rescore](input#demo-vs-rescore-no-live-pubmed) · [Incremental vs full](input#incremental-scan-vs-full-live-pull) · [Does full clear the DB?](input#does-full-clear-the-database) · [Run times](input#how-long-do-runs-take-ballpark)

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

## CUA — NIH grant proposal (Step 3)

Dashboard **Step 3** shows a **static** bundled demo (`graded6`) with hero KPIs (**corpus papers** = full pull, **verified papers** = top-K slice selected for drafting — see [Dashboard — Corpus vs verified papers](dashboard#corpus-vs-verified-papers)), **Jump to** nav (Proposal · Grant pipeline · Supporting details), and an inlined report: **The proposal** expanded at the top; **Grant pipeline** and **Pipeline trace & audit** each in their own collapsed block. Toolbar shows **`x/y obligations satisfied`**. Step 2 **ideal candidate profiles** and **ranked outputs** match **research hypotheses** column height and scroll when their content is longer. To generate a new proposal from your DB:

```bash
cd cua && pip install -e .
export ANTHROPIC_API_KEY=... CUA_LIVE=1
python -m cua.nih.run_db --db "$SUPABASE_DATABASE_URL" --run-id my-run --capture-content
```

See [Conclusion Update](workflow/conclusion-update#cua-package--nih-grant-proposal) and `cua/README.md`.

See [Supabase setup](developer-reference/supabase) and [Team env sharing](developer-reference/team-env-sharing).

See [Developer reference](developer-reference/) for schema, agent I/O, and API docs.

## Showcase (June 6, 2026)

| Audience | Start here |
|----------|------------|
| Judges / quick tour | [Home](index) → [Output examples](output) (Steps 1–3 screenshots) → [Dashboard demo tour](dashboard#demo-tour-3-min) → [Pipeline modes FAQ](input#recommended-workflow) → run `make dashboard` locally |
| Live demo | [Debugging — safe demo checklist](debugging#safe-demo-checklist-stage) — Step 2 for rankings; expand **Audit & provenance** for trace; finish on **Grant Proposal** (tab 3) |
| Architecture | [Workflow](workflow/) · [Design & engineering](design) |
| Team | [Team](team) |

**Live UI:** `cd neurodiscover && make dashboard` — three tabs; use **demo** mode on stage.  
**Docs site:** [neurodiscover.github.io](https://neurodiscover.github.io) (canonical; auto-deploys from `docs/` on push to `main`).

Refresh dashboard screenshots after UI changes:

```bash
cd neurodiscover
make dashboard --no-browser   # or running API :5000 + UI :8080
python3 scripts/capture_dashboard_screenshots.py
# → Step 2 overview captures .results-shell (centered column)
```

## Site publishing

How to publish this docs site to **https://neurodiscover.github.io** — see [Site publishing](pages-setup).
