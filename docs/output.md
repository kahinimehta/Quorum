---
layout: default
title: Output examples
nav_order: 5
description: "API JSON shapes, recommendations, synthetic cohort, and dashboard panels"
---

# Output examples

What NeuroDiscover produces — ranked recommendations, agent trace, synthetic patients, and API response shapes.

---

## Dashboard — Step 2 (Discovery Results)

After a run completes, **Step 2** shows pipeline outputs: synthetic cohort, ranked treatments, hypotheses, agent trace, and evidence audit.

At the top, **This run** shows:

- A **progress bar** and compact **agent stepper** (Running → Done) visible while the pipeline executes and after complete
- **Run settings** used (mode, disease, max papers, keyword, extraction) — changes when you change Step 1
- **Evidence scored** and **DB delta** for this run — changes when pulls add rows or demo caps differ
- **Run signature** — a one-line fingerprint (`run_id · mode · max · keyword · scored · +new`)
- **Support rows** table — per-connection evidence counts and confidence (changes when corpus or caps differ)

![Step 2 — Discovery results overview](/assets/images/dashboard/step2-discovery-results.png)
{: .doc-screenshot }

*Step 2 — synthetic cohort, ranked outputs, hypotheses, agent trace, and evidence table.*

---

## Dashboard — Step 3 (Grant Proposal · CUA)

**Step 3** is separate from pipeline rankings and **not run-scoped**. It always loads the static bundled CUA demo (`graded6`) via `GET /api/cua/demo` and inlines `/cua-demo/graded6.html` in the page (single scroll, no nested frame) — unchanged no matter which pipeline run you view in Step 2.

![Step 3 — CUA grant proposal tab](/assets/images/dashboard/step3-cua-grant-proposal.png)
{: .doc-screenshot }

*Step 3 — central hypothesis, specific aims, KPI strip (corpus → writer view, critic scores), and the interactive CUA pipeline report.*

To generate a new proposal from your database, run `python -m cua.nih.run_db` (see [Conclusion Update → CUA](workflow/conclusion-update#cua-package-optional--nih-grant-proposal)).

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
      "patient_id": "Patient A",
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
    }
  ]
}
```

Scoring:

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Tier | Condition |
|------|-----------|
| Prioritize | confidence ≥ 80 |
| Monitor | 65 ≤ confidence < 80 |
| Reject | confidence < 65 |

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

*Agent run trace (shared `run_id`) and paginated evidence preview with source links.*

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

## Synthetic cohort (Patients A–E)

![Synthetic cohort panel](/assets/images/dashboard/step2-synthetic-cohort.png)
{: .doc-screenshot }

*Illustrative patient profiles (A–E) — synthetic only, no PHI.*

Generated per `run_id` from recommendations + subgroups. **Not stored in the database.** Every profile is labeled synthetic / no PHI.

```json
{
  "run_id": "abc123",
  "synthetic_cohort": [
    {
      "patient_id": "Patient A",
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

Database overview for dashboard KPI tiles:

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
| KPI strip | `GET /api/stats` + `runStats` from last run |
| Run status strip | Complete / Partial / Running / Failed |
| Step 1 — Configure & run | `POST /api/run-discovery` |
| Step 2 — Pipeline diagram | Agent trace from `GET /api/agents?run_id=` |
| Synthetic cohort cards | `synthetic_cohort` in run response |
| Ranked treatments | `GET /api/recommendations?run_id=` |
| Evidence table | `GET /api/evidence?offset=&limit=` |
| Recent runs | `GET /api/runs?limit=5` |

See [Dashboard](dashboard) for how to run the UI locally.
