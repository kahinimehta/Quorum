#!/usr/bin/env python3
"""Post-run sanity checks for neurodiscover.db or Supabase."""
import sys

from db import connect, is_postgres


def validate(db_path: str | None = None) -> list[str]:
    errors = []
    with connect(db_path) as conn:
        if is_postgres():
            conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            tables = {r["table_name"] for r in conn.fetchall()}
        else:
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r["name"] for r in conn.fetchall()}

        required = {
            "evidence", "subgroups", "treatment_connections",
            "connection_evidence", "subgroup_evidence",
            "agent_outputs", "recommendations", "scan_state",
        }
        missing = required - tables
        if missing:
            errors.append(f"Missing tables: {sorted(missing)}")

        conn.execute("""
            SELECT COUNT(*) AS n FROM connection_evidence ce
            LEFT JOIN evidence e ON e.evidence_id = ce.evidence_id
            WHERE e.evidence_id IS NULL
        """)
        orphans = conn.fetchone()["n"]
        if orphans:
            errors.append(f"connection_evidence has {orphans} orphan evidence_id(s)")

        conn.execute("""
            SELECT COUNT(*) AS n FROM subgroup_evidence se
            LEFT JOIN evidence e ON e.evidence_id = se.evidence_id
            WHERE e.evidence_id IS NULL
        """)
        orphans = conn.fetchone()["n"]
        if orphans:
            errors.append(f"subgroup_evidence has {orphans} orphan evidence_id(s)")

        conn.execute("SELECT COUNT(*) AS n FROM scan_state")
        n_scan = conn.fetchone()["n"]
        if n_scan != 1:
            errors.append(f"scan_state should have exactly 1 row, found {n_scan}")

    return errors


def main():
    import argparse
    from paths import default_db_path

    p = argparse.ArgumentParser()
    p.add_argument("--db", default=default_db_path())
    a = p.parse_args()
    errs = validate(a.db if not is_postgres() else None)
    if errs:
        for e in errs:
            print(f"FAIL: {e}", file=sys.stderr)
        sys.exit(1)
    from db import backend_label
    print(f"OK: {backend_label()} passed validation")


if __name__ == "__main__":
    main()
