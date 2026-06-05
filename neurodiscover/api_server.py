"""
NeuroDiscover Backend API (FastAPI) — see docs/developer-reference/backend-queries.md

Run: python3 api_server.py   (port 5000)

Quick verify (no Supabase keys — local SQLite):
  unset SUPABASE_DATABASE_URL
  python3 cli.py build && python3 cli.py validate
  python3 api_server.py
  curl -s http://127.0.0.1:5000/health
  curl -s http://127.0.0.1:5000/api/stats
  curl -s -X POST http://127.0.0.1:5000/api/run-discovery \\
    -H 'Content-Type: application/json' -d '{"mode":"demo","max_papers":10}'
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import backend_label, connect, is_postgres
from run_status import analyze_run_trace
from timestamps import format_ts_for_api

load_dotenv()

app = FastAPI(title="NeuroDiscover API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunDiscoveryRequest(BaseModel):
    mode: str = "demo"
    query: str | None = None
    max_papers: int = Field(default=150, ge=10, le=500)
    disease: str = "Parkinson disease"
    include_preprints: int = 0
    with_fulltext: bool = False
    extract_backend: str | None = None
    pull_grants: bool = True


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    try:
        with connect(None) as conn:
            conn.execute(sql, params)
            return conn.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}") from exc


def _order_desc(col: str) -> str:
    if is_postgres():
        return f"{col} DESC NULLS LAST"
    return f"COALESCE({col}, -1) DESC"


def _top_recommendation() -> dict[str, Any] | None:
    rows = _query(
        f"""
        SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
               tc.mechanism
        FROM recommendations r
        LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
        ORDER BY {_order_desc('r.confidence')}
        LIMIT 1
        """
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "subgroup": r["subgroup"],
        "treatment": r["treatment"],
        "confidence": r["confidence"],
        "tier": r["tier"],
        "rationale": r["rationale"],
        "mechanism": r.get("mechanism"),
    }


@app.get("/health")
def health_check():
    return {
        "status": "running",
        "message": "NeuroDiscover backend API is live",
        "database": backend_label(),
        "supabaseConfigured": bool(os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")),
    }


@app.get("/api/stats")
def get_stats():
    """Evidence counts for dashboard tiles (no Supabase JS key required)."""
    counts = {r["source_type"]: r["count"] for r in _query(
        "SELECT source_type, COUNT(*) AS count FROM evidence GROUP BY source_type"
    )}
    sg = _query("SELECT COUNT(*) AS count FROM subgroups")
    conn = _query("SELECT COUNT(*) AS count FROM treatment_connections")
    total = _query("SELECT COUNT(*) AS count FROM evidence")
    scan = _query("SELECT disease, last_scan_at, last_run_id FROM scan_state WHERE id = 1")
    scan_row = scan[0] if scan else {}
    return {
        "literature": counts.get("literature", 0),
        "trial": counts.get("trial", 0),
        "grant": counts.get("grant", 0),
        "subgroups": sg[0]["count"] if sg else 0,
        "connections": conn[0]["count"] if conn else 0,
        "totalEvidence": total[0]["count"] if total else 0,
        "lastScanAt": format_ts_for_api(scan_row.get("last_scan_at")),
        "lastRunId": scan_row.get("last_run_id"),
        "database": backend_label(),
        "supabaseConfigured": bool(os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")),
    }


@app.get("/api/evidence")
def list_evidence(offset: int = 0, limit: int = 15):
    """Paginated evidence for the results table."""
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    rows = _query(
        """
        SELECT source_type, source_id, title, year, subgroup, mechanism, treatment,
               study_type, sample_size, access_status, url
        FROM evidence
        ORDER BY evidence_id
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    total = _query("SELECT COUNT(*) AS count FROM evidence")
    return {
        "items": [
            {
                "sourceType": r["source_type"],
                "sourceId": r.get("source_id"),
                "title": r.get("title"),
                "url": r.get("url"),
                "year": r.get("year"),
                "subgroup": r.get("subgroup"),
                "mechanism": r.get("mechanism"),
                "treatment": r.get("treatment"),
                "studyType": r.get("study_type"),
                "sampleSize": r.get("sample_size"),
                "accessStatus": r.get("access_status"),
            }
            for r in rows
        ],
        "offset": offset,
        "limit": limit,
        "total": total[0]["count"] if total else 0,
    }


def _steps_for_run(run_id: str) -> list[dict[str, Any]]:
    rows = _query(
        """
        SELECT agent_name, step_order, summary, payload, created_at
        FROM agent_outputs WHERE run_id = ? ORDER BY output_id
        """,
        (run_id,),
    )
    steps = []
    for r in rows:
        payload = r.get("payload")
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        created = r.get("created_at")
        steps.append(
            {
                "agentName": r["agent_name"],
                "stepOrder": r["step_order"],
                "summary": r["summary"],
                "payload": payload,
                "createdAt": format_ts_for_api(created),
            }
        )
    return steps


