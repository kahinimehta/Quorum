---
layout: default
title: Debugging
nav_order: 10
description: "Troubleshoot deploy, dashboard, API, and pipeline runs"
---

# Debugging

Common issues for **local development**, **GitHub Pages deploy**, and **live demo**.

---

## GitHub Pages (neurodiscover.github.io)

| Symptom | Fix |
|---------|-----|
| Deploy Action failed, git exit 128 | Check secret **`NEURODISCOVERY_DOCS`** in Quorum → Settings → Secrets. Classic PAT needs **`repo`** scope; authorize SSO for `neurodiscover` org. |
| Deploy green but site 404 | **neurodiscover/neurodiscover.github.io** → Settings → Pages → **Deploy from branch** → `main` / **root**. Wait 2–5 min; hard-refresh. |
| Unstyled / broken links | Confirm `docs/_config.yml` has `url: https://neurodiscover.github.io` and `baseurl: ""`. |
| Old content after push | Actions → **Deploy docs to neurodiscover.github.io** → confirm latest run on `main` succeeded. |

See [Site publishing](pages-setup) for full setup.

---

## Dashboard & API

### Dashboard won't start

```bash
cd neurodiscover
python3 --version          # must be 3.10.x – 3.12.x
pip install -r requirements.txt   # or: conda activate neurodiscover
python3 cli.py validate
python3 cli.py dashboard --no-browser
```

{: .highlight }
**Not Mac-only:** `make dashboard` works on macOS, Linux, and Windows. On Windows use `python cli.py dashboard` if `make` is missing. On headless/SSH use `--no-browser` and open the **`Open:` URL** printed by the launcher (includes `?api=`). On macOS, port 5000 may conflict with AirPlay — launcher auto-fallbacks or use `--port-api 5001 --port-ui 8081`.

| Error | Fix |
|-------|-----|
| Port 5000 or 8080 in use | Launcher auto-tries the next free port (e.g. 5001). Or stop other processes: `lsof -i :8080`. Manual override: `python3 cli.py dashboard --port-api 5001 --port-ui 8081` |
| `make: command not found` | Use `python3 cli.py dashboard` instead |
| Browser does not open | Expected on SSH/WSL — use `--no-browser` and copy the **`Open:` URL** from launcher output |
| Module not found | Run from `neurodiscover/`; Python **3.10–3.12**; `pip install -r requirements.txt` or `conda env update -f environment.yml --prune` |
| `biomcp` not found | Re-install deps; `which biomcp` should point inside your venv/conda env |
| DB errors | Local: `python3 cli.py build` (local only). Team Supabase: set `SUPABASE_DATABASE_URL`, **never** `build`. |

### API smoke test

Use the **API port** from launcher output (default 5000; may be 5001+ after auto-fallback).

```bash
curl -s http://127.0.0.1:5000/api/stats
curl -s http://127.0.0.1:5000/api/runs?limit=3
curl -s -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"demo","max_papers":10}'
```

Default POST returns `{ "run_id", "status": "running", "accepted": true }`. Poll `GET /api/run-discovery/status?run_id=YOUR_RUN_ID` until complete, or add `"wait": true` to the POST for the full payload (`recommendations`, `agent_outputs`, `runStats`).

---

## Pipeline run status

| UI status | Meaning |
|-----------|---------|
| **Complete** | All 6 agents logged for `run_id` + ≥1 recommendation — or ≥5 recommendations with partial trace (`run_status.py`) |
| **Partial** | Stopped early — check agent trace count (e.g. `3/6`) |
| **Failed** | Exception in orchestrator — see API terminal logs |

### Partial run checklist

- Literature step returned zero rows → check `max_papers`, DB has evidence  
- Missing Nebius/Ollama keys → set `EXTRACT_BACKEND=none` for metadata-only demo  
- Team DB empty locally → run `python3 cli.py build` once (local only) or set Supabase URL  

---

## Literature pull

```bash
cd neurodiscover
python3 cli.py pull --disease "your condition" --max 10 --no-pubtator
python3 cli.py scan --max 5
```

| Issue | Fix |
|-------|-----|
| BioMCP not found | Install `biomcp-python`; check `PUBMED_MCP_COMMAND` in `.env` |
| No new rows | Duplicates skipped — normal for re-pull; try new `--query` |
| Slow / timeout | Reduce `--max`; use `scan` for incremental |
| Invented ids rejected | Only BioMCP-returned ids are inserted — expected behavior |

---

## Jekyll docs (local)

```bash
cd docs
bundle install
bundle exec jekyll serve
# → http://127.0.0.1:4000
```

| Issue | Fix |
|-------|-----|
| `jekyll: command not found` | `bundle exec jekyll serve` |
| Theme errors | `bundle install` in `docs/`; Ruby 3.3+ |

---

## Logs & trace

| What | Where |
|------|--------|
| Agent trace | Dashboard Step 2, or `GET /api/agents?run_id=` |
| Stepper stuck on all Running | Hard-refresh after updating dashboard; stepper should show one **Running…** and rest **Waiting…** |
| Confidence unchanged after pull | Check literature trace for `Stored 0 new`; new rows need `subgroup`/`mechanism`/`treatment`. Rescore alone does not add rows. See [Output — when confidence changes](output#when-confidence-changes) |
| API server logs | Terminal running `api_server.py` / `make dashboard` |
| GitHub deploy | Quorum → Actions → **Deploy docs to neurodiscover.github.io** |
| DB inspect | `python3 cli.py show evidence` or `python3 cli.py query "SELECT ..."` |

---

## Safe demo checklist (stage)

- [ ] Run `make dashboard` **before** presenting (not live pull on stage)  
- [ ] Mode **demo**, max papers **10** (launcher default; API allows 10–500)  
- [ ] No `cli.py build` against team Supabase  
- [ ] Browser at the launcher **`Open:` URL** (includes `?api=`; not a stale GitHub Pages tab for live UI)  
- [ ] **Step 1** — pipeline mode + run button; global run status shows progress  
- [ ] **Step 2** — KPI strip above title (**this run** counts after pipeline); **Pipeline complete** badge, three output panels (profiles · ranked outputs match hypotheses height, scroll when longer · hypotheses); **Audit & provenance** collapsed until you expand it for agent trace
- [ ] **Step 3 — Grant Proposal** (last tab, static) — hero KPIs; **The proposal** expanded; **Grant pipeline** and **Pipeline trace & audit** collapsed; toolbar shows **x/y obligations satisfied**
- [ ] Fallback docs: [neurodiscover.github.io](https://neurodiscover.github.io) · screenshots on [Output examples](output) and [Inputs](input)  
- [ ] Mode questions: [Inputs — pipeline modes FAQ](input#recommended-workflow) (Demo vs Rescore, incremental vs full, full does not clear DB)  
