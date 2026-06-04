# NeuroDiscover Dashboard — Quickstart (< 5 min)

## Prerequisites

- Python 3.10+
- Team Supabase project (optional but recommended — **307 rows already live**)
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

- **Without running a pipeline:** counts, subgroups, recommendations, and evidence load from Supabase immediately.
- **Run pipeline:** click **Run Discovery Pipeline** (demo = offline) or **Incremental Scan** — calls `POST /api/run-discovery`.

## Smoke test (API only)

```bash
curl http://127.0.0.1:5000/api/recommendations
curl -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"demo","max_papers":10}'
```

## Supabase RLS

The anon key must allow `SELECT` on: `evidence`, `subgroups`, `subgroup_evidence`, `treatment_connections`, `recommendations`, `agent_outputs`. If policies block reads, the UI falls back to Flask GET routes (counts may be partial).
