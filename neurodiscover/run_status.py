"""Interpret agent_outputs traces for dashboard run status (display only)."""
from __future__ import annotations

from typing import Any

PIPELINE_AGENTS = [
    "Literature Synthesis Agent",
    "Patient Subgroup Agent",
    "Treatment Connection Agent",
    "Evidence Scoring Agent",
    "Commercial Discovery Agent",
    "Conclusion Update Agent",
]


def _short_agent(name: str) -> str:
    return name.replace(" Agent", "").strip()


def analyze_run_trace(
    steps: list[dict[str, Any]],
    rec_count: int = 0,
) -> dict[str, Any]:
    """
    Complete = all 6 agents logged for this run_id and ≥1 recommendation.
    Partial = fewer than 6 agents and/or no recommendations (stopped early or old trace).
    """
    names = {
        (s.get("agentName") or s.get("agent_name") or "").strip()
        for s in steps
        if s.get("agentName") or s.get("agent_name")
    }
    done = [a for a in PIPELINE_AGENTS if a in names]
    missing = [_short_agent(a) for a in PIPELINE_AGENTS if a not in names]
    n_done = len(done)

    if n_done >= 6 and rec_count >= 1:
        status = "Complete"
        detail = f"All 6 agents finished · {rec_count} recommendation(s)"
    elif n_done >= 6:
        status = "Complete"
        detail = f"All 6 agents finished · {rec_count} recommendations"
    elif rec_count >= 5:
        status = "Complete"
        detail = (
            f"{n_done}/6 agents in trace · {rec_count} recommendations "
            "(scores written; trace may be from an earlier step)"
        )
    else:
        status = "Partial"
        detail = f"Only {n_done}/6 agents ran for this run"
        if missing:
            detail += f" — missing: {', '.join(missing)}"
        if rec_count == 0:
            detail += " · no recommendations saved"
        else:
            detail += f" · {rec_count} recommendation(s)"

    return {
        "status": status,
        "statusDetail": detail,
        "agentsDone": n_done,
        "agentsTotal": len(PIPELINE_AGENTS),
        "agentsMissing": missing,
    }
