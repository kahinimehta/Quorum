---
layout: default
title: For judges
nav_order: 6
description: "Final showcase guide — rubric mapping and live demo script"
---

# For judges

**Team:** Quorum · **NeuroDiscover AI**  
**Track:** 02 — Autonomous Research  
**Final showcase:** June 6, 2025

Use this page as a **scorecard companion** — each rubric criterion links to evidence in the repo and live demo.

---

## Rubric mapping

| Criterion (weight) | Where to verify | What to look for |
|--------------------|-----------------|------------------|
| **Problem identification & significance (20%)** | [Problem & significance](problem) | Pfizer-style gap: hidden subgroups, static expert review, continuous evidence |
| **Technical implementation (25%)** | [Workflow](workflow/), [Output examples](output), live demo | Six agents, real API, 300+ evidence rows, BioMCP + SQL blackboard |
| **Creativity & innovation (20%)** | [Architecture](decisions), [Problem](problem) | Evidence-as-contract, skeptic + commercial agents, incremental scan |
| **Team composition & collaboration (10%)** | [Team](team) | Bio + CS + strategy + agent infrastructure |
| **Presentation skills (15%)** | This page + dashboard | 5-minute script below |
| **Execution & professionalism (10%)** | [Site publishing](pages-setup), GitHub Actions deploy | Docs site live, reproducible quick start |

---

## 5-minute live demo script

1. **Open** [https://neurodiscover.github.io](https://neurodiscover.github.io) — problem framing (30 s)  
2. **Local dashboard** — `cd neurodiscover && make dashboard` → `http://127.0.0.1:8080` (or show screenshot if offline)  
3. **Run discovery** — Step 1: mode `demo`, max papers `5` → **Run**  
4. **Show KPI strip** — processed vs in-database counts  
5. **Agent trace** — 6/6 agents, shared `run_id`  
6. **Ranked recommendations** — Prioritize / Monitor / Reject + confidence bars  
7. **Synthetic cohort** — Patients A–E, labeled synthetic / no PHI  
8. **Audit** — click evidence row → real or demo `source_id`  
9. **API** (optional):

```bash
curl -s http://127.0.0.1:5000/api/stats
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"demo","max_papers":5}'
```

---

## Technical depth (implementation)

| Component | Evidence |
|-----------|----------|
| Agent pipeline | `neurodiscover/orchestrator.py` — agents 1→6 |
| Literature ingestion | BioMCP, optional bioRxiv, NIH RePORTER grants |
| LLM extraction | Nebius / Ollama / none (`EXTRACT_BACKEND`) |
| Commercial signals | Tavily web search + grant landscape |
| Persistence | SQLite local or Supabase Postgres |
| Validation | PubTator grounding, consistency checks — [Validation](developer-reference/validation) |

---

## Innovation highlights

- **Database blackboard** — agents decoupled via SQL, not brittle prompt chains  
- **Dual scoring** — evidence strength (skeptic) + commercial potential (discovery)  
- **No hallucinated ids** — `UNIQUE(source_type, source_id)` dedup; demo ids clearly marked  
- **Run status** — Complete vs Partial with explicit agent count (e.g. `6/6`)  
- **Indication-configurable** — not locked to one disease; demo uses seed data for stage safety  

---

## Q&A prep

| Question | Answer |
|----------|--------|
| Is this limited to one disease? | No — `--disease` and API `query` configure the literature pull. Demo seed is generic placeholder labels. |
| How do you prevent fabricated citations? | Agent 1 only inserts ids returned by BioMCP; validation layer flags weak extractions. |
| What is synthetic cohort? | Ephemeral demo patients generated from recommendations — never stored, no PHI. |
| Can this run without cloud keys? | Yes — `make dashboard` offline demo from SQLite seed. |
| Where is the team live DB? | Optional Supabase; 307 evidence rows pre-loaded for judges. |

---

## Repository

- **Code:** [github.com/kahinimehta/Quorum](https://github.com/kahinimehta/Quorum)  
- **Docs:** [neurodiscover.github.io](https://neurodiscover.github.io)  
- **Debugging:** [Debugging guide](debugging) if something fails on stage  