@app.get("/api/run-stats")
def get_run_stats(run_id: str):
    """Per-run evidence metrics (processed vs full database totals)."""
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required")
    from orchestrator import (
        _build_run_stats,
        _evidence_counts,
        _parse_literature_step,
    )

    steps = _steps_for_run(run_id)
    if not steps:
        raise HTTPException(status_code=404, detail=f"No run found for run_id={run_id}")

    mode = "demo"
    max_papers = 150
    for step in steps:
        if step.get("agentName") != "Literature Synthesis Agent":
            continue
        summary = (step.get("summary") or "").lower()
        if "agents-only" in summary:
            mode = "agents-only"
        elif "demo" in summary:
            mode = "demo"
        elif "scan" in summary or "incremental" in summary:
            mode = "scan"
        elif "pull" in summary or "two-stage" in summary:
            mode = "full"
        payload = step.get("payload") or {}
        if isinstance(payload, dict) and payload.get("max_papers"):
            max_papers = int(payload["max_papers"])
        m = re.search(r"max_papers=(\d+)", step.get("summary") or "")
        if m:
            max_papers = int(m.group(1))
        break

    with connect(None) as conn:
        after = _evidence_counts(conn)

    lit = _parse_literature_step(steps)
    if mode in ("demo", "agents-only") and lit.get("demoUsed"):
        evidence_used = {
            "literature": lit["demoUsed"],
            "trial": 0,
            "grant": 0,
            "total": lit["demoUsed"],
        }
    else:
        pulled_total = lit["published"] + lit["preprints"] + lit["trials"]
        evidence_used = {
            "literature": lit["published"] + lit["preprints"],
            "trial": lit["trials"],
            "grant": 0,
            "total": pulled_total or lit["newStored"],
        }

    rec_rows = _query(
        "SELECT COUNT(*) AS count FROM recommendations WHERE run_id = ?",
        (run_id,),
    )
    rec_count = rec_rows[0]["count"] if rec_rows else 0

    before = dict(after)
    run_stats = _build_run_stats(mode, max_papers, before, after, steps, evidence_used)
    run_stats.update(analyze_run_trace(steps, rec_count))
    return {"runId": run_id, "runStats": run_stats}


@app.get("/api/runs")
def list_runs(limit: int = 5):
    """Recent pipeline runs from agent_outputs."""
    limit = min(max(limit, 1), 20)
    rows = _query(
        """
        SELECT ao.run_id,
               COUNT(*) AS steps,
               MIN(ao.created_at) AS started_at,
               (SELECT COUNT(*) FROM recommendations r WHERE r.run_id = ao.run_id) AS rec_count
        FROM agent_outputs ao
        WHERE ao.run_id IS NOT NULL
        GROUP BY ao.run_id
        ORDER BY MIN(ao.output_id) DESC
        LIMIT ?
        """,
        (limit,),
    )
    runs = []
    for r in rows:
        rid = r["run_id"]
        mode = "demo"
        summaries = _query(
            "SELECT summary, payload FROM agent_outputs WHERE run_id = ? AND agent_name = ? LIMIT 1",
            (rid, "Literature Synthesis Agent"),
        )
        if summaries:
            s = summaries[0].get("summary") or ""
            if "agents-only" in s.lower():
                mode = "agents-only"
            elif "scan" in s.lower() or "incremental" in s.lower():
                mode = "scan"
            elif "demo" in s.lower():
                mode = "demo"
            elif "pull" in s.lower() or "stored" in s.lower():
                mode = "full"
        steps = _steps_for_run(rid)
        from orchestrator import _evidence_counts, _parse_literature_step

        with connect(None) as conn:
            db = _evidence_counts(conn)
        lit = _parse_literature_step(steps)
        ev_note = f"+{lit.get('newStored', 0)} new"
        if mode == "agents-only" and lit.get("demoUsed"):
            ev_note = f"{lit['demoUsed']} papers (agents-only)"
        elif mode == "demo" and lit.get("demoUsed"):
            ev_note = f"{lit['demoUsed']} papers (demo)"
        elif lit.get("published"):
            ev_note = f"{lit['published']} pulled · +{lit.get('newStored', 0)} new"
        rec_count = r.get("rec_count") or 0
        meta = analyze_run_trace(steps, rec_count)
        runs.append({
            "runId": rid,
            "steps": r["steps"],
            "traceRows": r["steps"],
            "startedAt": format_ts_for_api(r.get("started_at")),
            "recommendations": rec_count,
            "syntheticProfiles": 5 if rec_count > 0 else 0,
            "mode": mode,
            "status": meta["status"],
            "statusDetail": meta["statusDetail"],
            "agentsDone": meta["agentsDone"],
            "agentsTotal": meta["agentsTotal"],
            "agentsMissing": meta["agentsMissing"],
            "evidenceNote": ev_note,
            "databaseTotal": db["total"],
        })
    return {"runs": runs}


