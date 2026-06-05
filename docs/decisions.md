---
layout: default
title: Architecture
nav_order: 8
description: "Key design decisions and trade-offs"
---

# Architecture decisions

Why we built NeuroDiscover this way.

---

## SQLite / Postgres, not MongoDB

Early working docs mentioned MongoDB `papers`. The team contract is SQL table **`evidence`** with FK integrity, shared via Supabase Session pooler or local `neurodiscover.db`.

## Database as blackboard

Agents do not call each other directly. They read/write tables so the API, agents, and dashboard can evolve independently.

## No `cli.py build` on live Supabase

`build` truncates all tables. The team DB already has 300+ real rows. Use `scan` / `pull` to add evidence only.

## Vanilla dashboard + FastAPI

Single `index.html` and `api_server.py` avoid build tooling for hackathon demos. Optional Supabase JS keys for direct reads; default path is API-only (no browser secrets).

## Synthetic cohort not persisted

Patient profiles are generated from recommendations + subgroups per `run_id`, labeled synthetic/no PHI, and never stored — reducing HIPAA scope.

## Run status: Complete vs Partial

**Complete** means all six pipeline agents logged output for that `run_id` and recommendations exist. **Partial** means the run stopped early — not a judgment on data quality.

## External tools

| Tool | Role |
|------|------|
| **BioMCP** | Unified PubMed + ClinicalTrials.gov |
| **Nebius / Ollama** | Structured extraction (`EXTRACT_BACKEND`) |
| **Tavily / NIH RePORTER** | Commercial agent signals |

## Documentation site

This site uses [Just the Docs](https://github.com/just-the-docs/just-the-docs) on GitHub Pages. Published to **https://neurodiscover.github.io** via the `neurodiscover/neurodiscover.github.io` org repo (see [Site publishing](pages-setup)).
