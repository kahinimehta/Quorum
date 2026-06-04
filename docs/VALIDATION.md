# Evidence extraction validation

After `cli.py pull`, the literature agent can run automated QA on LLM/Ollama extractions.

## Commands

```bash
# Pull with default QA (consistency + PubTator sample n=50)
python3 cli.py pull --max 20

# Pull without PubTator (faster)
python3 cli.py pull --max 20 --no-pubtator

# Drop rows that fail consistency checks
python3 cli.py pull --max 20 --strict-pull

# Audit entire evidence table
python3 cli.py validate-extraction

# PubTator grounding on existing DB
python3 cli.py validate-pubtator --sample 50

# Manual spot-check
python3 cli.py spot-check --count 15
# Edit spot_check_results.csv, then:
python3 cli.py spot-check --score
```

## Consistency checks (`validation/consistency.py`)

Validates per row:

- `source_id` format (numeric PMID, NCT*, grant id)
- `study_type` in allowed set (RCT, cohort, preclinical, Phase 1–3, review, unknown, …)
- `sample_size` if set: integer in (0, 1_000_000)
- Literature/trial: `mechanism` (≥5 chars), `treatment` (≥3), `key_result`, `evidence_snippet`

Failed rows are **kept by default**; use `--strict-pull` to skip insert.

## PubTator grounding (`validation/pubtator.py`)

Queries [PubTator3](https://www.ncbi.nlm.nih.gov/research/pubtator3/) for genes, diseases, chemicals and compares to tokens extracted from LLM fields.

| Overlap | Label |
|---------|--------|
| > 0.7 | HIGH |
| 0.3 – 0.7 | MEDIUM |
| < 0.3 | LOW |

Heuristic entity extraction is imperfect; use spot-check for final precision.

## Spot-check workflow

1. `spot-check` prints abstracts (via BioMCP) and writes `spot_check_results.csv`.
2. Read each abstract; fill `correct_*` columns (or set `precision` 0.0–1.0 per row).
3. `spot-check --score` reports average precision.

## Demo readiness (rule of thumb)

| Metric | Target |
|--------|--------|
| Consistency pass rate | ≥ 70% |
| PubTator avg overlap (n≥30) | ≥ 0.5 (HIGH/MEDIUM) |
| Manual spot-check (n=15) | ≥ 80% precision |

Validation summary is stored in `agent_outputs.payload` for the pull `run_id` (step 3).

## Design choices

- **Flag, don’t delete** by default — downstream agents can still use metadata-only rows.
- **PubTator** runs on literature PMIDs only (not trials/grants).
- **No schema change** — confidence lives in reports and CSV, not a new DB column.
