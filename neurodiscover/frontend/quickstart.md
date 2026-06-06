# NeuroDiscover Dashboard — Quickstart

## Requirements

| Item | Detail |
|------|--------|
| **Python** | **3.10, 3.11, or 3.12** (required). Check with `python3 --version`. Python 3.13+ is not tested with `biomcp-python` yet. |
| **OS** | macOS, Linux, or Windows |
| **Runtime deps** | [`requirements.txt`](../requirements.txt) — API, agents, CLI, literature pull |
| **Conda env** | [`environment.yml`](../environment.yml) — creates env `neurodiscover` from an empty conda environment |
| **Optional dev** | [`requirements-dev.txt`](../requirements-dev.txt) — Playwright for doc screenshots only |

`sqlite3` is in the Python standard library. No Node.js or frontend build step.

---

## Get the repo

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
cp .env.example .env   # optional: SUPABASE_DATABASE_URL for team DB
```

---

## Install dependencies

Pick **one** path below before running the dashboard.

### Option A — pip (venv or existing Python)

Use a Python in the **3.10–3.12** range:

```bash
python3 --version          # e.g. Python 3.12.x
python3 -m venv .venv      # recommended
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt
```

Verify the BioMCP CLI is on your PATH (needed for incremental scan / full pull):

```bash
which biomcp    # should print a path inside your venv or env
biomcp --help
```

### Option B — conda (empty environment)

From `neurodiscover/`:

```bash
conda env create -f environment.yml
conda activate neurodiscover
python --version           # should be 3.10.x – 3.12.x
which biomcp
```

Update after pulling dependency changes:

```bash
conda activate neurodiscover
conda env update -f environment.yml --prune
```

### Optional — dev / doc screenshots

Not required for the dashboard or API:

```bash
pip install -r requirements-dev.txt
playwright install chromium
# With API + UI already running (make dashboard --no-browser):
python3 scripts/capture_dashboard_screenshots.py
# → writes PNGs to docs/assets/images/dashboard/
```

---

## One command

From `neurodiscover/` (with deps installed and env activated):

```bash
make dashboard
```

**macOS / Linux:** `make dashboard` (same as `python3 cli.py dashboard`). **Windows:** use `python cli.py dashboard`.

Equivalents:

```bash
python3 cli.py dashboard
./dashboard          # bash — macOS/Linux; Git Bash or WSL on Windows
```

On Windows without `make`:

```bash
python cli.py dashboard
```

This will:

1. Install dependencies (unless `--skip-install`) via `pip install -r requirements.txt`
2. Build local `neurodiscover.db` if missing (skipped when `SUPABASE_DATABASE_URL` is set)
3. Run one pipeline pass before serving (unless `--skip-pipeline`):
   - **Local SQLite:** offline **demo** with `max_papers=10`
   - **Team Supabase:** **agents-only** on all existing evidence (no literature pull)
4. Start API (default **5000**, auto-fallback if busy) and UI on **8080**
5. Open the URL printed by the launcher (default `http://127.0.0.1:8080/?api=http://127.0.0.1:5000`; always includes `?api=`)

Press **Ctrl+C** to stop.

---

## Platform notes

| Platform | Tip |
|----------|-----|
| **Windows** | `make` is often not installed — use `python cli.py dashboard` |
| **Windows** | `./dashboard` needs **Git Bash** or **WSL** |
| **Linux / WSL / SSH / headless VM** | Use `--no-browser` and open the **`Open:` URL** from launcher output |
| **macOS** | Port **5000** may conflict with **AirPlay Receiver** (System Settings → General → AirDrop & Handoff) — use alternate ports below or disable AirPlay |
| **Any OS** | Wrong Python version? Use 3.10–3.12. Missing packages? Re-run `pip install -r requirements.txt` or `conda env update -f environment.yml --prune` |
| **Conda** | Always `conda activate neurodiscover` before `make dashboard` |

---

## Useful flags

```bash
python3 cli.py dashboard --no-browser      # do not auto-open browser
python3 cli.py dashboard --skip-pipeline   # start API + UI only
python3 cli.py dashboard --fresh           # rebuild local DB
python3 cli.py dashboard --skip-install    # skip pip install step (deps already installed)
python3 cli.py dashboard --port-api 5001 --port-ui 8081   # alternate ports
```

Minimal path (deps already installed, no browser):

```bash
python3 cli.py dashboard --skip-install --no-browser
# → copy the Open: URL from launcher output (includes ?api=)
```

