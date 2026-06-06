---
layout: default
title: Inputs
nav_order: 4
description: "External sources, API requests, and database rows that feed the pipeline"
---

# Inputs

What NeuroDiscover consumes — external evidence sources, API request bodies, and the distilled database columns each agent reads.

---

## Dashboard — Step 1 (Configure & Run)

The UI maps directly to pipeline inputs: **one pipeline mode** (segmented control), keyword filter, max papers, pull options (full mode only), and extraction backend. A **single Run button** uses whichever mode is selected — there is no separate incremental-scan button.

![Step 1 — Configure & run pipeline](/assets/images/dashboard/step1-configure-run.png)
{: .doc-screenshot }

*Step 1 — pick a pipeline mode, optional keyword filter, then click the run button (label matches the selected mode).*

### Pipeline modes (Step 1)

| UI mode | API `mode` | What it does |
|---------|------------|--------------|
| **Rescore DB** | `agents-only` | Skip literature pull; run agents 2–6 on evidence already in the database (default on team Supabase). |
| **Demo sample** | `demo` | Offline; uses existing rows, no live PubMed pull; caps literature rows for agents 2–6. |
| **Incremental scan** | `scan` | Pull new papers/trials only; skip LLM for known source IDs; trace says **Incremental scan complete**; Recent runs evidence column tagged `incremental`. |
| **Full live pull** | `full` | Live PubMed + trials + optional preprints, full text, and NIH grants; trace says **Full live pull complete**; evidence column shows papers/trials stored. |

Preprint, full-text, and grant toggles apply only to **Full live pull**.

### Recommended workflow

```text
Full live pull   →  stock the library (first time or big refresh)
Incremental scan →  add new papers cheaply (ongoing)
Rescore DB       →  rerun rankings on same evidence (no PubMed)
Demo sample      →  stage / laptop demo only (small cap, no pull)
```

| Situation | Use |
|-----------|-----|
| Empty or thin DB | **Full live pull** (optionally preprints + grants) |
| Team DB already has 300+ rows | **Incremental scan** for updates; **Rescore** to refresh rankings |
| On stage / first laptop open | **Demo sample** (pre-run `make dashboard`) |
| Never on team Supabase | `cli.py build` — it **truncates** all tables |

`make dashboard` picks defaults for you: **local SQLite** → demo `max_papers=10`; **Supabase** → rescore with **no cap** (`max_papers=0` = full corpus).

---

### Demo vs Rescore (no live PubMed)

Both modes **skip live literature pull**. Agent 1 only logs a trace row; agents 2–6 compute subgroups, connections, scores, and recommendations.

| | **Demo sample** | **Rescore DB** |
|---|-----------------|----------------|
| API `mode` | `demo` | `agents-only` |
| Adds new papers? | No | No |
| Default `max_papers` | **10** (launcher + UI) | **0** (= all rows on Supabase) |
| Typical DB | Local seed (~43 rows) | Team Supabase (~300+) |
| Agent 1 trace | “Demo mode: using X of Y rows…” | “Agents-only: using X of Y rows…” |

**Mental models:** Demo = *quick tour with a small sample*. Rescore = *re-sort the full catalog without buying new books*.

---

### What `max_papers` does

**Max papers** caps **literature** rows passed to agents 2–6. **Trials and grants** are not capped — all tagged trial/grant rows still count.

Only rows with **subgroup tags** affect scoring; untagged papers sit in the DB but do not move confidence.

| Mode | How the cap applies |
|------|---------------------|
| **Demo** | Always uses your `max_papers` (minimum **10** in the API) |
| **Rescore** | `max_papers > 0` caps literature; **`0`** or UI **≥ 500** → **no cap** (full DB) |
| **Incremental / Full** | Caps the **pull** size; agents 2–6 then run on the **full** DB after ingest |

**Why Demo feels “stuck” when you raise max:** On the local seed DB there are only ~11 tagged literature rows. Changing 10 → 50 → 150 often changes nothing — you already hit the ceiling. **Rescore on Supabase** has hundreds of papers, so the same knob clearly changes rankings.

**Demo (10) ≈ Rescore (10)** only on the **same database**. Demo on a laptop vs Rescore (10) on Supabase is *not* the same — different pools of papers.

---

### Incremental scan vs full live pull

Both hit **live APIs** (PubMed, trials via BioMCP), then run all six agents. Neither is offline like Demo/Rescore.

| | **Incremental scan** | **Full live pull** |
|---|----------------------|---------------------|
| API `mode` | `scan` | `full` |
| Intent | Add **what’s new** cheaply | **Backfill / refresh** the corpus |
| Known `source_id` in DB? | Skip LLM re-extraction | Same — skip duplicates |
| Date bias | Uses `scan_state.last_scan_at` to narrow pulls | Broader since-year pull |
| Preprints / grants UI | Off (scan path) | Optional toggles |
| Trace label | **Incremental scan complete** | **Full live pull complete** |

