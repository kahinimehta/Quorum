---
layout: default
title: Developer reference
nav_order: 10
has_children: true
description: "Schema, agent I/O, API contracts"
---

# Developer reference

Contract documents for schema, agent I/O, backend SQL, and validation. These are the source of truth for Person 2 (backend) and Person 4 (agents).

---

## Documents

| Page | Audience |
|------|----------|
| [Database schema](DATABASE) | Everyone — tables, columns, SQLite vs Postgres |
| [Agent I/O](AGENT_IO) | Agent authors — reads/writes per agent |
| [Backend queries](BACKEND_QUERIES) | API — SQL + JSON shapes |
| [API endpoints](PERSON2_API_ENDPOINTS) | Route list |
| [Person 2 backend](PERSON2_BACKEND) | Supabase handoff |
| [Dashboard API](DASHBOARD) | Dashboard ↔ API contract |
| [Literature pull](LITERATURE_PULL) | BioMCP, MCP env vars |
| [Validation](VALIDATION) | Extraction QA |
| [Supabase](SUPABASE) | Team shared DB |
| [Team env sharing](TEAM_ENV_SHARING) | `.env` distribution |
| [Downstream agents](REMAINING_AGENTS) | Agents 2–6 integration notes |

Also see root [`queries.sql`](https://github.com/kahinimehta/Quorum/blob/main/queries.sql) and [`AGENTS.md`](https://github.com/kahinimehta/Quorum/blob/main/AGENTS.md) in the repo.
