---
layout: default
title: Inputs
nav_order: 3
description: "External sources, API requests, and database rows that feed the pipeline"
---

# Inputs

What NeuroDiscover consumes — external evidence sources, API request bodies, and the distilled database columns each agent reads.

---

## External evidence sources

Agent 1 (Literature Synthesis) pulls from public APIs via **BioMCP** and optional MCP servers:

| Source | `source_type` | Example id | Tooling |
|--------|---------------|------------|---------|
| PubMed | `literature` | `PMID:38234567` | BioMCP / E-utilities |
| bioRxiv preprints | `literature` | DOI | bioRxiv MCP |
| ClinicalTrials.gov | `trial` | `NCT01234567` | BioMCP |
| NIH RePORTER | `grant` | project number | `cli.py pull-grants` |

{: .warning }
**Never invent PMIDs, DOIs, or NCT ids.** Seed data uses `DEMO-*` placeholders for offline demo only. Live pulls must use ids returned by BioMCP.

### Literature pull CLI

```bash
cd neurodiscover
python3 cli.py pull --disease "Parkinson disease" --max 150
python3 cli.py pull --max 50 --include-preprints 20
python3 cli.py pull --query "GBA GCase lysosomal" --gene GBA
python3 cli.py pull-grants --limit 30
python3 cli.py scan --max 5          # incremental; skips LLM for known ids
```

### Extraction backend

Set `EXTRACT_BACKEND=nebius|ollama|none` in `.env` for structured LLM extraction of subgroup, mechanism, treatment, key_result, and evidence_snippet from abstracts.

---

## POST /api/run-discovery (pipeline trigger)

The dashboard and API start a full run with:

```json
{
  "mode": "demo",
  "query": null,
  "max_papers": 150,
  "with_fulltext": false,
  "pull_grants": true
}
```

| Field | Values | Meaning |
|-------|--------|---------|
| `mode` | `demo` \| `scan` \| `full` | Offline seed / incremental scan / live pull |
| `max_papers` | integer | Caps literature rows used by agents 2–6 |
| `query` | string or null | Optional keyword filter passed to BioMCP |
| `with_fulltext` | boolean | Fetch OA Methods/Results/Discussion sections |
| `pull_grants` | boolean | Include NIH RePORTER grants in full mode |

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

## Subgroup vocabulary (prefer exact match)

Literature extraction prefers these names when applicable:

- GBA-mutation PD
- LRRK2 PD
- Alpha-synuclein-high PD
- Inflammation-high PD
- Rapid motor progressors

Five seed subgroups in `subgroups` table map to these names.

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

```sql
SELECT tc.connection_id, e.study_type, e.sample_size, e.access_status, e.key_result
FROM treatment_connections tc
JOIN connection_evidence ce ON ce.connection_id = tc.connection_id
JOIN evidence e ON e.evidence_id = ce.evidence_id;
```

### Agent 5 — Commercial Discovery

Reads `treatment_connections` (mechanism, treatment, subgroup_id) plus external Tavily web search and NIH RePORTER.

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

See [Agent I/O contract](developer-reference/agent-io) for full SQL and payload shapes.
