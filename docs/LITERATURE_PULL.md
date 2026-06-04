---
layout: default
title: Literature pull
parent: Developer reference
nav_order: 9
---

# Literature Pull — Two-Stage MCP Strategy

**Owner:** Person 3/4 (Ayelet)  
**Code:** `ingestion/published_pull.py`, `ingestion/biorxiv_pull.py`, `agents/fulltext.py`

## Overview

The Literature Synthesis Agent uses a **two-stage pull**:

| Stage | Source | Default | Full-text chain |
|-------|--------|---------|-----------------|
| 1 — Published | PubMed (E-utilities or MCP) | `--max 150` | NCBI PMC XML → Europe PMC → Unpaywall → `published_paywalled` |
| 2 — Preprints | bioRxiv API (or MCP) | `--include-preprints N` | JATS XML always; `access_type=preprint` |

Clinical trials still come from **BioMCP** (`trial search`) in the same run.

## CLI

```bash
cd neurodiscover
python3 cli.py build
python3 cli.py validate

# Stage 1 only (published papers, default max=150)
EXTRACT_BACKEND=none python3 cli.py pull --max 5 --no-pubtator --no-validate

# With OA section excerpts
python3 cli.py pull --max 10 --with-fulltext --no-pubtator

# Stage 1 + Stage 2 preprints
python3 cli.py pull --max 50 --include-preprints 20 --no-pubtator
```

## MCP wiring (optional)

Set env vars to prefer MCP subprocesses over direct APIs:

| Env var | Purpose |
|---------|---------|
| `PUBMED_MCP_COMMAND` | Shell command for PubMed search MCP |
| `BIORXIV_MCP_COMMAND` | Shell command for bioRxiv search MCP |
| `UNPAYWALL_EMAIL` | Email for Unpaywall OA lookup on paywalled DOIs |

Expected MCP interface (implemented in `ingestion/mcp_clients.py`):

```bash
$PUBMED_MCP_COMMAND search --json '{"query":"Parkinson GBA","max":10,"since_year":2020}'
# stdout: JSON list of articles OR {"results":[...]}
```

If the command is unset or fails, fallbacks run automatically:

- **PubMed:** NCBI E-utilities (`esearch` + `efetch`), then BioMCP if empty
- **bioRxiv:** `https://api.biorxiv.org/details/biorxiv/{start}/{end}/{cursor}` with client-side keyword filter
- **Unpaywall:** `https://api.unpaywall.org/v2/{doi}?email=...`

### Wiring real MCP servers later

1. Clone/install your team's PubMed/bioRxiv MCP repos locally.
2. Wrap each in a thin shell script that accepts `search --json '<payload>'` and prints JSON hits.
3. Set `PUBMED_MCP_COMMAND` / `BIORXIV_MCP_COMMAND` in `.env`.
4. No code changes required unless the MCP uses a different CLI contract — then adjust `ingestion/mcp_clients.py`.

CI does **not** require MCP repos; direct API fallbacks are the default path.

## Schema (`access_type` / `access_status`)

| `access_type` | `access_status` (backend) | Meaning |
|---------------|---------------------------|---------|
| `published_oa` | `open` | Full text retrieved (PMC/EPMC/Unpaywall) |
| `published_paywalled` | `restricted` | Metadata/abstract only |
| `preprint` | `abstract_only` | bioRxiv preprint |
| `error` | `error` | Lookup failed |
| `unknown` | `unknown` | No classification |

Legacy values `open` / `restricted` are mapped in code to `published_oa` / `published_paywalled`.

New columns: `is_preprint`, `publication_year`. Migration: `migrations/002_evidence_mcp_metadata.sql`.

## Title deduplication

Preprints whose normalized title matches a published paper from stage 1 are skipped.
Normalization: lowercase, strip punctuation, collapse whitespace (`ingestion/biorxiv_pull.py`).

## Testing

```bash
# Europe PMC section extract on known OA PMID
python3 -c "
from agents.fulltext import resolve_published_access
r = resolve_published_access('41989783', with_fulltext=True)
print(r['access_type'], bool(r.get('methods_text') or r.get('results_text')))
"

# Title dedupe unit check
python3 -c "
from ingestion.biorxiv_pull import normalize_title, title_is_duplicate
pub = {normalize_title('Alpha-Synuclein in Parkinson Disease.')}
print(title_is_duplicate('Alpha Synuclein in Parkinson Disease', pub))
"
```