**Incremental:** For each search hit, already stored → touch `last_scanned_at` and skip; new → one LLM extraction → insert.  
**Full:** Same merge behavior, plus optional preprints, full-text sections, and NIH grants — more network and extraction work, so **full usually takes longer** at the same `max_papers`.

{: .important }
**Stage safety:** Incremental and full call live PubMed and may run LLM extraction. Pre-run before presenting; use **Demo** or **Rescore** on stage. See [Debugging — safe demo checklist](debugging#safe-demo-checklist-stage).

---

### Does full clear the database?

**No.** Full live pull (and incremental scan) **merge** into existing data:

- Duplicate `source_type` + `source_id` → skip insert, no second copy
- New ids → `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING`

Agents 2–6 may **update** scores, connections, and recommendations for the new `run_id`, but they do **not** bulk-delete evidence.

| Command | Clears DB? |
|---------|------------|
| `cli.py build` | **Yes** — truncates all tables, reloads seed |
| `make dashboard --fresh` (local) | **Yes** — deletes and rebuilds local `neurodiscover.db` |
| Full / incremental / demo / rescore | **No** |

---

### How long do runs take? (ballpark)

Runtime depends on **how many papers are new** (not just `max_papers`) and **`EXTRACT_BACKEND`** (`nebius` vs `none`).

**Incremental scan, max 150, mature Supabase** (typical: `150 searched · +3 new · 147 skipped`):

| Phase | Rough time |
|-------|------------|
| Search + fetch ~150 sources | ~1–3 min |
| LLM on ~3 new papers | ~30 s–2 min |
| Agents 2–6 | ~30 s–2 min |
| **Total** | **~2–7 min** |

**Same settings, empty DB** (~150 all new): literature LLM dominates — often **~12–35 min**.

**Full live pull @ 150** with preprints + grants + full text: often **~1.5×–3×** longer than incremental on a mature DB; **30–60+ min** if many items are new.

Watch Step 1 literature progress: `Processing 45/150 sources (2 new, 43 skipped)…` — high **skipped** means a fast finish.

---

## External evidence sources

Agent 1 (Literature Synthesis) pulls from public APIs via **BioMCP** and optional MCP servers:

| Source | `source_type` | Example id | Tooling |
|--------|---------------|------------|---------|
| PubMed | `literature` | `PMID:38234567` | BioMCP / E-utilities |
| bioRxiv preprints | `literature` | DOI | bioRxiv MCP |
| ClinicalTrials.gov | `trial` | `NCT01234567` | BioMCP |
| NIH RePORTER | `grant` | project number | `cli.py pull-grants` / full-mode `pull_grants` |

Grant rows infer `subgroup`, `mechanism`, and `treatment` from project title keywords (GBA, LRRK2, alpha-synuclein, etc.) so they can enter agents 2–6. Existing grants with null subgroup are backfilled on each grant pull.

{: .warning }
**Never invent PMIDs, DOIs, or NCT ids.** Seed data uses `DEMO-*` placeholders for offline demo only. Live pulls must use ids returned by BioMCP.

### Literature pull CLI

```bash
cd neurodiscover
python3 cli.py pull --disease "your condition" --max 150
python3 cli.py pull --max 50 --include-preprints 20
python3 cli.py pull --query "GBA GCase lysosomal" --gene GBA
python3 cli.py pull-grants --limit 30
python3 cli.py scan --max 5          # incremental; skips LLM for known ids
```

### Extraction backend

Set `EXTRACT_BACKEND=nebius|ollama|none` in `.env` for structured LLM extraction of subgroup, mechanism, treatment, key_result, and evidence_snippet from abstracts.

---

## POST /api/run-discovery (pipeline trigger)

The form in **Step 1 — Configure & Run** (above) posts the same body the API accepts:

```json
{
  "mode": "demo",
  "run_id": "f799fbe8",
  "query": null,
  "max_papers": 150,
  "disease": "Parkinson's",
  "include_preprints": 0,
  "with_fulltext": false,
  "extract_backend": null,
  "pull_grants": true
}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `mode` | `demo` \| `scan` \| `full` \| `agents-only` | Offline seed / incremental scan / live pull / downstream-only on existing evidence |
| `run_id` | string (optional) | Client-generated id (8 chars); UI sends this so the stepper tracks the run immediately. **Full** mode passes it to literature pull. |
| `max_papers` | **10–500** (API validated; **agents-only** may use **0** = all rows) | **Demo**: caps literature for agents 2–6. **Rescore**: cap if &gt; 0; **0** or UI ≥ 500 = full DB. **Scan/full**: caps pull size; agents 2–6 use full DB after ingest. See [What max papers does](#what-max_papers-does). |
| `query` | string or null | Optional keyword filter passed to BioMCP |
| `disease` | string | Literature anchor; dashboard default **Parkinson's** (API default `"Parkinson disease"` if omitted) |
| `include_preprints` | integer | bioRxiv cap; used in **full** mode |
| `with_fulltext` | boolean | OA full-text sections; **full** / `pull` paths |
| `extract_backend` | `nebius` \| `ollama` \| `none` or null | Override `EXTRACT_BACKEND` in `.env` |
| `pull_grants` | boolean | **Full** mode only: run NIH RePORTER pull (≤30 grants, default PD-focused query if unset) |
| `wait` | boolean | default `false`; if `true`, block until pipeline completes and return full payload (recommendations, agent_outputs, runStats, synthetic_cohort) |

---

## Evidence row (Agent 1 output → Agent 2+ input)

Each row in the `evidence` table is a distilled finding — not raw API JSON.

### Required on live pull

| Column | Example |
|--------|---------|
| `source_type` | `literature` |
| `source_id` | `PMID:38234567` |

### Core discovery fields (literature)

| Column | Example |
|--------|---------|
| `title` | GCase activity and lysosomal dysfunction in GBA-associated Parkinson's |
| `year` | 2023 |
| `subgroup` | GBA-mutation PD |
| `mechanism` | lysosomal dysfunction |
| `treatment` | GCase activation |
| `key_result` | Reduced GCase activity correlates with faster progression… |
| `evidence_snippet` | GCase enhancement restored lysosomal function. |

### Access metadata

| `access_type` | `access_status` | Meaning |
|---------------|-----------------|---------|
| `published_oa` | `open` | OA full text available |
| `published_paywalled` | `restricted` | Abstract/metadata only |
| `preprint` | `abstract_only` | bioRxiv preprint |

### Demo seed example

From `seed_data.json` (placeholder ids — not for live citation):

```json
{
  "source_type": "literature",
  "source_id": "DEMO-PMID-001",
  "title": "GCase activity and lysosomal dysfunction in GBA-associated Parkinson's",
  "year": 2023,
  "subgroup": "GBA-mutation PD",
  "mechanism": "lysosomal dysfunction",
  "treatment": "GCase activation",
  "key_result": "Reduced GCase activity correlates with faster progression in GBA carriers.",
  "study_type": "preclinical + cohort",
  "sample_size": 120
}
```

---

Literature extraction prefers consistent subgroup names when the evidence supports them. Demo seed uses five names in `seed_data.json` (e.g. `GBA-mutation PD`, `LRRK2 PD`, `Rapid motor progressors`) — exact match enables auto-linking via `subgroup_evidence`.

---

## Per-agent SQL reads

Downstream agents never read raw BioMCP blobs — only distilled columns.

### Agent 2 — Patient Subgroup

```sql
SELECT evidence_id, subgroup, mechanism, treatment, key_result, study_type, sample_size
FROM evidence
WHERE subgroup IS NOT NULL;
```

### Agent 3 — Treatment Connection

```sql
SELECT s.subgroup_id, s.name, e.mechanism, e.treatment, e.evidence_id
FROM evidence e
JOIN subgroups s ON s.name = e.subgroup
WHERE e.mechanism IS NOT NULL AND e.treatment IS NOT NULL;
```

### Agent 4 — Evidence Scoring

In-memory connections from Agent 3 plus evidence rows matching each connection’s subgroup + mechanism + treatment. Scoring uses **per-connection `evidence_count`** (continuous) and source types — not `study_type` / `sample_size` directly.

Reference SQL (post-persistence inspection):

```sql
SELECT tc.connection_id, e.source_type, e.study_type, e.sample_size, e.access_status, e.key_result
FROM treatment_connections tc
JOIN connection_evidence ce ON ce.connection_id = tc.connection_id
JOIN evidence e ON e.evidence_id = ce.evidence_id;
```

### Agent 5 — Commercial Discovery

Reads in-memory scored connections from Agent 4. **Heuristic** commercial scoring in `commercial_discovery_agent.py` (no Tavily). Grants are ingested separately via `pull-grants` / full-mode `pull_grants`.

### Agent 6 — Conclusion Update

```sql
SELECT tc.connection_id, s.name AS subgroup, tc.treatment,
       tc.evidence_strength, tc.commercial_potential
FROM treatment_connections tc
JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
WHERE tc.evidence_strength IS NOT NULL AND tc.commercial_potential IS NOT NULL;
```

---

## Shared run_id

All six agents append to `agent_outputs` with the same `run_id` for one pipeline run:

```sql
INSERT INTO agent_outputs (run_id, agent_name, step_order, summary, payload)
VALUES (?, ?, ?, ?, ?);
```

See [Agent I/O](developer-reference/agent-io) for full SQL and payload shapes.