---

## Using the UI

1. **Step 1 — Configure & Run** — pick **pipeline mode** (Rescore DB / Demo sample / Incremental scan / Full live pull), disease (default **Parkinson's**), max papers, keywords, extraction backend.
2. Click the **run button** (label matches the selected mode). The **run status strip** shows pipeline progress while agents run.
3. **Step 2 — Discovery Results** — KPI strip and panels full-width (minimal side padding); ideal candidate profiles and ranked treatments match the research hypotheses column height (scroll when longer; bars show `Treatment · Subgroup`); hypotheses use scores from **this run’s** recommendations; discovery pipeline diagram below; **Audit & provenance** collapsed by default — expand for agent trace + evidence table.
4. **Step 3 — Grant Proposal** — static bundled `graded6` demo (not tied to your `run_id`). Hero KPIs (corpus · verified papers · citations · Critic F1/F2/F3), **Jump to** (Proposal · Grant pipeline · Supporting details). **The proposal** stays expanded; **Grant pipeline** and **Pipeline trace & audit** are separate collapsed blocks. Report toolbar shows **`x/y obligations satisfied`**. **Run a live grant proposal (CLI)** is collapsible at the bottom. For a live run: `cd cua && pip install -e .` then `python -m cua.nih.run_db` with `ANTHROPIC_API_KEY` + `CUA_LIVE=1` (see `cua/README.md`).

`make dashboard` only runs demo once at startup. Change settings and rerun from Step 1 while the servers stay up.

**Confidence** updates when new evidence rows with `subgroup` + `mechanism` + `treatment` land in the DB and agents 2–6 rerun. Rescore on the same corpus without new rows may show similar numbers; check the literature step for `Stored N new evidence`.

**Pipeline modes explained** (Demo vs Rescore, max papers, incremental vs full, timing): [docs/input.md — pipeline modes FAQ](../../docs/input.md#recommended-workflow) · [Step 3 grant tab sections](../../docs/dashboard.md#step-3--report-structure) on [neurodiscover.github.io](https://neurodiscover.github.io).

**Local demo:** leave `SUPABASE_DATABASE_URL` unset. **Never** run `cli.py build` on the team Supabase DB.

**Team Supabase:** set `SUPABASE_DATABASE_URL` in `.env`, then run `make dashboard` — same command. The launcher runs **agents-only** (agents 2–6 on the full corpus) so connections and recommendations appear on first load.

On **Step 2**, the KPI strip above Discovery Results switches to **this run** counts (papers, trials, grants used by agents 2–6).

---

## Manual setup (optional)

If you prefer two terminals instead of the one-command launcher, install deps first (pip or conda above), then:

```bash
cd neurodiscover
python3 cli.py build      # local SQLite only — never on team Supabase
python3 api_server.py
```

Second terminal:

```bash
cd neurodiscover/frontend
python3 -m http.server 8080
```

Header shows **DB LIVE** when the API is connected (local SQLite or Supabase backend).

---

## Team Supabase (optional)

In `.env`:

| Key | Purpose |
|-----|---------|
| `SUPABASE_DATABASE_URL` | Backend reads/writes (Session pooler URI) |
| `SUPABASE_URL` + `SUPABASE_ANON_KEY` | Optional direct browser reads |

```bash
python3 cli.py validate   # not build
make dashboard            # agents-only pipeline + API + UI
```

Or API only:

```bash
python3 api_server.py
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"agents-only","max_papers":0}'
```

---

## Verify API

```bash
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":10,"wait":true}'
```

Response includes `runStats.processed` (papers used this run) and `runStats.databaseTotals`.

---

## Ideal candidate profiles

Up to five illustrative profiles (Patient Cluster A–E) per run. Returned in `POST /api/run-discovery` and via `GET /api/synthetic-cohort?run_id=`. Not stored in the database.

---

## More detail

- Web docs: [neurodiscover.github.io](https://neurodiscover.github.io) — [Dashboard](https://neurodiscover.github.io/dashboard/) · [Debugging](https://neurodiscover.github.io/debugging/)
- Architecture: [`../../docs/dashboard.md`](../../docs/dashboard.md) · API: [`../../docs/developer-reference/dashboard-api.md`](../../docs/developer-reference/dashboard-api.md)
- API shapes: [`../../docs/developer-reference/backend-queries.md`](../../docs/developer-reference/backend-queries.md)
