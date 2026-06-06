# NeuroDiscover (Quorum) — agent context

> **🟢 DB STATUS: LIVE.** Supabase already holds **307 real evidence rows** (228 papers,
> 39 trials, 40 NIH grants), plus the 5 subgroups and their evidence links. **Just set the
> Session-pooler `SUPABASE_DATABASE_URL` (see [`docs/developer-reference/supabase.md`](docs/developer-reference/supabase.md)) and
> `SELECT` — the data is ready to query.** Do **NOT** run `cli.py build` (it truncates every
> table); use `cli.py scan` / `pull` only to *add* more evidence.

Multi-agent system for **commercial development discovery**: hidden patient subgroups,
subgroup → treatment connections, and ranked portfolio opportunities —
`confidence = evidence_strength*0.55 + commercial_potential*0.45`.

This file covers the **data layer + Literature Synthesis Agent** (Ayelet's part:
Person 3 data engineer + one Person 4 agent). Other agents are teammates' work
but all share the database below.

## Documentation

| Doc | Purpose |
|-----|---------|
| [`docs/developer-reference/database.md`](docs/developer-reference/database.md) | Schema — tables, columns, SQLite vs Postgres |
| [`docs/developer-reference/agent-io.md`](docs/developer-reference/agent-io.md) | Agent reads/writes |
| [`docs/developer-reference/backend-queries.md`](docs/developer-reference/backend-queries.md) | API SQL + JSON shapes |
| [`queries.sql`](queries.sql) | Copy-paste SELECTs |
| [`docs/developer-reference/supabase.md`](docs/developer-reference/supabase.md) | Team shared DB |
| [`docs/developer-reference/person2-backend.md`](docs/developer-reference/person2-backend.md) | Supabase + FastAPI |
| [`docs/dashboard.md`](docs/dashboard.md) | Dashboard UI |
| [`docs/developer-reference/dashboard-api.md`](docs/developer-reference/dashboard-api.md) | Dashboard + API |
| [`docs/developer-reference/api-endpoints.md`](docs/developer-reference/api-endpoints.md) | FastAPI routes |
| [`docs/developer-reference/validation.md`](docs/developer-reference/validation.md) | Extraction QA |
| [neurodiscover.github.io](https://neurodiscover.github.io) | Public docs site |
| [`neurodiscover/frontend/quickstart.md`](neurodiscover/frontend/quickstart.md) | Run UI in &lt; 5 min |

**Canonical store:** SQLite locally, or **Supabase Postgres** when `SUPABASE_DATABASE_URL` is set. Table is **`evidence`**, not `papers`.

## How to run
```bash
cd neurodiscover
pip install -r requirements.txt
cp .env.example .env          # SUPABASE_DATABASE_URL and/or NEBIUS_*
# Team shared DB (optional):
# python3 cli.py init-supabase && python3 cli.py build
python3 cli.py build           # local SQLite only — never when SUPABASE_DATABASE_URL is set
python3 cli.py validate        # FK / schema sanity checks
python3 cli.py demo            # offline literature-agent run (safe demo path)
python3 cli.py pull            # two-stage: PubMed (+ optional bioRxiv) + trials
python3 cli.py pull --max 150  # published papers (default max)
python3 cli.py pull --include-preprints 50   # also pull bioRxiv preprints
python3 cli.py pull --with-fulltext          # OA Methods/Results/Discussion excerpts
python3 cli.py enrich-with-fulltext --limit 50
python3 cli.py pull --query "GBA GCase lysosomal"
python3 cli.py pull-grants     # NIH RePORTER grants into evidence
python3 cli.py scan --max 5    # incremental scan (skips LLM for known source_ids)
python3 cli.py show [table]    # inspect tables
python3 cli.py query "SQL"     # run a read query
```

## Dashboard (one command: `dashboard`)

```bash
cd neurodiscover
make dashboard
# → launcher prints Open: URL (UI :8080/?api=... ; Ctrl+C to stop)
```

Same as `python3 cli.py dashboard` or `./dashboard`. Opens the browser automatically (`--no-browser` to skip). UI has three tabs: Steps 1–2 pipeline; **Step 3** static CUA grant proposal (`graded6`, collapsible sections, not run-scoped).

- **Local:** leave `SUPABASE_DATABASE_URL` unset — builds seed DB, runs demo (`max_papers=10`).
- **Team Supabase:** set `SUPABASE_DATABASE_URL` — skips `build`, runs **agents-only** (agents 2–6 on all existing evidence).

| Doc | Purpose |
|-----|---------|
| [`docs/dashboard.md`](docs/dashboard.md) | Run the UI locally |
| [`docs/developer-reference/dashboard-api.md`](docs/developer-reference/dashboard-api.md) | Architecture + API map |
| [`neurodiscover/frontend/quickstart.md`](neurodiscover/frontend/quickstart.md) | Step-by-step |
| [`docs/developer-reference/backend-queries.md`](docs/developer-reference/backend-queries.md) | API JSON shapes |

## Architecture: 6 agents, database is the blackboard
The pipeline runs in order. Each agent READS what the previous wrote and WRITES
its own table. The backend serves the final tables to the dashboard.

| # | Agent | Reads | Writes |
|---|-------|-------|--------|
| 1 | Literature Synthesis | external: PubMed/bioRxiv (E-utilities/API or MCP) + trials via BioMCP | `evidence`, `subgroup_evidence`, `scan_state` — code: `agents/literature_agent.py`, `ingestion/published_pull.py` |
| 2 | Patient Subgroup | `evidence` | `subgroups` |
| 3 | Treatment Connection | `subgroups`, `evidence` | `treatment_connections`, `connection_evidence` |
| 4 | Evidence Scoring (skeptic) | `treatment_connections`, `evidence` | `evidence_strength` col + `agent_outputs` |
| 5 | Commercial Discovery | scored connections (in-memory from Agent 4) | `commercial_potential` col + `agent_outputs` |
| 6 | Conclusion Update | scored `treatment_connections` | `recommendations` (orchestrator) · optional `cua/` NIH proposal (read-only, local files) |

Every agent appends one row to `agent_outputs` (run_id, step_order, summary) as it
runs. The dashboard reads `agent_outputs` to show the "agent trace".

## Database (SQLite or Supabase)
Schema is in `neurodiscover/schema.sql` (SQLite) and `neurodiscover/schema.pg.sql` (Postgres). See [`docs/developer-reference/database.md`](docs/developer-reference/database.md).

- `evidence` — one row per source. `source_type` is `literature` | `trial` | `grant`.
  Includes `doi`, `access_status`, `access_type` (`published_oa` | `published_paywalled` | `preprint`), `is_preprint`.
  `UNIQUE(source_type, source_id)` dedups re-pulls.
- `subgroups` — the patient subgroups.
- `treatment_connections` — subgroup -> mechanism -> treatment, plus score columns.
- `connection_evidence`, `subgroup_evidence` — many-to-many join tables.
- `agent_outputs` — append-only run trace.
- `recommendations` — final ranked output.
- `scan_state` — singleton tracking last literature scan (incremental mode).

## Conventions (important)
- **Do not rename columns** without updating `schema.sql`, `schema.pg.sql`, and [`docs/developer-reference/database.md`](docs/developer-reference/database.md). Backend reads `evidence` (NOT `papers`).
- **Never invent PMIDs / NCT ids.** Seed `source_id`s are placeholders (`DEMO-*`).
  The literature agent backfills real ids via `pull`. Do not present DEMO ids as real.
- **Demo mode is the safe path.** Never run a live API call live on stage; pre-run
  `pull` to populate the DB, then demo from it.
- **Incremental scan saves LLM cost:** `cli.py scan` skips Nebius for known source_ids.

## External tools
- BioMCP (`biomcp-python`): unified PubMed + ClinicalTrials.gov access. CLI:
  `biomcp article search --disease "your condition"`, `biomcp trial search --condition ...`.
- Nebius / Ollama: `EXTRACT_BACKEND=nebius|ollama|none` for structured extraction (NEBIUS_* or OLLAMA_*).
- `cli.py pull --query` / `--prompt`: passes `--keyword` to BioMCP while keeping `--disease` anchor.
- NIH RePORTER: grants via `cli.py pull-grants` (also optional in **full** pipeline mode when `pull_grants=true`).

## Anara-inspired patterns (not a runtime dependency)
Literature agent borrows: unified PubMed+trial search, `access_status` flags,
two-step fetch (search → get abstract), no hallucinated ids, distilled DB columns only.
