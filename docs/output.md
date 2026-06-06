---
layout: default
title: Output examples
nav_order: 5
description: "API JSON shapes, recommendations, ideal candidate profiles, and dashboard panels"
---

# Output examples

What NeuroDiscover produces — ranked recommendations, agent trace, synthetic patients, and API response shapes.

---

## Dashboard — Step 2 (Discovery Results)

After a run completes, **Step 2** shows pipeline outputs: ideal candidate profiles, ranked treatments, and hypotheses. **Audit & provenance** (agent trace + evidence preview) is collapsed by default — expand it to inspect this run’s `run_id` and source links.

Layout top-to-bottom:

1. **KPI strip** — papers · trials · grants · subgroups · connections (database totals, or **this run** after a pipeline).
2. **Pipeline complete** badge beside the Step 2 title when a run finishes successfully.
3. Subtitle: *Cohort, ranked outputs, & hypotheses*.
4. **Three panels** — **Ideal candidate profiles** · **Ranked outputs** · **Research hypotheses** (with confidence-by-treatment strip).
5. **Discovery pipeline** — flow diagram (inputs → six agents → outputs).
6. **Audit & provenance** — collapsed by default; expand for agent run trace + paginated evidence preview.

![Step 2 — Discovery results overview](/assets/images/dashboard/step2-discovery-results.png)
{: .doc-screenshot }

*Step 2 — full-width results shell with KPI strip above title; ideal candidate profiles and ranked outputs cap at research hypotheses body height (borders wrap content; scroll when longer); ranked bars show treatment · subgroup; discovery pipeline and audit & provenance below.*

---

## Dashboard — Step 3 (Grant Proposal)

**Step 3** is separate from pipeline rankings and **not run-scoped**. It loads bundled `graded6` via `GET /api/cua/demo` and inlines `/cua-demo/graded6.html`. **The proposal** stays expanded (NIH aims + PubMed ID citations); **Grant pipeline** is a separate collapsed block with the agent-flow diagram; **Pipeline trace & audit** is one collapsed group for contract, booster, audit, and ingestion prose. Hero KPIs and **Jump to** are unchanged across Step 2 runs.

![Step 3 — Grant proposal tab](/assets/images/dashboard/step3-grant-proposal.png)
{: .doc-screenshot }

*Step 3 — hero KPIs (corpus · verified papers · citations · Critic F1/F2/F3), report toolbar **17/21 obligations satisfied**, expanded proposal, collapsed Grant pipeline + Pipeline trace & audit.*

