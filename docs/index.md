---
layout: default
title: Home
nav_order: 1
description: "Agentic commercial development discovery — quick start and overview"
---

# NeuroDiscover AI

{: .fs-6 .fw-300 }

**Quorum** — agentic system for **commercial development discovery**: continuously ingest literature and trials, surface **hidden patient subgroups** inside heterogeneous indications, map **subgroup → mechanism → treatment** connections, and rank opportunities by evidence and commercial potential.

**Live docs:** [https://neurodiscover.github.io](https://neurodiscover.github.io) · **Track:** Autonomous Research (Literature synthesis, hypothesis generation & evidence tracking) · **Partner framing:** Pfizer Commercial Development Discovery

---

## What problem we solve

Traditional portfolio review evaluates a **small set** of opportunities over **months**, using expert taxonomies that structurally miss:

- Patient subgroups hidden inside a heterogeneous indication  
- Mechanisms that connect conditions thought to be unrelated  
- White-space signals that only appear when literature, trials, and funding are synthesized continuously  

NeuroDiscover is an **AI-native alternative**: six agents share a SQL evidence store, update conclusions as new sources arrive, and output auditable **Prioritize / Monitor / Reject** tiers.

See [Problem & significance](problem) for full framing and [For judges](for-judges) for rubric alignment.

## How ranking works

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

| Tier | Rule |
|------|------|
| **Prioritize** | confidence ≥ 80 |
| **Monitor** | 65 ≤ confidence < 80 |
| **Reject** | confidence < 65 |

## Why this architecture

- **Hidden subgroups** — Heterogeneous indications need subgroup-aware discovery, not one-size-fits-all review.  
- **Evidence as contract** — Every claim links to real PMIDs, NCT ids, or grants (no invented ids).  
- **Database blackboard** — Agents read/write SQL tables; dashboard and API share one store.  
- **Safe demo** — Synthetic patient profiles (A–E) illustrate outputs with **no PHI**.  
- **Indication-agnostic** — Configure disease/condition via CLI or API; demo seed data is illustrative only.

See [Architecture decisions](decisions) for trade-offs.

## Quick start

**Works on macOS, Linux, and Windows** — you only need **Python 3.10+** and a browser. `make dashboard` is shorthand for `python3 cli.py dashboard`; it is not Mac-specific.

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
pip install -r requirements.txt
cp .env.example .env   # optional: SUPABASE_DATABASE_URL for team DB
make dashboard
```

Same without `make`:

```bash
python3 cli.py dashboard
# or: ./dashboard   (bash — macOS, Linux, Git Bash / WSL on Windows)
```

This will:

1. Install dependencies if needed (unless `--skip-install`)
2. Build local `neurodiscover.db` if missing (skipped when `SUPABASE_DATABASE_URL` is set)
3. Run one offline **demo** pipeline pass
4. Start the API on **port 5000** and UI on **port 8080**
5. Open **http://127.0.0.1:8080** in your default browser (skip with `--no-browser`)

Press **Ctrl+C** to stop both servers.

### Platform notes

| Platform | Tip |
|----------|-----|
| **Windows** | `make` is often missing — use `python cli.py dashboard` (or `python3` if available) |
| **Windows** | `./dashboard` needs **Git Bash** or **WSL** |
| **Linux / WSL / SSH** | Use `--no-browser` and open `http://127.0.0.1:8080` manually |
| **macOS** | Port **5000** may be used by **AirPlay Receiver** — use `--port-api 5001 --port-ui 8081` or disable AirPlay in System Settings |
| **Any OS** | Port in use? `python3 cli.py dashboard --port-api 5001 --port-ui 8081 --no-browser` |

Useful flags: `--no-browser`, `--skip-pipeline` (servers only), `--fresh` (rebuild local DB).

Full dashboard walkthrough: [Run the dashboard](dashboard). Troubleshooting: [Debugging](debugging).

{: .important }
**Team live database:** Supabase holds 300+ real evidence rows. Set `SUPABASE_DATABASE_URL` in `.env` and **do not** run `cli.py build` (it truncates all tables). Use `scan` / `pull` to add evidence only.

## Repository map

| Path | Role |
|------|------|
| `neurodiscover/agents/` | Six pipeline agents |
| `neurodiscover/orchestrator.py` | Wires agents 1→6 for API runs |
| `neurodiscover/api_server.py` | FastAPI backend (:5000) |
| `neurodiscover/frontend/index.html` | Dashboard UI (:8080) |
| `docs/` | This documentation site |

## Next steps

- [Problem & significance](problem) — unmet need and track alignment  
- [Workflow](workflow/) — six-agent pipeline  
- [Inputs](input) · [Output examples](output)  
- [Team](team) — interdisciplinary roles  
- [For judges](for-judges) — rubric mapping  
- [Debugging](debugging) — deploy, API, and pipeline troubleshooting  
- [Run the dashboard](dashboard) — UI walkthrough  
