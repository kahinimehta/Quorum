---
layout: default
title: Dashboard API
parent: Developer reference
nav_order: 6
---

# NeuroDiscover Dashboard

Single-page UI: `neurodiscover/frontend/index.html` (vanilla HTML/CSS/JS, no build step).

## Quick start

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
pip install -r requirements.txt
make dashboard
```

Opens **http://127.0.0.1:8080** in your default browser (`--no-browser` to skip). Press **Ctrl+C** to stop API + UI.

With **team Supabase** (`SUPABASE_DATABASE_URL` in `.env`), the same command skips `build` and runs **agents-only** before serving so connections and recommendations are populated on first load.

Details: [`../../neurodiscover/frontend/quickstart.md`](../../neurodiscover/frontend/quickstart.md).

## Data flow

**Default (no browser Supabase keys):** UI → FastAPI (`api_server.py` :5000) → SQLite or team Postgres (`SUPABASE_DATABASE_URL` on the server only).

**Optional:** set `SUPABASE_URL` + `SUPABASE_ANON_KEY` in the page or `localStorage` for direct read-only Supabase queries (parallel to the API).

```mermaid
flowchart LR
  Browser[Browser]
  API[api_server.py :5000]
  DB[(SQLite or Postgres)]
  Orch[orchestrator.py]
  Agents[Agents 1-6]

  Browser -->|GET /api/*| API
  Browser -->|POST /api/run-discovery| API
  API --> DB
  API --> Orch
  Orch --> Agents
  Agents --> DB
```

## UI layout

| Area | Content |
|------|---------|
| Header | DB status, evidence totals, synthetic cohort badge, run id |
| KPI strip + summary bar | Per-type counts; **this run** vs **in database** after a pipeline run |
| Run status strip | Ready / Running / Complete / Partial / Failed |
| **Agent pipeline stepper** | One agent **Running…** at a time during a run; **Done** / **Waiting…** for others; polls `GET /api/agents?run_id=` while POST is in flight |
| **Step 1** | Configure & run — pipeline mode (Rescore / Demo / Incremental / Full), disease, max papers, extraction; single run button |
| **Step 2** | Results — pipeline diagram, synthetic cohort, ranked outputs, hypotheses, audit trace, evidence table |

Timestamps display in **US Eastern** (`America/New_York`, labeled EST or EDT).

## API reads (no browser keys)

| Panel | Route |
|-------|--------|
| DB / KPI tiles | `GET /api/stats` |
| Subgroups / connections | `GET /api/discover/parkinsons` (legacy path; indication-agnostic) |
| Recommendations | `GET /api/recommendations?run_id=` |
| Recent runs | `GET /api/runs` |
| Per-run counts | `GET /api/run-stats?run_id=` |
| Agent trace | `GET /api/agents?run_id=` |
| Evidence table | `GET /api/evidence?offset=&limit=` |
| Synthetic patients | `GET /api/synthetic-cohort?run_id=` or included in run response |

## Pipeline run

| Action | Endpoint |
|--------|----------|
| Demo / scan / full / agents-only | `POST /api/run-discovery` |

Body (example): `{ "mode": "demo", "run_id": "abc12345", "max_papers": 10, "disease": "Parkinson's", "query": null, "with_fulltext": false, "pull_grants": true }`

Response includes: `run_id`, `recommendations`, `agent_outputs` (alias `steps`), `synthetic_cohort`, `runStats` (processed vs database totals).

Orchestrator modes:

- **demo / scan** — literature via `cli.py` subprocess, then agents 2–6 in-process (commits after each agent 2–6 step for live stepper)
- **agents-only** — no literature subprocess; agents 2–6 on existing DB evidence (`make dashboard` on Supabase)
- **full** — `literature_agent.run()` with client `run_id` (+ optional grants), then agents 2–6

**demo** caps literature rows used by downstream agents to `max_papers`. **agents-only** uses all evidence unless `max_papers` is set. **scan/full** agents use all evidence rows with subgroup (pull settings only affect step 1).

## Scoring (agents 4–5)

Evidence and commercial scores **scale with per-connection evidence count** (see [Evidence Scoring](../workflow/evidence-scoring) and [Commercial Discovery](../workflow/commercial-discovery)). Stored columns are 0–100; `recommendations.confidence` uses the same formula as the dashboard.

## Synthetic cohort

`generate_synthetic_cohort(run_id)` builds **Patients A–E** from `recommendations` + `subgroups`. Not stored in the DB. Every profile is labeled synthetic / no PHI.

## Confidence

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Tier | Rule |
|------|------|
| Prioritize | ≥ 80 |
| Monitor | 65–79 |
| Reject | < 65 |

## Related docs

- JSON shapes: [Backend queries](backend-queries)
- Endpoint list: [API endpoints](api-endpoints)
- Agent I/O: [Agent I/O](agent-io)
- Mockup notes (archived): [`../../neurodiscover/frontend/mockup-v2.md`](../../neurodiscover/frontend/mockup-v2.md)
