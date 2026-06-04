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
| Conclusion Update | scores → `recommendations` in orchestrator |

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

See [`AGENT_IO.md`](AGENT_IO.md) and [`DASHBOARD.md`](DASHBOARD.md).
