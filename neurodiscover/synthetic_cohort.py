"""
Ephemeral synthetic patient profiles for demo visualization (Synthea-style).

Not stored in the database. Regenerated from recommendations + subgroups on each call.
No real patient data, no PHI.
"""
from __future__ import annotations

import random
import string
from typing import Any

# Subgroup accent colors (dashboard UI)
SUBGROUP_COLORS: dict[str, str] = {
    "GBA-mutation PD": "#2563eb",
    "LRRK2 PD": "#0d9488",
    "Alpha-synuclein-high PD": "#7c3aed",
    "Inflammation-high PD": "#dc2626",
    "Rapid motor progressors": "#d97706",
}

DEFAULT_COLOR = "#64748b"


def _key_feature(defining_features: str | None) -> str:
    if not defining_features:
        return "Parkinson disease subgroup profile"
    clause = defining_features.split(";")[0].strip()
    return clause or defining_features[:120]


def _stable_rng(run_id: str, subgroup: str) -> random.Random:
    seed = hash((run_id, subgroup)) % (2**32)
    return random.Random(seed)


def _patient_letter(index: int) -> str:
    return f"Patient {string.ascii_uppercase[index]}"


def _fetch_ranked_for_run(conn, run_id: str) -> list[dict[str, Any]]:
    conn.execute(
        """
        SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
               tc.mechanism, s.defining_features
        FROM recommendations r
        JOIN subgroups s ON s.name = r.subgroup
        LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
        WHERE r.run_id = ?
        ORDER BY r.confidence DESC
        """,
        (run_id,),
    )
    rows = conn.fetchall()
    if rows:
        return rows

    conn.execute(
        """
        SELECT r.subgroup, r.treatment, r.confidence, r.tier, r.rationale,
               tc.mechanism, s.defining_features
        FROM recommendations r
        JOIN subgroups s ON s.name = r.subgroup
        LEFT JOIN treatment_connections tc ON tc.connection_id = r.connection_id
        ORDER BY r.confidence DESC
        """
    )
    return conn.fetchall()


def _fallback_for_subgroup(conn, subgroup_name: str) -> dict[str, Any] | None:
    conn.execute(
        "SELECT defining_features FROM subgroups WHERE name = ?",
        (subgroup_name,),
    )
    sg = conn.fetchone()
    conn.execute(
        """
        SELECT tc.treatment, tc.mechanism,
               (COALESCE(tc.evidence_strength, 0) * 0.55
                + COALESCE(tc.commercial_potential, 0) * 0.45) AS confidence
        FROM treatment_connections tc
        JOIN subgroups s ON s.subgroup_id = tc.subgroup_id
        WHERE s.name = ?
        ORDER BY confidence DESC
        LIMIT 1
        """,
        (subgroup_name,),
    )
    tc = conn.fetchone()
    if not tc:
        return None
    return {
        "subgroup": subgroup_name,
        "treatment": tc["treatment"],
        "confidence": round(float(tc["confidence"]), 1) if tc.get("confidence") is not None else None,
        "tier": None,
        "rationale": None,
        "mechanism": tc.get("mechanism"),
        "defining_features": sg.get("defining_features") if sg else None,
    }


def generate_synthetic_cohort(run_id: str, db_conn) -> list[dict[str, Any]]:
    """
    Build one synthetic patient profile per discovered subgroup (max 5, A–E).
    Ordered by confidence descending.
    """
    ranked = _fetch_ranked_for_run(db_conn, run_id)
    by_subgroup: dict[str, dict[str, Any]] = {}
    for row in ranked:
        name = row.get("subgroup")
        if name and name not in by_subgroup:
            by_subgroup[name] = dict(row)

    db_conn.execute("SELECT name FROM subgroups ORDER BY name")
    for sg_row in db_conn.fetchall():
        name = sg_row["name"]
        if name not in by_subgroup:
            fb = _fallback_for_subgroup(db_conn, name)
            if fb:
                by_subgroup[name] = fb

    ordered = sorted(
        by_subgroup.values(),
        key=lambda r: float(r.get("confidence") or 0),
        reverse=True,
    )[:5]

    cohort: list[dict[str, Any]] = []
    for idx, row in enumerate(ordered):
        subgroup = row["subgroup"]
        rng = _stable_rng(run_id, subgroup)
        age = rng.randint(55, 75)
        sex = "M" if idx % 2 == 0 else "F"
        features = _key_feature(row.get("defining_features"))
        course = (
            f"Modeled {subgroup} trajectory — illustrative progression only, "
            "not a real clinical record."
        )
        letter = _patient_letter(idx)
        cohort.append(
            {
                "patient_id": letter,
                "patient_letter": string.ascii_uppercase[idx],
                "subgroup": subgroup,
                "subgroup_color": SUBGROUP_COLORS.get(subgroup, DEFAULT_COLOR),
                "synthetic_age": age,
                "synthetic_sex": sex,
                "key_feature": features,
                "course": course,
                "top_opportunity": row.get("treatment"),
                "mechanism": row.get("mechanism"),
                "confidence": row.get("confidence"),
                "tier": row.get("tier"),
                "is_synthetic": True,
                "phi_free": True,
            }
        )
    return cohort
