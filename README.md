# Quorum — NeuroDiscover AI

> **Collaborators:** The **dashboard**, **demo video** (`docs/demo_draft.mp4`), and **[docs site](https://neurodiscover.github.io)** are still being edited. Expect layout and copy changes before the showcase.

**Quorum** — six agents, one evidence store, ranked commercial discovery.

Agentic system for **commercial development discovery**: continuously ingest literature and trials, surface hidden patient subgroups inside heterogeneous indications, map **subgroup → mechanism → treatment** connections, and rank opportunities by evidence and commercial potential.

**Live docs:** [neurodiscover.github.io](https://neurodiscover.github.io) · **Track:** 02 — Autonomous Research · **Partner framing:** Pfizer Commercial Development Discovery

---

## Demo (draft)

<video src="docs/demo_draft.mp4" controls width="100%">
  <a href="docs/demo_draft.mp4">Download demo video</a>
</video>

**File:** `docs/demo_draft.mp4` (~71 MB). Under GitHub’s **100 MB per-file limit** — commit it **directly** (do **not** use Git LFS; LFS breaks the README `<video>` embed).

```bash
# From your machine (copy into the repo if needed)
cp /path/to/demo_draft.mp4 docs/demo_draft.mp4
git add docs/demo_draft.mp4
git commit -m "docs: add demo draft video"
git push
```

GitHub may warn that the file is over 50 MB — that is expected; the push should still succeed.

**Optional — smaller clone / faster load** (re-encode before commit):

```bash
ffmpeg -i docs/demo_draft.mp4 -vcodec libx264 -crf 28 -preset slow -movflags +faststart docs/demo_draft_compressed.mp4
mv docs/demo_draft_compressed.mp4 docs/demo_draft.mp4
```

---

## Quick start

Requires **Python 3.10+** on macOS, Linux, or Windows. `make dashboard` is shorthand for `python3 cli.py dashboard` — not Mac-only.

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
| **macOS** | Port **5000** may be used by **AirPlay Receiver** — use `--port-api 5001 --port-ui 8081` or disable AirPlay |
| **Any OS** | Port in use? `python3 cli.py dashboard --port-api 5001 --port-ui 8081 --no-browser` |

Useful flags: `--no-browser`, `--skip-pipeline` (servers only), `--fresh` (rebuild local DB).

More detail: [`docs/dashboard.md`](docs/dashboard.md) · [`neurodiscover/frontend/quickstart.md`](neurodiscover/frontend/quickstart.md) · [Debugging](https://neurodiscover.github.io/debugging/)

> **Team live database:** Supabase holds 300+ real evidence rows. Set `SUPABASE_DATABASE_URL` in `.env` and **do not** run `cli.py build` (it truncates all tables). Use `scan` / `pull` to add evidence only.

---

## Start here

| Audience | Document |
|----------|----------|
| Cursor / coding agents | [`AGENTS.md`](AGENTS.md) |
| Humans onboarding | [`CONTRIBUTING.md`](CONTRIBUTING.md) |
| **Project docs (web)** | **[neurodiscover.github.io](https://neurodiscover.github.io)** — Jekyll + Just the Docs ([source](docs/index.md)) |
| Database contract | [`docs/developer-reference/database.md`](docs/developer-reference/database.md) |

**Storage:** SQLite locally, or **Supabase Postgres** for the team shared DB (`SUPABASE_DATABASE_URL`). Table name is **`evidence`**, not `papers`. See [`docs/developer-reference/database.md`](docs/developer-reference/database.md) and [`docs/developer-reference/supabase.md`](docs/developer-reference/supabase.md).

## CLI (without dashboard)

```bash
cd neurodiscover
pip install -r requirements.txt
cp .env.example .env
python3 cli.py build      # local SQLite only — never on team Supabase
python3 cli.py validate
python3 cli.py demo       # safe offline literature-agent run
python3 cli.py pull --disease "your condition" --max 150
```

## Repo layout

```
Quorum/
  AGENTS.md
  docs/                  # Jekyll site (Just the Docs) → neurodiscover.github.io
  docs/demo_draft.mp4    # demo video (draft)
  queries.sql
  neurodiscover/
    cli.py               # entry point — run all commands from here
    schema.sql, schema.pg.sql, seed_data.json
    db.py, seed.py, paths.py, db_validate.py
    agents/
      literature_agent.py    # Agent 1 (literature synthesis)
    ingestion/
      grants_pull.py         # NIH RePORTER grants
    validation/
      consistency.py, pubtator.py, spot_check.py, report.py
    scripts/
      export_team_keys.py
    models/
      schemas.py             # Person 2 API DTOs (not DB schema)
    api_server.py            # FastAPI dashboard backend (:5000)
    orchestrator.py          # Agents 1→6 pipeline for POST /api/run-discovery
    frontend/
      index.html             # Dashboard UI
      quickstart.md          # Dashboard quick start
```

Dashboard docs: [`docs/dashboard.md`](docs/dashboard.md) (UI) · [`docs/developer-reference/dashboard-api.md`](docs/developer-reference/dashboard-api.md) (API contract).

## Team

See [`docs/team.md`](docs/team.md) on the docs site for roles and collaboration.
