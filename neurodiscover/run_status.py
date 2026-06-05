"""Interpret agent_outputs traces for dashboard run status (display only)."""
from __future__ import annotations

import re
from typing import Any

PIPELINE_AGENTS = [
    "Literature Synthesis Agent",
    "Patient Subgroup Agent",
    "Treatment Connection Agent",
    "Evidence Scoring Agent",
    "Commercial Discovery Agent",
    "Conclusion Update Agent",
]

AGENT_LITERATURE = PIPELINE_AGENTS[0]

_LITERATURE_COMPLETE = re.compile(
    r"Incremental scan complete|Full live pull complete|Demo mode:|Agents-only:",
    re.IGNORECASE,
)


def _short_agent(name: str) -> str:
    return name.replace(" Agent", "").strip()


def literature_complete(steps: list[dict[str, Any]]) -> bool:
    """Literature counts as done only after its final summary (not mid-pull progress rows)."""
    for step in steps:
        name = (step.get("agentName") or step.get("agent_name") or "").strip()
        if name != AGENT_LITERATURE:
            continue
        if _LITERATURE_COMPLETE.search(step.get("summary") or ""):
            return True
    return False


def completed_agent_names(steps: list[dict[str, Any]]) -> set[str]:
    names = {
        (s.get("agentName") or s.get("agent_name") or "").strip()
        for s in steps
        if s.get("agentName") or s.get("agent_name")
    }
    if AGENT_LITERATURE in names and not literature_complete(steps):
        names.discard(AGENT_LITERATURE)
    return names


def analyze_run_trace(
    steps: list[dict[str, Any]],
    rec_count: int = 0,
) -> dict[str, Any]:
    """
    Complete = all 6 agents logged for this run_id and ≥1 recommendation.
    Partial = fewer than 6 agents and/or no recommendations (stopped early or old trace).
    """
    names = completed_agent_names(steps)
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
