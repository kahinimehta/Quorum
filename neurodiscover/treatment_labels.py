"""Human-readable labels and explanations for canonical treatment slugs."""
from __future__ import annotations

TREATMENT_META: dict[str, dict[str, str]] = {
    "combination strategy": {
        "label": "Combination neuroprotection",
        "hint": (
            "Multi-agent stack for fast motor progression — combine symptomatic and "
            "disease-modifying neuroprotective approaches while single-agent proof matures."
        ),
        "summary": (
            "Rapid motor progressors show faster UPDRS decline than typical PD. "
            "Literature proposes combining neuroprotective agents rather than betting on "
            "one monotherapy, but combo regimens remain unproven in this subgroup."
        ),
    },
}


def treatment_label(treatment: str | None) -> str:
    if not treatment:
        return "—"
    meta = TREATMENT_META.get(treatment)
    return meta["label"] if meta else treatment


def treatment_hint(treatment: str | None) -> str:
    if not treatment:
        return ""
    meta = TREATMENT_META.get(treatment)
    return meta.get("hint", "") if meta else ""


def recommendation_rationale(
    *,
    subgroup: str,
    treatment: str,
    mechanism: str | None,
    confidence: float,
    tier: str,
) -> str:
    """Build dashboard-facing rationale text for a ranked connection."""
    label = treatment_label(treatment)
    mech = mechanism or "mechanism TBD"
    meta = TREATMENT_META.get(treatment)
    if meta:
        return (
            f"{subgroup} → {label} via {mech}. {meta['summary']} "
            f"Confidence {confidence} ({tier})."
        )
    return (
        f"{subgroup} → {treatment} via {mech}. Confidence {confidence} ({tier})."
    )
