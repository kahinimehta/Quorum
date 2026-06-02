#!/usr/bin/env python3
"""
cli.py — NeuroDiscover data layer command line.

SQLite (local): unset SUPABASE_DATABASE_URL
Supabase (team): set SUPABASE_DATABASE_URL=postgresql://...

Commands:
    python cli.py build
    python cli.py init-supabase    # first-time: apply schema.pg.sql
    python cli.py demo | pull | scan | pull-grants | validate | show | query
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(HERE, ".env"))
except Exception:  # noqa: BLE001
    pass

from db import backend_label, connect, is_postgres, schema_file  # noqa: E402
from paths import default_db_path, seed_path  # noqa: E402
from seed import build as build_db, init_schema  # noqa: E402
from literature_agent import run as run_agent  # noqa: E402
from grants_pull import run as run_grants  # noqa: E402
from db_validate import validate  # noqa: E402

DB = default_db_path()
SCHEMA = schema_file()
SEED = seed_path()


def cmd_build(a):
    build_db(DB if not is_postgres() else None, SCHEMA, SEED)


def cmd_init_supabase(a):
    init_schema()
    print("Next: python3 cli.py build   # load seed into Supabase")


def cmd_demo(a):
    run_agent(DB if not is_postgres() else None, a.disease, a.since, a.max,
              demo=True, incremental=False, query=a.query, gene=a.gene)


def cmd_pull(a):
    run_agent(DB if not is_postgres() else None, a.disease, a.since, a.max,
              demo=False, incremental=False, query=a.query, gene=a.gene)


def cmd_pull_grants(a):
    import requests
    from grants_pull import DEFAULT_QUERY
    q = a.query or DEFAULT_QUERY
    try:
        run_grants(DB if not is_postgres() else None, q, a.limit)
    except requests.RequestException as exc:
        print(f"[error] RePORTER request failed: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_scan(a):
    run_agent(DB if not is_postgres() else None, a.disease, a.since, a.max,
              demo=False, incremental=True, query=a.query, gene=a.gene)


def cmd_validate(a):
    errs = validate(DB if not is_postgres() else None)
    if errs:
        for e in errs:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {backend_label()} passed validation")


def cmd_show(a):
    with connect(DB if not is_postgres() else None) as conn:
        if is_postgres():
            conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY 1"
            )
            tables = [r["table_name"] for r in conn.fetchall()]
        else:
            conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r["name"] for r in conn.fetchall()]
        if not a.table:
            for name in tables:
                conn.execute(f"SELECT COUNT(*) AS n FROM {name}")
                n = conn.fetchone()["n"]
                print(f"{name:<24} {n} rows")
            return
        conn.execute(f"SELECT * FROM {a.table} LIMIT {a.limit}")
        for r in conn.fetchall():
            print(r)


def cmd_query(a):
    with connect(DB if not is_postgres() else None) as conn:
        sql = a.sql.replace("?", "%s") if is_postgres() else a.sql
        for r in conn.execute(sql).fetchall():
            print(r)


def main():
    p = argparse.ArgumentParser(prog="cli.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("build", help="rebuild DB from schema + seed").set_defaults(fn=cmd_build)
    sub.add_parser("init-supabase", help="apply schema.pg.sql to empty Supabase project").set_defaults(
        fn=cmd_init_supabase
    )

    def add_run_args(sp):
        sp.add_argument("--disease", default="Parkinson disease")
        sp.add_argument("--query", default=None,
                        help="refine BioMCP search (mechanism, phenotype, treatment)")
        sp.add_argument("--prompt", default=None, dest="query", help="alias for --query")
        sp.add_argument("--gene", default=None, help="optional gene filter for article search")
        sp.add_argument("--since", type=int, default=2020)
        sp.add_argument("--max", type=int, default=10)

    d = sub.add_parser("demo", help="run literature agent offline")
    add_run_args(d)
    d.set_defaults(fn=cmd_demo)

    pl = sub.add_parser("pull", help="pull real evidence via BioMCP + Nebius")
    add_run_args(pl)
    pl.set_defaults(fn=cmd_pull)

    sc = sub.add_parser("scan", help="incremental scan (low-cost)")
    add_run_args(sc)
    sc.set_defaults(fn=cmd_scan)

    pg = sub.add_parser("pull-grants", help="pull NIH grants into evidence")
    pg.add_argument("--query", default=None,
                    help="RePORTER advanced_text_search (default: PD-focused)")
    pg.add_argument("--limit", type=int, default=30)
    pg.set_defaults(fn=cmd_pull_grants)

    sub.add_parser("validate", help="FK and schema sanity checks").set_defaults(fn=cmd_validate)

    sh = sub.add_parser("show", help="inspect tables")
    sh.add_argument("table", nargs="?", default=None)
    sh.add_argument("--limit", type=int, default=20)
    sh.set_defaults(fn=cmd_show)

    q = sub.add_parser("query", help="run a read SQL query")
    q.add_argument("sql")
    q.set_defaults(fn=cmd_query)

    a = p.parse_args()
    if is_postgres():
        print(f"[db] {backend_label()}", file=sys.stderr)
    a.fn(a)


if __name__ == "__main__":
    main()
