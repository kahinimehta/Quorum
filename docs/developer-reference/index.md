---
layout: default
title: Developer reference
nav_order: 11
has_children: true
description: "Schema, agent I/O, API reference"
---

# Developer reference

Schema, agent I/O, backend SQL, validation, and API docs. Start with [Database schema](database) and [Agent I/O](agent-io) when changing agents or tables.

---

## Documents

| Page | Audience |
|------|----------|
| [Database schema](database) | Everyone — tables, columns, SQLite vs Postgres |
| [Agent I/O](agent-io) | Agent authors — reads/writes per agent |
| [Backend queries](backend-queries) | API — SQL + JSON shapes |
| [API endpoints](api-endpoints) | Route list |
| [Person 2 backend](person2-backend) | Supabase handoff |
| [Dashboard API](dashboard-api) | Dashboard ↔ API |
| [Literature pull](literature-pull) | BioMCP, MCP env vars |
| [Validation](validation) | Extraction QA |
| [Supabase](supabase) | Team shared DB |
| [Team env sharing](team-env-sharing) | `.env` distribution |
| [Downstream agents](remaining-agents) | Agents 2–6 integration notes |
| [Debugging](../debugging) | Deploy, API, and pipeline troubleshooting |

Also see root [`queries.sql`](https://github.com/kahinimehta/Quorum/blob/main/queries.sql) and [`AGENTS.md`](https://github.com/kahinimehta/Quorum/blob/main/AGENTS.md) in the repo.
