#!/usr/bin/env python3
"""
seed.py — build database from schema + seed_data.json (SQLite or Supabase Postgres).

Usage:
    python seed.py
    SUPABASE_DATABASE_URL=postgresql://... python seed.py
"""
import argparse
import json
import os

from db import connect, insert_ignore_sql, is_postgres, schema_file, truncate_all
from paths import default_db_path, seed_path


def _insert_id(conn, sql: str, params: tuple, id_column: str) -> int:
    if is_postgres():
        conn.execute(f"{sql} RETURNING {id_column}", params)
        row = conn.fetchone()
        return int(row[id_column])
    conn.execute(sql, params)
    return int(conn.lastrowid)


def build(db_path: str | None, schema_path_arg: str | None, seed_path_arg: str) -> None:
    schema = schema_path_arg or schema_file()
    with open(seed_path_arg) as f:
        data = json.load(f)

    if is_postgres():
        with connect() as conn:
            truncate_all(conn)
            _load_seed(conn, data)
            conn.commit()
            _print_counts(conn)
        from db import backend_label
        print(f"Built Supabase seed data ({backend_label()})")
        return

    if db_path and os.path.exists(db_path):
        os.remove(db_path)

    with connect(db_path) as conn:
        with open(schema) as f:
            conn.executescript(f.read())
        _load_seed(conn, data)
        conn.commit()
        _print_counts(conn)
    print(f"Built {db_path or default_db_path()}")


def _load_seed(conn, data: dict) -> None:
    subgroup_id = {}
    for s in data["subgroups"]:
        sid = _insert_id(
            conn,
            "INSERT INTO subgroups (name, defining_features, notes) VALUES (?,?,?)",
            (s["name"], s.get("defining_features"), s.get("notes")),
            "subgroup_id",
        )
        subgroup_id[s["name"]] = sid

    evidence_id = {}
    for e in data["evidence"]:
        eid = _insert_id(
            conn,
            """INSERT INTO evidence
               (source_type, source_id, title, year, venue, subgroup, mechanism,
                treatment, key_result, study_type, sample_size, evidence_snippet, url,
                doi, access_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (e["source_type"], e["source_id"], e.get("title"), e.get("year"),
             e.get("venue"), e.get("subgroup"), e.get("mechanism"), e.get("treatment"),
             e.get("key_result"), e.get("study_type"), e.get("sample_size"),
             e.get("evidence_snippet"), e.get("url"), e.get("doi"),
             e.get("access_status")),
            "evidence_id",
        )
        evidence_id[e["source_id"]] = eid
        sg = e.get("subgroup")
        if sg in subgroup_id:
            conn.execute(
                insert_ignore_sql(
                    "subgroup_evidence", ["subgroup_id", "evidence_id"], ["subgroup_id", "evidence_id"]
                ),
                (subgroup_id[sg], eid),
            )

    for c in data["treatment_connections"]:
        cid = _insert_id(
            conn,
            "INSERT INTO treatment_connections (subgroup_id, mechanism, treatment) VALUES (?,?,?)",
            (subgroup_id[c["subgroup_name"]], c.get("mechanism"), c["treatment"]),
            "connection_id",
        )
        for sid in c.get("supporting_source_ids", []):
            if sid in evidence_id:
                conn.execute(
                    insert_ignore_sql(
                        "connection_evidence",
                        ["connection_id", "evidence_id"],
                        ["connection_id", "evidence_id"],
                    ),
                    (cid, evidence_id[sid]),
                )


def _print_counts(conn) -> None:
    for tbl in ["subgroups", "evidence", "treatment_connections",
                "connection_evidence", "subgroup_evidence"]:
        conn.execute(f"SELECT COUNT(*) AS n FROM {tbl}")
        n = conn.fetchone()["n"]
        print(f"  {tbl:<22} {n} rows")


def init_schema() -> None:
    """Apply schema.pg.sql to empty Supabase project (first-time setup)."""
    if not is_postgres():
        raise SystemExit("init_schema requires SUPABASE_DATABASE_URL")
    with open(schema_file()) as f:
        script = f.read()
    with connect() as conn:
        conn.executescript(script)
        conn.commit()
    print("Applied schema.pg.sql to Supabase")


if __name__ == "__main__":

    p = argparse.ArgumentParser()
    p.add_argument("--db", default=default_db_path())
    p.add_argument("--schema", default=None)
    p.add_argument("--seed", default=seed_path())
    p.add_argument("--init-schema", action="store_true", help="apply schema.pg.sql only (Supabase)")
    a = p.parse_args()
    if a.init_schema:
        init_schema()
    else:
        build(a.db, a.schema, a.seed)
