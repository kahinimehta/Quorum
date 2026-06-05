---
layout: default
title: Downstream agents
parent: Developer reference
nav_order: 11
---

# Downstream agents (integrated)

Agents 2–6 run in-process via `neurodiscover/orchestrator.py` after literature synthesis (Agent 1).

| Agent | Module |
|-------|--------|
| Patient Subgroup | `agents/patient_subgroup_agent.py` |
| Treatment Connection | `agents/treatment_connection_agent.py` |
| Evidence Scoring | `agents/evidence_scoring_agent.py` |
| Commercial Discovery | `agents/commercial_discovery_agent.py` |
| Conclusion Update (dashboard) | scores → `recommendations` in orchestrator |
| Conclusion Update (CUA) | `cua/` — optional; read-only; local proposal artifacts |

## Input

Evidence rows from the `evidence` table (subgroup, mechanism, treatment, source_id, title, etc.).

## Output

- `subgroups`, `treatment_connections`, `connection_evidence`
- `evidence_strength`, `commercial_potential` on connections
- `recommendations` with Prioritize / Monitor / Reject tiers
- `agent_outputs` trace rows per run

## Scoring

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

See [Agent I/O](agent-io) and [Dashboard API](dashboard-api).

## CUA (optional Agent 6)

The `cua/` package is **not** wired into `orchestrator.py`. After agents 1–5 (or a full pipeline run) have populated the blackboard, run CUA manually:

```bash
cd cua && pip install -e .
export CUA_LIVE=1 ANTHROPIC_API_KEY=...
python -m cua.nih.run_db --db "$SUPABASE_DATABASE_URL" --run-id <id> --capture-content
```

Outputs land under `cua/outputs/` (proposal, trace, audit, ingestion). No `recommendations` or `agent_outputs` writes. Full detail: [Conclusion Update workflow](../workflow/conclusion-update#cua-package-optional--nih-grant-proposal) and `cua/README.md`.
