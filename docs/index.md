---
layout: default
title: Home
nav_order: 1
description: "Purpose, rationale, and quick start for NeuroDiscover AI"
---

# NeuroDiscover AI

{: .fs-6 .fw-300 }

Multi-agent Parkinson's disease discovery — hidden patient subgroups, treatment connections, and ranked recommendations for research and development.

---

## Purpose

NeuroDiscover is a **multi-agent discovery system** for Parkinson's disease (PD). It ingests public **literature**, **clinical trials**, and **NIH grants**; identifies **patient subgroups**; maps **subgroup → mechanism → treatment** connections; scores evidence and commercial potential; and ranks opportunities for research and development.

Final ranking uses a transparent formula:

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Tier | Rule |
|------|------|
| **Prioritize** | confidence ≥ 80 |
| **Monitor** | 65 ≤ confidence < 80 |
| **Reject** | confidence < 65 |

## Why this architecture

- **Hidden subgroups** — PD is heterogeneous (genetic, inflammatory, progression rate). One-size-fits-all trials miss signal.
- **Evidence as contract** — Every claim links to real PMIDs, NCT ids, or grants in a shared SQL database (not hallucinated ids).
- **Database blackboard** — Six agents run in sequence; each reads prior tables and writes its own. The dashboard and API read the same store.
- **Safe demo** — Synthetic patient profiles (Patients A–E) illustrate outputs with **no PHI** for judges and stakeholders.
- **Reproducibility** — Schema in git; local SQLite for laptops; optional team Supabase for shared live data.

See [Architecture decisions](decisions) for trade-offs.

## Quick start

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
pip install -r requirements.txt
cp .env.example .env   # optional: SUPABASE_DATABASE_URL for team DB
make dashboard
```

This will:

1. Build local `neurodiscover.db` if missing (skipped when `SUPABASE_DATABASE_URL` is set)
2. Run one offline **demo** pipeline pass
3. Start the API on **port 5000** and UI on **port 8080**
4. Open **http://127.0.0.1:8080** in your browser

Press **Ctrl+C** to stop both servers.

{: .important }
**Team live database:** Supabase already holds 300+ real evidence rows. Set `SUPABASE_DATABASE_URL` in `.env` and **do not** run `cli.py build` (it truncates all tables). Use `scan` / `pull` to add evidence only.

## Repository map

| Path | Role |
|------|------|
| `neurodiscover/agents/` | Six pipeline agents |
| `neurodiscover/orchestrator.py` | Wires agents 1→6 for API runs |
| `neurodiscover/api_server.py` | FastAPI backend (:5000) |
| `neurodiscover/frontend/index.html` | Dashboard UI (:8080) |
| `docs/` | This documentation site |

## Next steps

- [Workflow](workflow/) — six-agent pipeline and per-agent detail
- [Inputs](input) — what goes into the system
- [Output examples](output) — JSON shapes and dashboard panels
- [Team](team) — Quorum contributors
- [Run the dashboard](dashboard) — UI walkthrough