@app.get("/api/discover/parkinsons")
def discover_parkinsons():
    subgroup_rows = _query(
        """
        SELECT s.subgroup_id, s.name, s.defining_features, s.notes,
               COUNT(DISTINCT se.evidence_id) AS evidence_count
        FROM subgroups s
        LEFT JOIN subgroup_evidence se ON se.subgroup_id = s.subgroup_id
        GROUP BY s.subgroup_id, s.name, s.defining_features, s.notes
        ORDER BY s.name
        """
    )
    subgroups = [
        {
            "subgroupId": r["subgroup_id"],
            "name": r["name"],
            "definingFeatures": r.get("defining_features"),
            "notes": r.get("notes"),
            "evidenceCount": r.get("evidence_count") or 0,
        }
        for r in subgroup_rows
    ]

    conn_rows = _query(
        f"""
        SELECT tc.connection_id, s.name AS subgroup, tc.mechanism, tc.treatment,
               tc.evidence_strength, tc.commercial_potential,
               (COALESCE(tc.evidence_strength, 0) * 0.55
                + COALESCE(tc.commercial_potential, 0) * 0.45) AS confidence
        FROM treatment_connections tc
        JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
        ORDER BY {_order_desc('confidence')}
        """
    )
    treatment_connections = [
        {
            "connectionId": r["connection_id"],
            "subgroup": r["subgroup"],
            "mechanism": r.get("mechanism"),
            "treatment": r["treatment"],
            "evidenceStrength": r.get("evidence_strength"),
            "commercialPotential": r.get("commercial_potential"),
            "confidence": round(float(r["confidence"]), 2) if r.get("confidence") is not None else None,
        }
        for r in conn_rows
    ]

    return {
        "disease": "Parkinson's Disease",
        "subgroups": subgroups,
        "treatmentConnections": treatment_connections,
        "recommendation": _top_recommendation() or {},
    }


@app.get("/api/agents")
def get_agents(run_id: str | None = None):
    if run_id:
        rows = _query(
            """
            SELECT run_id, agent_name, step_order, summary, payload, created_at
            FROM agent_outputs WHERE run_id = ? ORDER BY output_id
            """,
            (run_id,),
        )
    else:
        rows = _query(
            """
            SELECT run_id, agent_name, step_order, summary, payload, created_at
            FROM agent_outputs
            WHERE run_id = (
                SELECT run_id FROM agent_outputs ORDER BY output_id DESC LIMIT 1
            )
            ORDER BY output_id
            """
        )
    if not rows:
        return {"runId": None, "steps": []}

    resolved_run_id = rows[0]["run_id"]
    steps = []
    for r in rows:
        payload = r.get("payload")
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        created = r.get("created_at")
        steps.append(
            {
                "agentName": r["agent_name"],
                "stepOrder": r["step_order"],
                "summary": r["summary"],
                "payload": payload,
                "createdAt": format_ts_for_api(created),
            }
        )
    return {"runId": resolved_run_id, "steps": steps}


@app.get("/api/recommendations")
def get_recommendations(run_id: str | None = None):
    if run_id:
        rows = _query(
            f"""
            SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
                   tc.mechanism
            FROM recommendations r
            LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
            WHERE r.run_id = ?
            ORDER BY {_order_desc('r.confidence')}
            """,
            (run_id,),
        )
    else:
        rows = _query(
            f"""
            SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
                   tc.mechanism
            FROM recommendations r
            LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
            WHERE r.run_id = (
                SELECT run_id FROM recommendations
                ORDER BY rec_id DESC LIMIT 1
            )
            ORDER BY {_order_desc('r.confidence')}
            """
        )
    recommendations = [
        {
            "subgroup": r["subgroup"],
            "treatment": r["treatment"],
            "confidence": r["confidence"],
            "tier": r["tier"],
            "rationale": r["rationale"],
            "mechanism": r.get("mechanism"),
        }
        for r in rows
    ]
    return {"recommendations": recommendations}


@app.post("/api/run-discovery")
def run_discovery(body: RunDiscoveryRequest):
    run_id = str(uuid.uuid4())[:8]
    try:
        from orchestrator import run as run_pipeline

        result = run_pipeline(
            run_id,
            body.mode,
            query=body.query,
            max_papers=body.max_papers,
            disease=body.disease,
            include_preprints=body.include_preprints,
            with_fulltext=body.with_fulltext,
            extract_backend=body.extract_backend,
            pull_grants=body.pull_grants,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result


@app.get("/api/synthetic-cohort")
def get_synthetic_cohort(run_id: str):
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id query parameter is required")
    try:
        from synthetic_cohort import generate_synthetic_cohort

        with connect(None) as conn:
            cohort = generate_synthetic_cohort(run_id, conn)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"run_id": run_id, "synthetic_cohort": cohort}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
