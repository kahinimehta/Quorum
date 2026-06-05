---
layout: default
title: Literature Synthesis
parent: Workflow
nav_order: 1
description: "Agent 1 — PubMed, trials, grants ingestion"
---

# Agent 1 — Literature Synthesis

**Module:** `neurodiscover/agents/literature_agent.py`  
**Owner:** Ayelet Peres  
**Step order:** 1

---

## Role

Pull manuscripts and clinical trials for a **configured disease or condition**, extract structured findings via LLM, and write distilled rows to the `evidence` table. Auto-link evidence to seed subgroups when names match exactly.

## External inputs

| Source | Tool | `source_type` |
|--------|------|---------------|
| PubMed | BioMCP | `literature` |
| bioRxiv | bioRxiv MCP (optional) | `literature` |
| ClinicalTrials.gov | BioMCP | `trial` |
| NIH RePORTER | `pull-grants` | `grant` |

## Pipeline steps

1. **PULL** — search BioMCP for disease + optional keyword/gene filter
2. **FETCH** — abstract and metadata per hit (two-step; access flags set)
3. **EXTRACT** — Nebius/Ollama structured extraction (`EXTRACT_BACKEND`)
4. **WRITE** — INSERT into `evidence` (`UNIQUE(source_type, source_id)` dedups)
5. **LINK** — `subgroup_evidence` when `evidence.subgroup` matches `subgroups.name`
6. **TRACE** — log to `agent_outputs`; update `scan_state` on incremental scans

## Writes

| Table | Content |
|-------|---------|
| `evidence` | One row per source with subgroup, mechanism, treatment, key_result, access metadata |
| `subgroup_evidence` | Many-to-many links to seed subgroups |
| `scan_state` | Singleton: last scan time, last `run_id` |
| `agent_outputs` | Trace row with pull stats |

## Key columns on `evidence`

```
source_type, source_id, title, year, subgroup, mechanism, treatment,
key_result, evidence_snippet, access_type, access_status, doi,
methods_text, results_text, discussion_text
```

## CLI

```bash
python3 cli.py pull --disease "your condition" --max 150
python3 cli.py pull --max 50 --include-preprints 20
python3 cli.py pull --query "GBA GCase lysosomal" --gene GBA
python3 cli.py scan --max 5                    # incremental
python3 cli.py demo                            # offline; no API
```

## Example trace payload

```json
{
  "new_evidence": 3,
  "skipped_duplicates": 7,
  "since_year": 2024,
  "incremental": true
}
```

## Validation

After pull, optional consistency checks and PubTator grounding run automatically. See [Validation](developer-reference/validation).
