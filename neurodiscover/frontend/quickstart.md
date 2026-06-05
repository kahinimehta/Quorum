# NeuroDiscover Dashboard — Quickstart

## Get the repo

```bash
git clone https://github.com/kahinimehta/Quorum.git
cd Quorum/neurodiscover
pip install -r requirements.txt
cp .env.example .env   # optional: SUPABASE_DATABASE_URL for team DB
```

## One command

From `neurodiscover/`:

```bash
make dashboard
```

**Cross-platform:** works on **macOS, Linux, and Windows** with **Python 3.10, 3.11, or 3.12**. `make dashboard` is not Mac-only — it runs `python3 cli.py dashboard` under the hood.

Equivalents:

```bash
python3 cli.py dashboard
./dashboard          # bash — macOS/Linux; Git Bash or WSL on Windows
```

**Conda:**

```bash
conda env create -f environment.yml
conda activate neurodiscover
cp .env.example .env
make dashboard
```

On Windows without `make`:

```bash
python cli.py dashboard
```

This will:

1. Install dependencies (unless `--skip-install`)
2. Build local `neurodiscover.db` if missing (skipped when `SUPABASE_DATABASE_URL` is set)
3. Run one pipeline pass before serving (unless `--skip-pipeline`):
   - **Local SQLite:** offline **demo** with `max_papers=10`
   - **Team Supabase:** **agents-only** on all existing evidence (no literature pull)
4. Start API on **5000** and UI on **8080**
5. Open **http://127.0.0.1:8080** in your default browser (unless `--no-browser`)

Press **Ctrl+C** to stop.

## Platform notes

| Platform | Tip |
|----------|-----|
| **Windows** | `make` is often not installed — use `python cli.py dashboard` |
| **Windows** | `./dashboard` needs **Git Bash** or **WSL** |
| **Linux / WSL / SSH / headless VM** | Use `--no-browser` and open `http://127.0.0.1:8080` manually |
| **macOS** | Port **5000** may conflict with **AirPlay Receiver** (System Settings → General → AirDrop & Handoff) — use alternate ports below or disable AirPlay |
| **Any OS** | Missing packages? Run `pip install -r requirements.txt` first |

## Useful flags

```bash
python3 cli.py dashboard --no-browser      # do not auto-open browser
python3 cli.py dashboard --skip-pipeline   # start API + UI only
python3 cli.py dashboard --fresh           # rebuild local DB
python3 cli.py dashboard --skip-install    # skip pip install step
python3 cli.py dashboard --port-api 5001 --port-ui 8081   # alternate ports
```

Minimal path (no auto-install, no browser):

```bash
pip install -r requirements.txt
python3 cli.py dashboard --no-browser
# → open http://127.0.0.1:8080 manually
```

## Using the UI

1. **Step 1 — Configure & Run** — pick **pipeline mode** (Rescore DB / Demo sample / Incremental scan / Full live pull), disease (default **Parkinson's**), max papers, keywords, extraction backend.
2. Click the **run button** (label matches the selected mode). The **agent pipeline stepper** shows one agent **Running…** at a time; others **Waiting…** until **Done**.
3. **Step 2 — Discovery Results** — synthetic cohort, ranked treatments, hypotheses, agent trace, evidence table (scores from **this run’s** recommendations).

`make dashboard` only runs demo once at startup. Change settings and rerun from Step 1 while the servers stay up.

**Confidence** updates when new evidence rows with `subgroup` + `mechanism` + `treatment` land in the DB and agents 2–6 rerun. Rescore on the same corpus without new rows may show similar numbers; check the literature step for `Stored N new evidence`.

**Local demo:** leave `SUPABASE_DATABASE_URL` unset. **Never** run `cli.py build` on the team Supabase DB.

**Team Supabase:** set `SUPABASE_DATABASE_URL` in `.env`, then run `make dashboard` — same command. The launcher runs **agents-only** (agents 2–6 on the full corpus) so connections and recommendations appear on first load.

After each run, the KPI strip and summary bar show **this run** counts (e.g. 5 papers used) separately from **in database** totals.

## Manual setup (optional)

If you prefer two terminals instead of the one-command launcher:

```bash
cd neurodiscover
pip install -r requirements.txt
python3 cli.py build
python3 api_server.py
```

Second terminal:

```bash
cd neurodiscover/frontend
python3 -m http.server 8080
```

Badge should read **Local API** when browser Supabase keys are unset.

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

## Verify API

```bash
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":10}'
```

Response includes `runStats.processed` (papers used this run) and `runStats.databaseTotals`.

## Synthetic cohort

Up to five illustrative profiles (Patients A–E) per run. Returned in `POST /api/run-discovery` and via `GET /api/synthetic-cohort?run_id=`. Not stored in the database.

## More detail

- Web docs: [neurodiscover.github.io](https://neurodiscover.github.io) — [Dashboard](https://neurodiscover.github.io/dashboard/) · [Debugging](https://neurodiscover.github.io/debugging/)
- Architecture: [`../../docs/dashboard.md`](../../docs/dashboard.md) · API: [`../../docs/developer-reference/dashboard-api.md`](../../docs/developer-reference/dashboard-api.md)
- API shapes: [`../../docs/developer-reference/backend-queries.md`](../../docs/developer-reference/backend-queries.md)
