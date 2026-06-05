---
layout: default
title: Agent I/O
parent: Developer reference
nav_order: 2
---

# Agent I/O Contract — NeuroDiscover (Quorum)

**Owner:** Person 4 (multi-agent logic). Literature section by Ayelet.  
**Database contract:** [Database schema](database)

Every agent **reads** prior tables, **writes** its own output, and **appends** to `agent_outputs`.

## Standard trace row

All agents insert into `agent_outputs`:

```sql
INSERT INTO agent_outputs (run_id, agent_name, step_order, summary, payload)
VALUES (?, ?, ?, ?, ?);
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `run_id` | TEXT | yes | Same id for one pipeline run (share across agents) |
| `agent_name` | TEXT | yes | Exact names below |
| `step_order` | INTEGER | yes | 1, 2, … within this agent's steps |
| `summary` | TEXT | yes | Human-readable one-liner for dashboard |
| `payload` | TEXT (JSON) | optional | Machine-readable stats |

**Rule:** Downstream agents never read raw BioMCP JSON or external API blobs. Only distilled DB columns.

---

## Agent 1 — Literature Synthesis Agent (Ayelet)

**Reads:** external PubMed + ClinicalTrials.gov via BioMCP; `subgroups.name` for auto-linking  
**Writes:** `evidence`, `subgroup_evidence` (auto-link), `scan_state`, `agent_outputs`

### CLI (Person 3 data layer)

```bash
python3 cli.py pull --disease "Parkinson disease" --max 150          # stage 1: published (default)
python3 cli.py pull --max 50 --include-preprints 20                  # + bioRxiv preprints
python3 cli.py pull --max 50 --with-fulltext                         # OA: PMC → EPMC → Unpaywall sections
python3 cli.py enrich-with-fulltext --limit 50                       # backfill sections on existing rows
python3 cli.py pull --query "GBA GCase lysosomal" --gene GBA
python3 cli.py pull-grants --limit 30
python3 cli.py scan --max 5
```

See [Literature pull](literature-pull) for MCP env vars (`PUBMED_MCP_COMMAND`, `BIORXIV_MCP_COMMAND`, `UNPAYWALL_EMAIL`).

`EXTRACT_BACKEND=nebius|ollama|none` selects LLM for **core discovery** fields on literature (5 fields). Trials still use the fuller prompt (`study_type`, `sample_size`).

### INSERT `evidence`

Required on live pull: `source_type`, `source_id` (real PMID/DOI/NCT only — no invented ids).

Recommended populated fields:

```
source_type, source_id, title, year, publication_year, venue, abstract, subgroup, mechanism, treatment,
key_result, evidence_snippet, access_type, access_status, full_text_url, is_preprint,
methods_text, results_text, discussion_text, url, doi
```

Literature rows may omit `study_type` / `sample_size` until Agent 4 parses methods/results.

### `access_type` / `access_status` values

| `access_type` | `access_status` | Meaning |
|---------------|-----------------|---------|
| `published_oa` | `open` | OA full text available |
| `published_paywalled` | `restricted` | Abstract/metadata only |
| `preprint` | `abstract_only` | bioRxiv preprint |
| `error` | `error` | Lookup failed |
| `unknown` | `unknown` | Unclassified |

### Auto-link `subgroup_evidence`

After insert, if `evidence.subgroup` matches `subgroups.name` exactly:

```sql
INSERT OR IGNORE INTO subgroup_evidence (subgroup_id, evidence_id) VALUES (?, ?);
```

### Example `payload`

```json
{
  "new_evidence": 3,
  "skipped_duplicates": 7,
  "touched_existing": 7,
  "rejected_no_id": 1,
  "since_year": 2024,
  "incremental": true
}
```

### CLI

```bash
python3 cli.py pull --since 2022 --max 10    # full backfill
python3 cli.py scan --max 5                  # incremental (skips LLM for known ids)
python3 cli.py demo                          # offline; no API calls
```

---

## Agent 2 — Patient Subgroup Agent (Alia)

**Reads:**

```sql
SELECT evidence_id, subgroup, mechanism, treatment, key_result, study_type, sample_size
FROM evidence
WHERE subgroup IS NOT NULL;
```

**Writes:** `subgroups` (INSERT new names or UPDATE features), `agent_outputs`

**Do not** duplicate evidence rows. Tag subgroups in evidence; refine definitions in `subgroups`.

---

## Agent 3 — Treatment Connection Agent (Alia)

**Reads:**

```sql
SELECT s.subgroup_id, s.name, e.mechanism, e.treatment, e.evidence_id
FROM evidence e
JOIN subgroups s ON s.name = e.subgroup
WHERE e.mechanism IS NOT NULL AND e.treatment IS NOT NULL;
```

**Writes:**

```sql
INSERT INTO treatment_connections (subgroup_id, mechanism, treatment) VALUES (?,?,?);
INSERT OR IGNORE INTO connection_evidence (connection_id, evidence_id) VALUES (?,?);
```

Plus `agent_outputs`.

---

## Agent 4 — Evidence Scoring / Skeptic (Alia)

**Reads:** `treatment_connections` + linked evidence via `connection_evidence`

```sql
SELECT tc.connection_id, e.study_type, e.sample_size, e.access_status, e.key_result
FROM treatment_connections tc
JOIN connection_evidence ce ON ce.connection_id = tc.connection_id
JOIN evidence e ON e.evidence_id = ce.evidence_id;
```

**Writes:**

```sql
UPDATE treatment_connections SET evidence_strength = ? WHERE connection_id = ?;
```

Down-weight `abstract_only` / small `sample_size` in scoring logic. Plus `agent_outputs`.

---

## Agent 5 — Commercial Discovery (Alia / Amy)

**Reads:** `treatment_connections` (mechanism, treatment, subgroup_id)  
**External:** Tavily web search, NIH RePORTER grants API  
**Writes:**

```sql
UPDATE treatment_connections SET commercial_potential = ? WHERE connection_id = ?;
```

Optional: INSERT grant rows into `evidence` with `source_type = 'grant'`. Plus `agent_outputs`.

---

## Agent 6 — Conclusion Update (Amy)

**Reads:** scored `treatment_connections` joined to `subgroups`

```sql
SELECT tc.connection_id, s.name AS subgroup, tc.treatment,
       tc.evidence_strength, tc.commercial_potential
FROM treatment_connections tc
JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
WHERE tc.evidence_strength IS NOT NULL AND tc.commercial_potential IS NOT NULL;
```

**Writes:**

```sql
INSERT INTO recommendations (run_id, connection_id, subgroup, treatment, confidence, tier, rationale)
VALUES (?, ?, ?, ?, ?, ?, ?);
```

Where `confidence = evidence_strength * 0.55 + commercial_potential * 0.45` and:

| Tier | Condition |
|------|-----------|
| Prioritize | confidence ≥ 80 |
| Monitor | 65 ≤ confidence < 80 |
| Reject | confidence < 65 |

Plus `agent_outputs`.

---

## Shared `run_id` convention

Pass the same `run_id` through all six agents in one discovery run so the dashboard can filter:

```sql
SELECT * FROM agent_outputs WHERE run_id = ? ORDER BY output_id;
```

---

## Subgroup name vocabulary (prefer exact match)

- GBA-mutation PD
- LRRK2 PD
- Alpha-synuclein-high PD
- Inflammation-high PD
- Rapid motor progressors

Literature agent extraction prompt prefers these names when applicable.
