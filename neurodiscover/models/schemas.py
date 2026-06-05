"""
API / DTO models for JSON responses (Person 2 backend, Person 5 dashboard).

The SQLite blackboard contract is canonical — see docs/developer-reference/database.md and
neurodiscover/schema.sql. Map API fields to DB columns in the backend layer;
do not treat these Pydantic models as the database schema.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Subgroup(BaseModel):
    """A clinically or biologically defined patient subgroup."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    criteria: dict[str, Any] = Field(default_factory=dict)
    n_subjects: int | None = Field(default=None, ge=0)


class TreatmentConnection(BaseModel):
    """A hypothesized link between a treatment and a subgroup or outcome."""

    model_config = ConfigDict(extra="forbid")

    treatment: str
    subgroup: str
    mechanism: str | None = None
    evidence_summary: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AgentTrace(BaseModel):
    """A single step recorded from an agent in the discovery pipeline."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    step: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class Critique(BaseModel):
    """Structured feedback on a hypothesis, opportunity, or agent output."""

    model_config = ConfigDict(extra="forbid")

    target_id: str
    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class RankedOpportunity(BaseModel):
    """A scored and ordered therapeutic or research opportunity."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    title: str
    description: str
    score: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None
    related_subgroups: list[str] = Field(default_factory=list)
