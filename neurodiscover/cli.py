#!/usr/bin/env python3
"""
cli.py — NeuroDiscover data layer command line.

SQLite (local): unset SUPABASE_DATABASE_URL
Supabase (team): set SUPABASE_DATABASE_URL=postgresql://...

Commands:
    python cli.py build
    python cli.py init-supabase    # first-time: apply schema.pg.sql
    python cli.py demo | pull | scan | pull-grants | validate | show | query
    python cli.py spot-check | validate-extraction | validate-pubtator
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
from agents.literature_agent import run as run_agent  # noqa: E402
from ingestion.grants_pull import run as run_grants  # noqa: E402
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
    run_agent(
        DB if not is_postgres() else None, a.disease, a.since, a.max,
        demo=False, incremental=False, query=a.query, gene=a.gene,
        validate_pull=not a.no_validate,
        strict_pull=a.strict_pull,
        pubtator_sample=0 if a.no_pubtator else a.pubtator_sample,
        with_fulltext=a.with_fulltext,
        include_preprints=a.preprints,
    )


def cmd_enrich_fulltext(a):
    from agents.literature_agent import enrich_with_fulltext

    enrich_with_fulltext(DB if not is_postgres() else None, limit=a.limit)


def cmd_pull_grants(a):
    import requests
    from ingestion.grants_pull import DEFAULT_QUERY
    q = a.query or DEFAULT_QUERY
    try:
        run_grants(DB if not is_postgres() else None, q, a.limit)
    except requests.RequestException as exc:
        print(f"[error] RePORTER request failed: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_scan(a):
    run_agent(
        DB if not is_postgres() else None, a.disease, a.since, a.max,
        demo=False, incremental=True, query=a.query, gene=a.gene,
        validate_pull=not a.no_validate,
        strict_pull=False,
        pubtator_sample=0,
    )


def cmd_validate_extraction(a):
    from validation.consistency import batch_validate

    with connect(DB if not is_postgres() else None) as conn:
        conn.execute(
            "SELECT source_type, source_id, title, mechanism, treatment, key_result, "
            "study_type, sample_size, evidence_snippet FROM evidence"
        )
        rows = conn.fetchall()
    result = batch_validate([dict(r) for r in rows])
    print(f"Evidence rows: {result['total']}")
    print(f"Passed consistency: {result['passed']} ({result['pass_rate']:.0%})")
    print(f"Failed: {result['failed']}")
    for fail in result["failed_rows"][:10]:
        print(f"  {fail['source_id']}: {fail['issues']}")
    if result["pass_rate"] < 0.7:
        sys.exit(1)


def cmd_validate_pubtator(a):
    from validation.pubtator import batch_pubtator_verify

    with connect(DB if not is_postgres() else None) as conn:
        conn.execute(
            "SELECT source_type, source_id, title, mechanism, treatment, key_result, "
            "study_type, sample_size, subgroup FROM evidence WHERE source_type = 'literature'"
        )
        rows = [dict(r) for r in conn.fetchall()]
    out = batch_pubtator_verify(rows, sample_size=a.sample)
    print(f"Sampled: {out['sampled']}")
    print(f"Average overlap: {out['average_overlap']:.2f} ({out['confidence']})")
    print(f"genes={out['genes_avg']:.2f} diseases={out['diseases_avg']:.2f} chemicals={out['chemicals_avg']:.2f}")


def cmd_spot_check(a):
    from validation.spot_check import export_spot_check, score_spot_check
    from pathlib import Path

    out = Path(a.output)
    if a.score:
        score_spot_check(out)
        return
    export_spot_check(
        DB if not is_postgres() else None,
        count=a.count,
        mode=a.sample,
        output=out,
    )


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
        sp.add_argument("--max", type=int, default=150)

    d = sub.add_parser("demo", help="run literature agent offline")
    add_run_args(d)
    d.set_defaults(fn=cmd_demo)

    pl = sub.add_parser("pull", help="two-stage pull: PubMed (+ optional bioRxiv) + trials")
    add_run_args(pl)
    pl.add_argument("--no-validate", action="store_true", help="skip extraction QA after pull")
    pl.add_argument("--strict-pull", action="store_true",
                    help="do not insert rows that fail consistency checks")
    pl.add_argument("--pubtator-sample", type=int, default=50,
                    help="PubTator grounding sample size (0=skip)")
    pl.add_argument("--no-pubtator", action="store_true", help="skip PubTator grounding")
    pl.add_argument(
        "--with-fulltext",
        action="store_true",
        help="download OA Methods/Results/Discussion (PMC → EPMC → Unpaywall)",
    )
    pl.add_argument(
        "--include-preprints", "--preprints",
        type=int, default=0, dest="preprints", metavar="N",
        help="stage 2: also pull up to N bioRxiv preprints (title-deduped vs published)",
    )
    pl.set_defaults(fn=cmd_pull)

    ef = sub.add_parser(
        "enrich-with-fulltext",
        help="backfill section excerpts on existing literature rows",
    )
    ef.add_argument("--limit", type=int, default=50)
    ef.set_defaults(fn=cmd_enrich_fulltext)

    sc = sub.add_parser("scan", help="incremental scan (low-cost)")
    add_run_args(sc)
    sc.add_argument("--no-validate", action="store_true", help="skip extraction QA")
    sc.set_defaults(fn=cmd_scan)

    pg = sub.add_parser("pull-grants", help="pull NIH grants into evidence")
    pg.add_argument("--query", default=None,
                    help="RePORTER advanced_text_search (default: PD-focused)")
    pg.add_argument("--limit", type=int, default=30)
    pg.set_defaults(fn=cmd_pull_grants)

    sub.add_parser("validate", help="FK and schema sanity checks").set_defaults(fn=cmd_validate)

    ve = sub.add_parser("validate-extraction", help="consistency checks on all evidence rows")
    ve.set_defaults(fn=cmd_validate_extraction)

    vp = sub.add_parser("validate-pubtator", help="PubTator3 entity overlap on literature PMIDs")
    vp.add_argument("--sample", type=int, default=50)
    vp.set_defaults(fn=cmd_validate_pubtator)

    sp = sub.add_parser("spot-check", help="sample papers for manual extraction QA")
    sp.add_argument("--count", type=int, default=15)
    sp.add_argument("--sample", choices=("random", "low-confidence"), default="random")
    sp.add_argument("--output", default="spot_check_results.csv")
    sp.add_argument("--score", action="store_true", help="score filled CSV")
    sp.set_defaults(fn=cmd_spot_check)

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
