---
layout: default
title: Home
nav_order: 1
description: "Agentic commercial development discovery — quick start and overview"
---

# NeuroDiscover AI

{: .fs-5 .fw-300 }

Six agents · one evidence store · ranked commercial discovery · grant proposal

<div class="video-embed-wrap">
  <div class="video-embed">
    <iframe src="https://www.youtube-nocookie.com/embed/32vsR5R4hHM?modestbranding=1&amp;rel=0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
  </div>
</div>

<div class="home-meta" markdown="1">

| | |
|:--|:--|
| Team | **Quorum** |
| Track | **02 — Autonomous Research** |
| Partner | Pfizer Commercial Development Discovery |
| Code | [github.com/kahinimehta/Quorum](https://github.com/kahinimehta/Quorum) |

</div>

{: .home-lede }

Continuously ingest literature and trials, surface hidden patient subgroups, map subgroup → mechanism → treatment, and rank opportunities by evidence and commercial potential.

---

## What problem we solve

Traditional portfolio review evaluates a **small set** of opportunities over **months**, using expert taxonomies that structurally miss:

- Patient subgroups hidden inside a heterogeneous indication  
- Mechanisms that connect conditions thought to be unrelated  
- White-space signals that only appear when literature, trials, and funding are synthesized continuously  

NeuroDiscover is an **AI-native alternative**: six agents share a SQL evidence store, update conclusions as new sources arrive, and output auditable **Prioritize / Monitor / Reject** tiers.

See [Problem & significance](problem) for full framing.

## How ranking works

```
confidence = evidence_strength × 0.55 + commercial_potential × 0.45
```

Scores **scale with per-connection evidence count** — new literature, trials, or tagged grants move confidence when agents 2–6 rerun after a pull. See [Output examples — when confidence changes](output#when-confidence-changes).

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

See [Architecture decisions](decisions) for trade-offs · [Design & engineering](design) for modularity and technical patterns.

## Quick start

Requires **Python 3.10, 3.11, or 3.12** on macOS, Linux, or Windows.

**pip:**

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
python3 --version          # must be 3.10.x – 3.12.x
pip install -r requirements.txt
cp .env.example .env
make dashboard    # same as: python3 cli.py dashboard
```

**conda (empty environment):**

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
conda env create -f environment.yml
conda activate neurodiscover
cp .env.example .env
make dashboard
```

Opens the URL printed by the launcher (UI on **8080**, API default **5000** with auto-fallback; URL always includes `?api=` so the static server reaches FastAPI). Press **Ctrl+C** to stop.

**Three tabs:** Step 1 configure & run · Step 2 ranked results · Step 3 static CUA grant proposal (bundled `graded6` demo — proposal first, grouped pipeline/writer/booster/audit sections, jump-to nav).

{: .highlight }
**Windows:** use `python cli.py dashboard` if `make` is not installed. **SSH / headless:** add `--no-browser` and open the **`Open:` URL** from launcher output.

Full setup, platform notes, and flags → [Run the dashboard](dashboard) · [Debugging](debugging)

{: .important }
**Team live database:** Supabase holds 300+ real evidence rows. Set `SUPABASE_DATABASE_URL` in `.env` and **do not** run `cli.py build` (it truncates all tables). Use `scan` / `pull` to add evidence only.

## Repository map

| Path | Role |
|------|------|
| `neurodiscover/agents/` | Six pipeline agents |
| `neurodiscover/orchestrator.py` | Wires agents 1→6 for API runs |
| `neurodiscover/api_server.py` | FastAPI backend (:5000) |
| `neurodiscover/frontend/index.html` | Dashboard UI (:8080) — Steps 1–3 |
| `cua/` | Optional grant-proposal Agent 6 (CLI; dashboard Step 3 = static demo) |
| `docs/` | This documentation site |

## Next steps

- [Problem & significance](problem) — unmet need and track alignment  
- [Workflow](workflow/) — six-agent pipeline  
- [Design & engineering](design) — modularity, blackboard pattern, technical proficiency  
- [Inputs](input) · [Output examples](output)  
- [Team](team) — interdisciplinary roles  
- [Debugging](debugging) — deploy, API, and pipeline troubleshooting  
- [Run the dashboard](dashboard) — UI walkthrough  
