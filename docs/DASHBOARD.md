# NeuroDiscover Dashboard Architecture

Single-page dashboard: `neurodiscover/frontend/index.html` (vanilla HTML/CSS/JS, no build step).

## Data flow

**Default (no Supabase keys):** browser → API → SQLite or team Postgres (via `SUPABASE_DATABASE_URL` on the server only).

**Optional:** browser → Supabase anon client for read-only panels (parallel to API).

```mermaid
flowchart LR
  Browser[Browser dashboard]
  API[api_server.py :5000]
  DB[(SQLite or Postgres)]
  Orch[orchestrator.py]
  Agents[Agents 1-6 + cli.py]
  SB[(Supabase — optional direct reads)]

  Browser -->|GET /api/* reads| API
  Browser -.->|optional SELECT| SB
  Browser -->|POST /api/run-discovery| API
  API --> DB
  API --> Orch
  Orch --> Agents
  Agents --> DB
```

## Read path (Supabase JS SDK)

The frontend uses `@supabase/supabase-js` from CDN with the **anon key** for:

| Panel | Tables |
|-------|--------|
| DB status tiles | `evidence` (count by `source_type`), `subgroups` |
| Subgroup chips | `subgroups`, `subgroup_evidence` |
| Recent runs | `agent_outputs` (group by `run_id`) |
| Confidence bars | `treatment_connections` + `subgroups` |
| Top recommendations | `recommendations` |
| Agent timeline | `agent_outputs` |
| Evidence table | `evidence` (paginated) |

If Supabase URL/key are missing (**no keys required**), the UI uses API-only mode:

| Panel | API route |
|-------|-----------|
| DB tiles | `GET /api/stats` |
| Subgroups / confidence bars | `GET /api/discover/parkinsons` |
| Recommendations | `GET /api/recommendations` |
| Recent runs | `GET /api/runs` |
| Agent timeline | `GET /api/agents?run_id=` |
| Evidence table | `GET /api/evidence?offset=&limit=` |

Local setup: unset `SUPABASE_DATABASE_URL`, run `python3 cli.py build` once, then `python3 api_server.py`.

## Synthetic cohort layer (visualization only)

After Agent 6 (Conclusion Update), `synthetic_cohort.generate_synthetic_cohort(run_id, conn)` builds **Patients A–E** — one fictional profile per subgroup, ordered by confidence.

| Property | Detail |
|----------|--------|
| Data sources | `subgroups.defining_features`, `recommendations`, `treatment_connections` |
| Storage | **None** — not written to Postgres/SQLite |
| Privacy | `is_synthetic: true`, `phi_free: true` on every profile; UI labels cannot be hidden |
| Style | Synthea-inspired demo constructs for judges/stakeholders |

**API**

- Included in `POST /api/run-discovery` → `synthetic_cohort[]`
- `GET /api/synthetic-cohort?run_id=<id>` regenerates the same shape

**UI (Discovery Dashboard — v2 layout)**

- **Header + KPI strip:** evidence counts and connection total
- **Pipeline block:** data inputs → numbered agents → three output targets
- **Three columns:** Synthetic Cohort | Ranked Outputs | Research Hypotheses (+ continuous update)
- **Audit row:** agent trace + evidence library

See [`../neurodiscover/frontend/MOCKUP_V2.md`](../neurodiscover/frontend/MOCKUP_V2.md) for mockup PDF parity notes.

No HIPAA scope: no real records, no PHI, no clinical identifiers.

## Write / run path (Flask API)

| Action | Endpoint | Backend |
|--------|----------|---------|
| Run full / demo / scan | `POST /api/run-discovery` | `orchestrator.run()` |

Body: `{ "mode": "demo"|"scan"|"full", "query?", "max_papers?" }`  
Response: `{ "run_id", "recommendations", "steps" }`

Orchestrator:

- **demo / scan** — `cli.py` subprocess (literature only), then agents 2–6 in-process + DB persist
- **full** — `literature_agent.run()` (+ optional grants), then agents 2–6

Agent 1 owns the canonical `run_id` (`scan_state.last_run_id` or latest literature `agent_outputs` row). Agents 2–6 log to the same `run_id`.

## Confidence scoring

On `treatment_connections` and `recommendations`:

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Tier | Rule |
|------|------|
| Prioritize | confidence ≥ 80 |
| Monitor | 65 ≤ confidence < 80 |
| Reject | confidence < 65 |

In-process agents score 0–10; the orchestrator scales to **0–100** when writing to the DB.

## Quick verify

**One command** (word: **`dashboard`**):

```bash
cd neurodiscover
make dashboard
```

Opens API + UI and runs the offline demo pipeline. Browser: http://127.0.0.1:8080

**Team Supabase:** set `SUPABASE_DATABASE_URL` in `.env`, skip `build`, run `validate` + `api_server.py`, same `curl` commands. Do not run `cli.py build` on the shared DB.

Full step-by-step: [`../neurodiscover/frontend/QUICKSTART.md`](../neurodiscover/frontend/QUICKSTART.md).

## Related docs

- API JSON shapes: [`BACKEND_QUERIES.md`](BACKEND_QUERIES.md)
- Agent writes: [`AGENT_IO.md`](AGENT_IO.md)
- Setup + verify: [`../neurodiscover/frontend/QUICKSTART.md`](../neurodiscover/frontend/QUICKSTART.md)
