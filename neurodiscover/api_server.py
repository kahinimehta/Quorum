"""
NeuroDiscover Backend API

Person 2 backend scaffold aligned with the shared Supabase/Postgres database.

Safe behavior:
- Reads SUPABASE_DATABASE_URL from .env
- Uses SELECT queries only
- Does not run cli.py build
- Does not truncate or mutate tables

Endpoints:
- GET /health
- GET /api/discover/parkinsons
- GET /api/agents
- GET /api/recommendations
- POST /api/run-discovery
"""

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None


load_dotenv()

SUPABASE_DATABASE_URL = os.getenv("SUPABASE_DATABASE_URL")

app = FastAPI(title="NeuroDiscover API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunDiscoveryRequest(BaseModel):
    disease: str = "Parkinson's Disease"
    limit: int = 50


def get_connection():
    if not SUPABASE_DATABASE_URL:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_DATABASE_URL is not set in .env",
        )

    if psycopg is None:
        raise HTTPException(
            status_code=500,
            detail="psycopg is not installed. Make sure psycopg[binary] is in requirements.txt",
        )

    return psycopg.connect(
        SUPABASE_DATABASE_URL,
        row_factory=dict_row,
    )


def query_db(sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    params = params or tuple()

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return list(rows)

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Database query failed: {str(error)}",
        )


@app.get("/health")
def health_check():
    return {
        "status": "running",
        "message": "NeuroDiscover backend API is live",
        "database": "supabase/postgres" if SUPABASE_DATABASE_URL else "not connected",
    }


@app.get("/api/discover/parkinsons")
def discover_parkinsons():
    """
    Main dashboard payload for Parkinson's Disease.

    Reads:
    - evidence
    - subgroups
    - treatment_connections
    - recommendations
    - agent_outputs
    """

    evidence_summary = query_db(
        """
        SELECT
            source_type,
            COUNT(*) AS count
        FROM evidence
        GROUP BY source_type
        ORDER BY source_type
        """
    )

    subgroups = query_db(
        """
        SELECT *
        FROM subgroups
        LIMIT 20
        """
    )

    treatment_connections = query_db(
        """
        SELECT *,
               ROUND(
                   (
                       COALESCE(evidence_strength, 0) * 0.55
                       + COALESCE(commercial_potential, 0) * 0.45
                   )::numeric,
                   2
               ) AS confidence
        FROM treatment_connections
        ORDER BY confidence DESC
        LIMIT 20
        """
    )

    recommendations = query_db(
        """
        SELECT *
        FROM recommendations
        LIMIT 10
        """
    )

    agent_trace = query_db(
        """
        SELECT *
        FROM agent_outputs
        ORDER BY step_order ASC
        LIMIT 50
        """
    )

    return {
        "disease": "Parkinson's Disease",
        "databaseStatus": evidence_summary,
        "subgroups": subgroups,
        "treatmentConnections": treatment_connections,
        "recommendation": recommendations[0] if recommendations else None,
        "agentTrace": agent_trace,
    }


@app.get("/api/agents")
def get_agents():
    """
    Returns the agent trace for the dashboard.
    """

    agent_trace = query_db(
        """
        SELECT *
        FROM agent_outputs
        ORDER BY step_order ASC
        LIMIT 50
        """
    )

    return {
        "agents": agent_trace,
    }


@app.get("/api/recommendations")
def get_recommendations():
    """
    Returns final recommendations.
    """

    recommendations = query_db(
        """
        SELECT *
        FROM recommendations
        LIMIT 10
        """
    )

    return {
        "recommendations": recommendations,
    }


@app.post("/api/run-discovery")
def run_discovery(request: RunDiscoveryRequest):
    """
    Frontend button endpoint.

    MVP behavior:
    - Does not rebuild the database
    - Does not run live ingestion
    - Reads current Supabase-backed discovery outputs
    """

    payload = discover_parkinsons()

    return {
        "requestedDisease": request.disease,
        "status": "completed",
        **payload,
    }