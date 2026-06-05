"""Pipeline mode labels and detection from agent_outputs traces."""
from __future__ import annotations

import json
import re
from typing import Any

MODE_LABELS: dict[str, str] = {
    "agents-only": "Rescore DB",
    "demo": "Demo sample",
    "scan": "Incremental scan",
    "full": "Full live pull",
}

LITERATURE_AGENT = "Literature Synthesis Agent"


def normalize_mode(mode: str | None) -> str:
    if not mode:
        return "demo"
    m = mode.lower().replace("_", "-")
    if m in MODE_LABELS:
        return m
    if m == "pull":
        return "full"
    return m


def mode_label(mode: str | None) -> str:
    return MODE_LABELS.get(normalize_mode(mode), mode or "Unknown")


def _parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def detect_pipeline_mode(
    steps: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
) -> str:
    """Resolve canonical mode: settings > literature payload > summary heuristics."""
    if settings and settings.get("mode"):
        return normalize_mode(str(settings["mode"]))

    resolved: str | None = None
    for step in steps:
        name = (step.get("agentName") or step.get("agent_name") or "").strip()
        if LITERATURE_AGENT not in name:
            continue
        payload = _parse_payload(step.get("payload"))
        if payload.get("pipeline_mode"):
            resolved = normalize_mode(str(payload["pipeline_mode"]))
        summary = (step.get("summary") or "").lower()
        if "agents-only" in summary:
            return "agents-only"
        if "demo mode" in summary:
            return "demo"
        if "incremental scan" in summary:
            resolved = "scan"
        elif "full live pull" in summary:
            resolved = "full"
        elif payload.get("incremental") is True:
            resolved = "scan"
        elif payload.get("incremental") is False and "starting" in summary:
            resolved = "full"
    return resolved or "demo"


def literature_stats_from_steps(steps: list[dict[str, Any]]) -> dict[str, int]:
    """Aggregate pull/store counts from literature agent trace rows."""
    out = {
        "published": 0,
        "preprints": 0,
        "trials": 0,
        "newStored": 0,
        "skipped": 0,
        "demoUsed": 0,
        "demoDbTotal": 0,
    }
    for step in steps:
        name = step.get("agentName") or step.get("agent_name") or ""
        if LITERATURE_AGENT not in name:
            continue
        summary = step.get("summary") or ""
        payload = _parse_payload(step.get("payload"))
        m = re.search(
            r"Two-stage pull: (\d+) published, (\d+) preprints?, (\d+) trials",
            summary,
        )
        if m:
            out["published"] = int(m.group(1))
            out["preprints"] = int(m.group(2))
            out["trials"] = int(m.group(3))
        m = re.search(r"Stored (\d+) new evidence", summary)
        if m:
            out["newStored"] = int(m.group(1))
        m = re.search(r"Incremental scan complete: stored (\d+) new", summary)
        if m:
            out["newStored"] = int(m.group(1))
        m = re.search(r"Full live pull complete: stored (\d+) new", summary)
        if m:
            out["newStored"] = int(m.group(1))
        m = re.search(r"(\d+) existing skipped", summary)
        if m:
            out["skipped"] = int(m.group(1))
        m = re.search(r"using (\d+) of (\d+) seeded", summary)
        if m:
            out["demoUsed"] = int(m.group(1))
            out["demoDbTotal"] = int(m.group(2))
        m = re.search(r"Agents-only: using (\d+) of (\d+)", summary)
        if m:
            out["demoUsed"] = int(m.group(1))
            out["demoDbTotal"] = int(m.group(2))
        if payload.get("new_evidence") is not None:
            out["newStored"] = int(payload["new_evidence"])
        if payload.get("skipped_duplicates") is not None:
            out["skipped"] = int(payload["skipped_duplicates"])
        if payload.get("skipped") is not None:
            out["skipped"] = int(payload["skipped"])
    return out


def format_evidence_note(mode: str, lit: dict[str, int]) -> str:
    """Human-readable evidence column for Recent runs."""
    mode = normalize_mode(mode)
    new = lit.get("newStored", 0)
    skipped = lit.get("skipped", 0)
    published = lit.get("published", 0)
    trials = lit.get("trials", 0)

    if mode == "agents-only" and lit.get("demoUsed"):
        return f"{lit['demoUsed']} rows rescored (no pull)"
    if mode == "demo" and lit.get("demoUsed"):
        return f"{lit['demoUsed']} papers (demo sample)"
    if mode == "scan":
        parts = [f"+{new} new"]
        if skipped:
            parts.append(f"{skipped} skipped")
        parts.append("incremental")
        if published:
            parts.insert(0, f"{published} searched")
        return " · ".join(parts)
    if mode == "full":
        parts = []
        if published:
            parts.append(f"{published} papers")
        if trials:
            parts.append(f"{trials} trials")
        parts.append(f"+{new} stored")
        if skipped:
            parts.append(f"{skipped} skipped")
        return " · ".join(parts) if parts else f"+{new} stored"
    if new:
        return f"+{new} stored"
    if published or trials:
        bits = []
        if published:
            bits.append(f"{published} papers")
        if trials:
            bits.append(f"{trials} trials")
        return " · ".join(bits)
    return "—"