**Verified papers** is not the full database — it is ingestion’s `top_k` (60 in `graded6`) after clustering and relevance ranking. The full **corpus** (400) still backs citation integrity. See [Dashboard — Corpus vs verified papers](dashboard#corpus-vs-verified-papers).

| Jump to | Layout | Content |
|---------|--------|---------|
| **Proposal** | Always visible (first in report) | NIH R01 proposal — significance, innovation, three aims; **PubMed ID** / NCT / Grant citation links |
| **Grant pipeline** | Collapsed block | Interactive agent-flow diagram + **Open full report** link |
| **Supporting details** | One collapsed group | Contract · dropped args · revise rounds · booster · A/B outcomes · raw trace · audit · ingestion |

To generate a new proposal from your database, run `python -m cua.nih.run_db` (see [Conclusion Update → CUA](workflow/conclusion-update#cua-package--nih-grant-proposal)).

Section-by-section tour (contract, best-of-N, data loop, audit, …): [Dashboard — Step 3 report structure](dashboard#step-3--report-structure).

---

## POST /api/run-discovery response

Full pipeline response (demo mode, abbreviated):

```json
{
  "run_id": "a1b2c3d4",
  "recommendations": [
    {
      "subgroup": "GBA-mutation PD",
      "treatment": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "tier": "Prioritize",
      "rationale": "Strong preclinical and Phase 2 signal for GCase chaperones in GBA carriers."
    }
  ],
  "agent_outputs": [
    {
      "agentName": "Literature Synthesis Agent",
      "stepOrder": 1,
      "summary": "Processed 5 literature rows (demo mode).",
      "createdAt": "2026-06-01T16:00:00Z"
    }
  ],
  "synthetic_cohort": [
    {
      "patient_id": "Patient Cluster A",
      "patient_letter": "A",
      "subgroup": "GBA-mutation PD",
      "subgroup_color": "#2563eb",
      "synthetic_age": 68,
      "synthetic_sex": "M",
      "key_feature": "GBA1 variant carriers",
      "top_opportunity": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "is_synthetic": true,
      "phi_free": true
    }
  ],
  "runStats": {
    "mode": "demo",
    "modeLabel": "Demo sample",
    "maxPapersRequested": 10,
    "processed": { "literature": 5, "trial": 0, "grant": 0, "total": 5 },
    "databaseTotals": { "literature": 228, "trial": 39, "grant": 40, "total": 307 },
    "added": { "literature": 0, "trial": 0, "grant": 0, "total": 0 }
  }
}
```

`steps` is an alias of `agent_outputs`.

---

## Recommendations (Agent 6)

![Ranked outputs panel](/assets/images/dashboard/step2-ranked-treatments.png)
{: .doc-screenshot }

*Ranked treatments with confidence bars and Prioritize / Monitor / Reject tiers.*

### Treatment labels

Canonical `treatment` slugs in `evidence` and `recommendations` map to dashboard copy via `treatment_labels.py` (backend rationales) and the Step 2 UI.

| DB slug | Dashboard label | Meaning |
|---------|-----------------|--------|
| `GCase activation` | GCase activation | Lysosomal GCase chaperone/activator for GBA-mutation PD |
| `LRRK2 inhibition` | LRRK2 inhibition | Kinase-pathway LRRK2 inhibitor for LRRK2 PD |
| `clearance therapy` | clearance therapy | Alpha-synuclein clearance/immunotherapy for high-seeding PD |
| `microglial modulation` | microglial modulation | Anti-inflammatory microglial target for inflammation-high PD |
| **`combination strategy`** | **Combination neuroprotection** | **Rapid motor progressors** (fast UPDRS decline): literature proposes stacking multiple neuroprotective agents—symptomatic plus disease-modifying—because no single therapy is established for this trajectory. Evidence is cohort-level and early; typically **Monitor** tier. |

```json
{
  "recommendations": [
    {
      "subgroup": "GBA-mutation PD",
      "treatment": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "tier": "Prioritize",
      "rationale": "Multiple literature and trial sources; strong mechanism alignment."
    },
    {
      "subgroup": "LRRK2 PD",
      "treatment": "LRRK2 inhibition",
      "confidence": 71.2,
      "tier": "Monitor",
      "rationale": "Phase 2 ongoing; evidence strength moderate."
    },
    {
      "subgroup": "Rapid motor progressors",
      "treatment": "combination strategy",
      "mechanism": "neuroprotection",
      "confidence": 77.8,
      "tier": "Monitor",
      "rationale": "Rapid motor progressors → Combination neuroprotection via neuroprotection. Rapid motor progressors show faster UPDRS decline than typical PD. Literature proposes combining neuroprotective agents rather than betting on one monotherapy, but combo regimens remain unproven in this subgroup. Confidence 77.8 (Monitor)."
    }
  ]
}
```

### Scoring (Steps 1–2)

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Field | Minimum | Maximum |
|-------|---------|---------|
| `evidence_strength` (Agent 4, stored) | 0 | 100 |
| `commercial_potential` (Agent 5, stored) | 0 | 100 |
| `confidence` (Agent 6, displayed) | 0 | 100 |

Agents 4–5 compute **0–10** heuristics in code; the orchestrator scales ×10 before writing the DB columns above.

| Tier | Condition |
|------|-----------|
| Prioritize | confidence ≥ 80 |
| Monitor | 65 ≤ confidence < 80 |
| Reject | confidence < 65 |

{: .note }
**Not the same as Tab 3 Critic scores.** Grant Proposal **F1 / F2 / F3** use a **1–9** NIH Critic scale (minimum 1, maximum 9). See [Dashboard — Critic score scale](dashboard#critic-score-scale-f1--f2--f3).

### When confidence changes

Scores **update every pipeline run** (agents 2–6 recompute from the full `evidence` corpus with `subgroup IS NOT NULL`). Confidence moves when:

- New literature/trial rows are stored **with** `subgroup`, `mechanism`, and `treatment` filled (check literature step: `Stored N new evidence`).
- Those rows attach to an existing connection (increase `evidence_count`) or create a new connection.
- Grant pulls tag rows into subgroups (title keyword inference + backfill on each pull).

Confidence may stay flat when `Stored 0 new`, when new rows lack extraction fields, or when **Rescore** runs on the same corpus without new scored rows. **Demo** and **Rescore** cap literature only — trials always count. Results charts prefer **this run’s** `recommendations` over global connection totals.

Recent runs **Mode** column uses human labels (`Incremental scan`, `Full live pull`, …). **Evidence** column examples:

| Mode | Example evidence note |
|------|------------------------|
| Incremental scan | `150 searched · +3 new · 147 skipped · incremental` |
| Full live pull | `150 papers · 5 trials · +12 stored · 138 skipped` |
| Rescore DB | `182 rows rescored (no pull)` |
| Demo sample | `10 papers (demo sample)` |

Only scored rows (with subgroup tags) affect confidence — see [Inputs](input).

---

## Agent trace

![Agent trace and evidence audit](/assets/images/dashboard/step2-audit-evidence.png)
{: .doc-screenshot }

*Expand **Audit & provenance** on Step 2 — agent run trace (shared `run_id`) and paginated evidence preview with source links.*

Every run logs rows in `agent_outputs`. Literature logs **mode-specific** summaries and live progress commits during scan/pull:

```json
{
  "runId": "a1b2c3d4",
  "steps": [
    {
      "agentName": "Literature Synthesis Agent",
      "stepOrder": 0,
      "summary": "Starting incremental scan for Parkinson's…",
      "payload": { "pipeline_mode": "scan", "incremental": true, "progress": 0, "total": 150 }
    },
    {
      "agentName": "Literature Synthesis Agent",
      "stepOrder": 2,
      "summary": "Incremental scan complete: stored 3 new evidence rows (147 existing skipped, 0 rejected).",
      "payload": { "pipeline_mode": "scan", "new_evidence": 3, "skipped_duplicates": 147 }
    },
    {
      "agentName": "Patient Subgroup Agent",
      "stepOrder": 2,
      "summary": "Identified 5 subgroups from 182 evidence rows.",
      "payload": { "count": 5 }
    }
  ]
}
```

Full live pull uses **Full live pull complete: stored N new…** and `"pipeline_mode": "full"` in payloads.

### GET /api/runs

```json
{
  "runs": [
    {
      "runId": "8aaa41ec",
      "mode": "scan",
      "modeLabel": "Incremental scan",
      "evidenceNote": "150 searched · +3 new · 147 skipped · incremental",
      "status": "Complete",
      "statusDetail": "All 6 agents finished · 6 recommendation(s)"
    },
    {
      "runId": "c88de439",
      "mode": "full",
      "modeLabel": "Full live pull",
      "evidenceNote": "150 papers · 5 trials · +12 stored · 138 skipped",
      "status": "Complete",
      "statusDetail": "All 6 agents finished · 6 recommendation(s)"
    }
  ]
}
```

### Run status

| Status | Meaning |
|--------|---------|
| **Complete** | Six agents in trace and ≥1 recommendation (or ≥5 recommendations per `run_status.py`) |
| **Partial** | Stopped early — dashboard shows e.g. `3/6` agents, not `?/6` |
| **Failed** | Exception during orchestration |

---

## Ideal candidate profiles (Patient Cluster A–E)

![Ideal candidate profiles panel](/assets/images/dashboard/step2-synthetic-cohort.png)
{: .doc-screenshot }

*Illustrative candidate profiles (Patient Cluster A–E) — synthetic only, no PHI.*

Generated per `run_id` from recommendations + subgroups. **Not stored in the database.** Every profile is labeled synthetic / no PHI.

```json
{
  "run_id": "abc123",
  "synthetic_cohort": [
    {
      "patient_id": "Patient Cluster A",
      "subgroup": "GBA-mutation PD",
      "top_opportunity": "GCase activation",
      "mechanism": "lysosomal dysfunction",
      "confidence": 82.5,
      "is_synthetic": true,
      "phi_free": true
    }
  ]
}
```

Route: `GET /api/synthetic-cohort?run_id=abc123`

---

## Database tables written

| Agent | Tables / columns |
|-------|------------------|
| 1 Literature | `evidence`, `subgroup_evidence`, `scan_state`, `agent_outputs` |
| 2 Subgroups | `subgroups`, `agent_outputs` |
| 3 Connections | `treatment_connections`, `connection_evidence`, `agent_outputs` |
| 4 Evidence | `treatment_connections.evidence_strength`, `agent_outputs` |
| 5 Commercial | `treatment_connections.commercial_potential`, `agent_outputs` |
| 6 Conclusion | `recommendations`, `agent_outputs` |

### Literature agent payload example

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

---

## GET /api/stats

Database overview for the Step 2 KPI strip (before a run switches subtitles to **this run**):

```json
{
  "literature": 228,
  "trial": 39,
  "grant": 40,
  "subgroups": 5,
  "connections": 5,
  "totalEvidence": 307,
  "lastScanAt": "2026-06-02T14:32:00",
  "lastRunId": "a1b2c3d4",
  "database": "sqlite",
  "supabaseConfigured": false
}
```

---

## GET /api/discover/parkinsons

{: .highlight }
**Legacy route** — `disease` is currently hardcoded in `api_server.py` as `"Parkinson's Disease"`. Subgroups and connections reflect the live database.

```json
{
  "disease": "Parkinson's Disease",
  "subgroups": [
    {
      "subgroupId": 1,
      "name": "GBA-mutation PD",
      "definingFeatures": "GBA1 variant carriers; reduced GCase activity",
      "evidenceCount": 2
    }
  ],
  "treatmentConnections": [
    {
      "connectionId": 1,
      "subgroup": "GBA-mutation PD",
      "mechanism": "lysosomal dysfunction",
      "treatment": "GCase activation",
      "evidenceStrength": 8.5,
      "commercialPotential": 7.2,
      "confidence": 80.2
    }
  ]
}
```

---

## Dashboard panels

| Panel | Source |
|-------|--------|
| Step 2 KPI strip | `GET /api/stats` + `runStats` from last run (Tab 2 only) |
| Run status strip | Complete / Partial / Running / Failed |
| Step 1 — Configure & run | `POST /api/run-discovery` |
| Step 2 — Pipeline diagram | Agent trace from `GET /api/agents?run_id=` |
| Ideal candidate profile cards | `synthetic_cohort` in run response |
| Ranked treatments | `GET /api/recommendations?run_id=` |
| Evidence table | `GET /api/evidence?offset=&limit=` |
| Recent runs | `GET /api/runs?limit=5` |
| Step 3 — Grant proposal | `GET /api/cua/demo` · inlined `GET /cua-demo/graded6.html` |

See [Dashboard](dashboard) for how to run the UI locally.
