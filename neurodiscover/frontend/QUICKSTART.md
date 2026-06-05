# NeuroDiscover Dashboard — Quickstart

## One command

From `neurodiscover/`:

```bash
make dashboard
```

Same as `python3 cli.py dashboard` or `./dashboard`.

This will:

1. Install dependencies (unless `--skip-install`)
2. Build local `neurodiscover.db` if missing (skipped when `SUPABASE_DATABASE_URL` is set)
3. Run one offline **demo** pipeline pass
4. Start API on **5000** and UI on **8080**
5. Open **http://127.0.0.1:8080** in your default browser

Press **Ctrl+C** to stop.

### Useful flags

```bash
python3 cli.py dashboard --fresh           # rebuild local DB
python3 cli.py dashboard --skip-pipeline   # servers only
python3 cli.py dashboard --no-browser      # do not auto-open browser
```

## Using the UI

1. **Step 1 — Configure & Run** — set mode (Demo / Incremental scan / Full), max papers, keywords, extraction backend.
2. Click **Run Discovery Pipeline** or **Incremental Scan Only**.
3. **Step 2 — Discovery Results** — synthetic cohort, ranked treatments, hypotheses, agent trace, evidence table.

`make dashboard` only runs demo once at startup. Change settings and rerun from Step 1 while the servers stay up.

**Local demo:** leave `SUPABASE_DATABASE_URL` unset. **Never** run `cli.py build` on the team Supabase DB.

After each run, the KPI strip and summary bar show **this run** counts (e.g. 5 papers used) separately from **in database** totals.

## Manual setup (optional)

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
python3 api_server.py
```

## Verify API

```bash
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":5}'
```

Response includes `runStats.processed` (papers used this run) and `runStats.databaseTotals`.

## Synthetic cohort

Up to five illustrative profiles (Patients A–E) per run. Returned in `POST /api/run-discovery` and via `GET /api/synthetic-cohort?run_id=`. Not stored in the database.

## More detail

- Architecture: [`../../docs/dashboard.md`](../../docs/dashboard.md) · API: [`../../docs/developer-reference/dashboard-api.md`](../../docs/developer-reference/dashboard-api.md)
- API shapes: [`../../docs/developer-reference/backend-queries.md`](../../docs/developer-reference/backend-queries.md)
