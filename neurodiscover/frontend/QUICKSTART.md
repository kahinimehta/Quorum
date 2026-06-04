# NeuroDiscover Dashboard — Quickstart (< 5 min)

## One command: `dashboard`

From the `neurodiscover/` folder, run **one word**:

```bash
cd neurodiscover
make dashboard
```

Same thing:

```bash
python3 cli.py dashboard
```

Or:

```bash
./dashboard
```

That single command will:

1. Install Python dependencies (`pip install -r requirements.txt`)
2. Build local `neurodiscover.db` if needed (skipped when `SUPABASE_DATABASE_URL` is set)
3. Run the offline demo pipeline (agents + synthetic cohort data)
4. Start the API on port **5000** and the UI on port **8080**

Then open **http://127.0.0.1:8080** — press **Ctrl+C** in the terminal to stop both servers.

### Rerunning with different settings

`make dashboard` only runs **one** offline demo at startup. To try new options (mode, keyword, max papers, preprints, etc.):

1. Keep `make dashboard` running (or start it once).
2. Open the **Pipeline Setup** tab, change the form, and click **Run Discovery Pipeline** or **Incremental Scan**.

The **Discovery Dashboard** refreshes for that run: new `run_id`, ranked outputs, synthetic cohort (regenerated from that run’s recommendations), and agent trace. Scores on `treatment_connections` are updated in place; evidence rows accumulate when you use **full** or **scan** (not replaced in demo mode).

**Leave `SUPABASE_DATABASE_URL` unset** in `.env` for the safe local laptop demo (never `build` on the team Supabase DB).

Optional flags:

```bash
python3 cli.py dashboard --fresh          # rebuild local DB
python3 cli.py dashboard --skip-pipeline  # servers only, no agent run
```

---

## Manual steps (if you prefer)

You do **not** need `SUPABASE_URL`, `SUPABASE_ANON_KEY`, or `SUPABASE_DATABASE_URL` for the dashboard.
The UI talks to the Python API only; the API uses a local SQLite file.

```bash
cd neurodiscover
pip install -r requirements.txt
python3 cli.py build
python3 api_server.py
```

In another terminal:

```bash
cd neurodiscover/frontend
python3 -m http.server 8080
```

Open **http://localhost:8080** — badge should say **Local API**.

---

## With team Supabase (optional)

- Python 3.10+
- Team Supabase project (**307 rows already live**)
- Modern browser (Chrome, Firefox, Safari)

## 1. Install Python dependencies

```bash
cd neurodiscover
cp .env.example .env
pip install -r requirements.txt
```

## 2. Configure `.env`

| Key | Used by | Purpose |
|-----|---------|---------|
| `SUPABASE_DATABASE_URL` | `cli.py`, API, orchestrator | Session pooler Postgres URI (backend writes) |
| `NEBIUS_API_KEY`, `NEBIUS_BASE_URL`, `NEBIUS_MODEL` | Literature extraction | When `EXTRACT_BACKEND=nebius` |
| `EXTRACT_BACKEND` | Literature agent | `nebius` \| `ollama` \| `none` |
| `SUPABASE_URL` | Frontend (optional) | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | Frontend (optional) | Anon / publishable key for read-only panels |

**Do not run `python3 cli.py build` on the shared Supabase database** — it truncates all tables.

## 3. Start the API (port 5000)

```bash
cd neurodiscover
python3 api_server.py
```

Or: `uvicorn api_server:app --host 0.0.0.0 --port 5000`

## 4. Open the dashboard

**Option A — file URL**

Open `neurodiscover/frontend/index.html` in your browser.

Before opening, set Supabase keys in the browser console or inject a small script tag:

```html
<script>
  window.SUPABASE_URL = 'https://YOUR_REF.supabase.co';
  window.SUPABASE_ANON_KEY = 'your-anon-key';
  window.NEURODISCOVER_API = 'http://127.0.0.1:5000';
</script>
```

**Option B — local static server (recommended for CORS)**

```bash
cd neurodiscover/frontend
python3 -m http.server 8080
```

Visit `http://localhost:8080` and configure keys via `localStorage`:

```javascript
localStorage.setItem('SUPABASE_URL', 'https://YOUR_REF.supabase.co');
localStorage.setItem('SUPABASE_ANON_KEY', 'your-anon-key');
location.reload();
```

## 5. Use the dashboard

**Local API mode (no Supabase keys):** after `cli.py build`, open the UI — tiles, subgroups, and recommendations load from the API. Run **Demo** to refresh scores and agent trace.

**Supabase mode (optional keys):** live team data loads from Supabase on page open; runs still go through `POST /api/run-discovery`.

---

## Quick verify (no Supabase keys)

```bash
cd neurodiscover
make dashboard
```

In another terminal while it is running:

```bash
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/synthetic-cohort?run_id=test
```

Open **http://127.0.0.1:8080** — Discovery Dashboard tab with synthetic cohort + ranked outputs.

---

## Quick verify (team Supabase)

Only if you have `SUPABASE_DATABASE_URL` in `.env` (Session pooler URI from the team):

```bash
cd neurodiscover
pip install -r requirements.txt
# Do NOT run cli.py build
python3 cli.py validate
python3 api_server.py
```

```bash
curl -s http://127.0.0.1:5000/health
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/recommendations
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"demo","max_papers":10}'
```

Optional frontend: set `SUPABASE_URL` + `SUPABASE_ANON_KEY` in the page or `localStorage` for direct reads; otherwise the same API routes above still work.

## Synthetic Cohort Layer

After running the pipeline, the dashboard automatically generates up to **5 synthetic patient profiles** (Patients A–E), one per discovered subgroup. Profiles are built from `recommendations` + `subgroups` — **no real patient data** is used at any point.

- Regenerated on each `POST /api/run-discovery` (included in the response as `synthetic_cohort`)
- Read-only refresh: `GET /api/synthetic-cohort?run_id=<id>`
- **Not stored in the database** — ephemeral visualization only
- UI badges **Synthetic only** and **🔒 Synthetic · no PHI** are always shown

Safe for demos, investor presentations, and regulatory discussions.

```bash
curl -s 'http://127.0.0.1:5000/api/synthetic-cohort?run_id=YOUR_RUN_ID'
```

---

## Supabase RLS (optional frontend keys only)

If you use the Supabase JS client in the browser, the anon key must allow `SELECT` on: `evidence`, `subgroups`, `subgroup_evidence`, `treatment_connections`, `recommendations`, `agent_outputs`. If policies block reads, leave keys unset — the UI uses the API routes in the table above.
