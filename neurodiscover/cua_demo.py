"""Load pre-rendered CUA demo artifacts for the dashboard Grant Proposal tab."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_RUN_ID = "graded6"


def outputs_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "cua" / "outputs"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def demo_available(run_id: str = DEFAULT_RUN_ID) -> bool:
    base = outputs_dir()
    return (base / f"{run_id}.proposal.json").is_file() and (base / f"{run_id}.html").is_file()


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def load_demo_summary(run_id: str = DEFAULT_RUN_ID) -> dict[str, Any]:
    base = outputs_dir()
    if not demo_available(run_id):
        return {
            "available": False,
            "run_id": run_id,
            "outputs_dir": str(base),
        }

    proposal = _read_json(base / f"{run_id}.proposal.json") or {}
    audit = _read_json(base / f"{run_id}.audit.json") or {}
    ingestion = _read_json(base / f"{run_id}.ingestion.json") or {}

    grounding = audit.get("grounding_report") or {}
    ledger = audit.get("obligation_ledger") or []
    calibration = audit.get("calibration") or {}
    internal = calibration.get("internal_scores") or {}

    aims = []
    for aim in proposal.get("aims") or []:
        aims.append(
            {
                "id": aim.get("id"),
                "hypothesis": _truncate(aim.get("hypothesis") or "", 320),
                "citation_count": len(aim.get("citation_ids") or []),
            }
        )

    sections = []
    for sec in proposal.get("sections") or []:
        sections.append(
            {
                "name": sec.get("name"),
                "dimension": sec.get("serves_dimension"),
                "preview": _truncate(sec.get("text") or "", 360),
            }
        )

    satisfied = sum(1 for o in ledger if o.get("status") == "satisfied")
    at_risk = sum(1 for o in ledger if o.get("status") == "at_risk")

    return {
        "available": True,
        "static_demo": True,
        "pipeline_linked": False,
        "demo_id": run_id,
        "run_id": run_id,
        "version": "v1.1",
        "project_title": proposal.get("project_title"),
        "central_hypothesis": proposal.get("central_hypothesis"),
        "sections": sections,
        "aims": aims,
        "ingestion": {
            "corpus_n": ingestion.get("corpus_n"),
            "top_k": ingestion.get("top_k"),
            "ranking_method": ingestion.get("ranking_method"),
        },
        "audit": {
            "citations": grounding.get("n_references"),
            "all_in_corpus": grounding.get("all_in_source_set"),
            "obligations_satisfied": satisfied,
            "obligations_at_risk": at_risk,
            "scores": internal,
        },
        "report_path": f"/cua-demo/{run_id}.html",
    }
