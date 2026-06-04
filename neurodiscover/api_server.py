"""
NeuroDiscover Backend API — contract in docs/BACKEND_QUERIES.md

Run: python3 api_server.py   (port 5000)
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import backend_label, connect, is_postgres

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
    }


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
def get_agents():
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

    run_id = rows[0]["run_id"]
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
                "createdAt": str(created) if created is not None else None,
            }
        )
    return {"runId": run_id, "steps": steps}


@app.get("/api/recommendations")
def get_recommendations():
    rows = _query(
        f"""
        SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
               tc.mechanism
        FROM recommendations r
        LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
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

    return {
        "run_id": result["run_id"],
        "recommendations": result["recommendations"],
        "steps": result["steps"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
