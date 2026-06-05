#!/usr/bin/env python3
"""
One-command local dashboard launcher.

Used by: python3 cli.py dashboard  |  make dashboard  |  ./dashboard
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import uuid
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(HERE, "frontend")


def _popen(cmd: list[str], **kwargs) -> subprocess.Popen:
    return subprocess.Popen(
        cmd,
        cwd=kwargs.get("cwd", HERE),
        stdout=kwargs.get("stdout", sys.stdout),
        stderr=kwargs.get("stderr", sys.stderr),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start NeuroDiscover dashboard (API + UI)")
    parser.add_argument("--port-api", type=int, default=5000, help="FastAPI port")
    parser.add_argument("--port-ui", type=int, default=8080, help="Static frontend port")
    parser.add_argument("--skip-install", action="store_true", help="Skip pip install -r requirements.txt")
    parser.add_argument("--skip-build", action="store_true", help="Skip local sqlite build")
    parser.add_argument("--skip-pipeline", action="store_true", help="Do not run demo pipeline before serving")
    parser.add_argument("--fresh", action="store_true", help="Rebuild local neurodiscover.db")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the dashboard URL in your default browser",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, HERE)
    from dotenv import load_dotenv

    load_dotenv(os.path.join(HERE, ".env"))

    from db import is_postgres
    from paths import default_db_path

    py = sys.executable
    procs: list[subprocess.Popen] = []

    def shutdown(*_):
        print("\n[dashboard] Stopping…")
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(0.3)
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if not args.skip_install:
        print("[dashboard] Installing dependencies…")
        subprocess.run([py, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=HERE, check=False)

    if is_postgres():
        print("[dashboard] SUPABASE_DATABASE_URL is set — skipping build (never build on team DB).")
    elif not args.skip_build:
        db_path = default_db_path()
        if args.fresh and os.path.isfile(db_path):
            os.remove(db_path)
        if args.fresh or not os.path.isfile(db_path):
            print("[dashboard] Building local demo database…")
            subprocess.run([py, "cli.py", "build"], cwd=HERE, check=True)
        subprocess.run([py, "cli.py", "validate"], cwd=HERE, check=True)

    if not args.skip_pipeline:
        from orchestrator import run as run_pipeline

        run_id = str(uuid.uuid4())[:8]
        if is_postgres():
            print("[dashboard] Running agents 2–6 on team Supabase evidence (no literature pull)…")
            result = run_pipeline(run_id, "agents-only", max_papers=0)
        else:
            print("[dashboard] Running offline demo pipeline…")
            result = run_pipeline(run_id, "demo", max_papers=10)
        print(
            f"[dashboard] Pipeline done — run_id={result['run_id']}, "
            f"recommendations={len(result.get('recommendations', []))}, "
            f"synthetic={len(result.get('synthetic_cohort', []))}"
        )

    print(f"[dashboard] Starting API on http://127.0.0.1:{args.port_api}")
    api = _popen([py, "api_server.py"], cwd=HERE)
    procs.append(api)
    time.sleep(1.2)

    print(f"[dashboard] Starting UI on http://127.0.0.1:{args.port_ui}")
    ui = _popen(
        [py, "-m", "http.server", str(args.port_ui), "--bind", "127.0.0.1"],
        cwd=FRONTEND,
    )
    procs.append(ui)

    ui_url = f"http://127.0.0.1:{args.port_ui}/"
    print()
    print("  NeuroDiscover dashboard is running")
    print(f"  Open:  {ui_url}")
    print(f"  API:   http://127.0.0.1:{args.port_api}")
    print("  Press Ctrl+C to stop")
    print()

    if not args.no_browser:
        time.sleep(0.4)
        print("[dashboard] Opening in your default browser…")
        opened = webbrowser.open(ui_url, new=2)
        if not opened:
            print("[dashboard] Could not launch a browser — open the URL above manually.")

    try:
        while True:
            if api.poll() is not None:
                print("[dashboard] API process exited.", file=sys.stderr)
                return 1
            if ui.poll() is not None:
                print("[dashboard] UI process exited.", file=sys.stderr)
                return 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
