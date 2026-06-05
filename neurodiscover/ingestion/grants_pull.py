#!/usr/bin/env python3
"""Pull NIH RePORTER grants into the evidence table (source_type=grant)."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone

import requests

from ingestion.evidence_tags import infer_tags_from_text as _infer_from_grant_text

AGENT_NAME = "Literature Synthesis Agent"
REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"

DEFAULT_QUERY = (
    "(Parkinson OR Parkinsons) AND (GBA OR GCase OR lysosomal OR LRRK2 OR alpha-synuclein)"
)
DEFAULT_FISCAL_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def search_grants(
    text_query: str = DEFAULT_QUERY,
    fiscal_years: list[int] | None = None,
    limit: int = 30,
) -> list[dict]:
    # RePORTER v2 expects {"criteria": {...}}; the old {"query": {...}} form now
    # returns HTTP 500. Use the "advanced" operator so boolean text_query works,
    # and fall back to a plain term match if the advanced form is rejected.
    fys = fiscal_years or DEFAULT_FISCAL_YEARS
    forms = [
        {"criteria": {"advanced_text_search": {"operator": "advanced",
            "search_field": "all", "search_text": text_query},
            "fiscal_years": fys}, "limit": limit, "offset": 0},
        {"criteria": {"advanced_text_search": {"operator": "and",
            "search_field": "all", "search_text": "Parkinson disease"},
            "fiscal_years": fys}, "limit": limit, "offset": 0},
    ]
    resp = None
    for payload in forms:
        resp = requests.post(REPORTER_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json().get("results", [])[:limit]
    resp.raise_for_status()
    return []


def grant_to_finding(project: dict) -> dict | None:
    source_id = project.get("core_project_num")
    if not source_id:
        return None
    project_id = project.get("project_id")
    url = (
        f"https://reporter.nih.gov/project-details/{project_id}"
        if project_id
        else None
    )
    amount = project.get("award_amount") or 0
    text = " ".join(
        filter(
            None,
            [
                project.get("project_title") or "",
                (project.get("abstract_text") or "")[:800],
            ],
        )
    )
    inferred = _infer_from_grant_text(text)
    return {
        "source_type": "grant",
        "source_id": source_id,
        "title": (project.get("project_title") or "")[:500],
        "year": project.get("fiscal_year"),
        "venue": "NIH",
        "subgroup": inferred["subgroup"],
        "mechanism": inferred["mechanism"],
        "treatment": inferred["treatment"],
        "key_result": f"NIH grant awarded ${amount:,}",
        "study_type": None,
        "sample_size": None,
        "evidence_snippet": None,
        "url": url,
        "doi": None,
        "access_status": "open",
    }


def upsert_grant(conn, finding: dict) -> bool:
    from db import is_postgres

    cols = (
        "source_type", "source_id", "title", "year", "venue", "subgroup",
        "mechanism", "treatment", "key_result", "study_type", "sample_size",
        "evidence_snippet", "url", "doi", "access_status",
    )
    qs = ", ".join("?" for _ in cols)
    vals = tuple(finding.get(k) for k in cols) + (_now_iso(),)
    if is_postgres():
        conn.execute(
            f"INSERT INTO evidence ({', '.join(cols)}, last_scanned_at) "
            f"VALUES ({qs}, ?) ON CONFLICT (source_type, source_id) DO NOTHING "
            f"RETURNING evidence_id",
            vals,
        )
        return conn.fetchone() is not None
    conn.execute(
        f"INSERT OR IGNORE INTO evidence ({', '.join(cols)}, last_scanned_at) "
        f"VALUES ({qs}, ?)",
        vals,
    )
    return conn.rowcount > 0


def log_trace(conn, run_id: str, step: int, summary: str, payload: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO agent_outputs (run_id, agent_name, step_order, summary, payload) "
        "VALUES (?,?,?,?,?)",
        (run_id, AGENT_NAME, step, summary, json.dumps(payload) if payload else None),
    )


def backfill_grant_fields(conn) -> int:
    """Fill subgroup/mechanism/treatment on existing grant rows from title text."""
    conn.execute(
        "SELECT evidence_id, title FROM evidence "
        "WHERE source_type = 'grant' AND subgroup IS NULL"
    )
    updated = 0
    for row in conn.fetchall():
        inferred = _infer_from_grant_text(row.get("title") or "")
        if not inferred.get("subgroup"):
            continue
        conn.execute(
            "UPDATE evidence SET subgroup = ?, mechanism = ?, treatment = ? "
            "WHERE evidence_id = ?",
            (
                inferred["subgroup"],
                inferred["mechanism"],
                inferred["treatment"],
                row["evidence_id"],
            ),
        )
        updated += 1
    return updated


def run(db_path, text_query: str, limit: int, *, run_id: str | None = None) -> None:
    from db import backend_label, connect

    pipeline_run_id = run_id or str(uuid.uuid4())[:8]
    projects = search_grants(text_query, limit=limit)
    new = 0
    with connect(db_path) as conn:
        for project in projects:
            finding = grant_to_finding(project)
            if finding and upsert_grant(conn, finding):
                new += 1
        backfilled = backfill_grant_fields(conn)
        log_trace(
            conn, pipeline_run_id, 4,
            f"Pulled {len(projects)} grants from NIH RePORTER; stored {new} new rows.",
            {"query": text_query, "limit": limit, "new_grants": new, "grants_backfilled": backfilled},
        )
        conn.commit()
    print(f"[pull-grants] {backend_label()} — stored {new} new of {len(projects)}. run_id={pipeline_run_id}")


def main() -> None:
    from paths import default_db_path

    p = argparse.ArgumentParser(description="Pull NIH grants into evidence")
    p.add_argument("--db", default=default_db_path())
    p.add_argument("--query", default=DEFAULT_QUERY, help="RePORTER advanced_text_search")
    p.add_argument("--limit", type=int, default=30)
    a = p.parse_args()
    try:
        run(a.db, a.query, a.limit)
    except requests.RequestException as exc:
        print(f"[error] RePORTER request failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
