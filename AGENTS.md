# NeuroDiscover (Quorum) — agent context

Multi-agent system for the NextGen BioAgents Hackathon. It discovers hidden
Parkinson's disease patient subgroups and subgroup -> treatment connections,
then ranks them by `confidence = evidence_strength*0.55 + commercial_potential*0.45`.

This file covers the **data layer + Literature Synthesis Agent** (Ayelet's part:
Person 3 data engineer + one Person 4 agent). Other agents are teammates' work
but all share the database below.

## Team contract docs (read before coding)

| Doc | Audience |
|-----|----------|
| [`docs/DATABASE.md`](docs/DATABASE.md) | Everyone — schema, SQLite vs MongoDB, field ownership |
| [`docs/AGENT_IO.md`](docs/AGENT_IO.md) | Person 4 — what each agent reads/writes |
| [`docs/BACKEND_QUERIES.md`](docs/BACKEND_QUERIES.md) | Person 2 — API SQL + JSON shapes |
| [`queries.sql`](queries.sql) | Person 2 — copy-paste SELECTs |
| [`docs/SUPABASE.md`](docs/SUPABASE.md) | Team shared live DB (free tier) |
| [`docs/PERSON2_BACKEND.md`](docs/PERSON2_BACKEND.md) | Person 2 Supabase connection |
| [`docs/VALIDATION.md`](docs/VALIDATION.md) | Extraction QA after pull |

**Canonical store:** SQLite locally, or **Supabase Postgres** when `SUPABASE_DATABASE_URL` is set. Table is **`evidence`**, not `papers`.

## How to run
```bash
cd neurodiscover
pip install -r requirements.txt
cp .env.example .env          # SUPABASE_DATABASE_URL and/or NEBIUS_*
# Team shared DB (optional):
# python3 cli.py init-supabase && python3 cli.py build
python3 cli.py build           # local SQLite, or Supabase if URL is set
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

## Architecture: 6 agents, database is the blackboard
The pipeline runs in order. Each agent READS what the previous wrote and WRITES
its own table. The backend serves the final tables to the dashboard.

| # | Agent | Reads | Writes |
|---|-------|-------|--------|
| 1 | Literature Synthesis | external: PubMed/bioRxiv (E-utilities/API or MCP) + trials via BioMCP | `evidence`, `subgroup_evidence`, `scan_state` — code: `agents/literature_agent.py`, `ingestion/published_pull.py` |
| 2 | Patient Subgroup | `evidence` | `subgroups` |
| 3 | Treatment Connection | `subgroups`, `evidence` | `treatment_connections`, `connection_evidence` |
| 4 | Evidence Scoring (skeptic) | `treatment_connections`, `evidence` | `evidence_strength` col + `agent_outputs` |
| 5 | Commercial Discovery | `treatment_connections`; external: Tavily/RePORTER | `commercial_potential` col + `agent_outputs` |
| 6 | Conclusion Update | scored `treatment_connections` | `recommendations` |

Every agent appends one row to `agent_outputs` (run_id, step_order, summary) as it
runs. The dashboard reads `agent_outputs` to show the "agent trace".

## Database (SQLite or Supabase)
Schema is in `neurodiscover/schema.sql` (SQLite) and `neurodiscover/schema.pg.sql` (Postgres). See [`docs/DATABASE.md`](docs/DATABASE.md).

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
- **The schema is the team contract.** Do not rename columns without telling
  Person 2 (backend) and Person 4 (agents). Backend reads `evidence` (NOT `papers`).
- **Never invent PMIDs / NCT ids.** Seed `source_id`s are placeholders (`DEMO-*`).
  The literature agent backfills real ids via `pull`. Do not present DEMO ids as real.
- **Demo mode is the safe path.** Never run a live API call live on stage; pre-run
  `pull` to populate the DB, then demo from it.
- **Incremental scan saves LLM cost:** `cli.py scan` skips Nebius for known source_ids.

## External tools
- BioMCP (`biomcp-python`): unified PubMed + ClinicalTrials.gov access. CLI:
  `biomcp article search --disease "Parkinson disease"`, `biomcp trial search --condition ...`.
- Nebius / Ollama: `EXTRACT_BACKEND=nebius|ollama|none` for structured extraction (NEBIUS_* or OLLAMA_*).
- `cli.py pull --query` / `--prompt`: passes `--keyword` to BioMCP while keeping `--disease` anchor.
- Tavily: live web search for the Commercial Discovery agent (market/white-space signal).
- NIH RePORTER: free grants API for the commercial agent's "already funded?" check.

## Anara-inspired patterns (not a runtime dependency)
Literature agent borrows: unified PubMed+trial search, `access_status` flags,
two-step fetch (search → get abstract), no hallucinated ids, distilled DB columns only.
