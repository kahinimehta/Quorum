#!/usr/bin/env bash
# Capture dashboard screenshots for docs/assets/images/dashboard/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ND="$ROOT/neurodiscover"
OUT="$ROOT/docs/assets/images/dashboard"
mkdir -p "$OUT"
export PYTHONPATH="$ND"

API_PID=""
UI_PID=""
cleanup() {
  [[ -n "$API_PID" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "$UI_PID" ]] && kill "$UI_PID" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ND"
if [[ ! -f neurodiscover.db ]] && [[ -z "${SUPABASE_DATABASE_URL:-}" ]]; then
  python3 cli.py build --max 0 2>/dev/null || python3 seed.py 2>/dev/null || true
fi

python3 -m uvicorn api_server:app --host 127.0.0.1 --port 5000 >/tmp/nd-api.log 2>&1 &
API_PID=$!
cd "$ND/frontend"
python3 -m http.server 8080 >/tmp/nd-ui.log 2>&1 &
UI_PID=$!
sleep 2

echo "Seeding agents-only run for screenshots…"
curl -sf -m 60 -X POST http://127.0.0.1:5000/api/run-discovery \
  -H 'Content-Type: application/json' \
  -d '{"mode":"agents-only","max_papers":0,"run_id":"docshot"}' >/tmp/nd-run.json || true

CHROME="${CHROME:-google-chrome}"
CHROME_PROFILE="${CHROME_PROFILE:-/tmp/nd-chrome-profile-$$}"
shot() {
  local file="$1" url="$2" wait="${3:-3}"
  sleep "$wait"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --user-data-dir="$CHROME_PROFILE" \
    --window-size=1440,1200 \
    --screenshot="$file" "$url" 2>/dev/null || \
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
    --user-data-dir="$CHROME_PROFILE" \
    --window-size=1440,1200 \
    --screenshot="$file" "$url"
  echo "Wrote $file"
}

shot "$OUT/step1-configure-run.png" "http://127.0.0.1:8080/index.html" 4

# Step 2 — append hash or click via JS not available; page boots to results if recs exist
shot "$OUT/step2-discovery-results.png" "http://127.0.0.1:8080/index.html" 3

# Scroll regions approximated via tall window; optional element crops omitted
shot "$OUT/step2-ranked-treatments.png" "http://127.0.0.1:8080/index.html" 2
shot "$OUT/step2-synthetic-cohort.png" "http://127.0.0.1:8080/index.html" 2
shot "$OUT/step2-audit-evidence.png" "http://127.0.0.1:8080/index.html" 2

echo "Done. For Step 3 (CUA tab) + element crops, use: cd neurodiscover && python3 scripts/capture_dashboard_screenshots.py"
