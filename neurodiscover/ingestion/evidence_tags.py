"""Keyword inference + backfill so agents 2–6 can score more than LLM-tagged rows."""
from __future__ import annotations

from db import insert_ignore_sql


def infer_tags_from_text(text: str) -> dict[str, str | None]:
    """Map title/abstract text to canonical subgroup, mechanism, treatment."""
    t = (text or "").lower()
    subgroup = mechanism = treatment = None

    if any(k in t for k in ("gba", "gcase", "glucocerebrosidase", "ambroxol")):
        subgroup = "GBA-mutation PD"
        mechanism = "lysosomal dysfunction"
        if any(k in t for k in ("ambroxol", "chaperone", "gcase", "activation")):
            treatment = "GCase activation"
    if "lrrk2" in t:
        subgroup = subgroup or "LRRK2 PD"
        mechanism = mechanism or "LRRK2 kinase pathway"
        treatment = treatment or "LRRK2 inhibition"
    if "alpha-synuclein" in t or "synuclein" in t:
        subgroup = subgroup or "Alpha-synuclein-high PD"
        mechanism = mechanism or "alpha-synuclein aggregation"
        treatment = treatment or "clearance therapy"
    if "inflammation" in t or "inflammatory" in t or "microglia" in t:
        subgroup = subgroup or "Inflammation-high PD"
        mechanism = mechanism or "neuroinflammation"
        if "microglia" in t:
            treatment = treatment or "microglial modulation"
    if ("progress" in t and "motor" in t) or "rapid progress" in t:
        subgroup = subgroup or "Rapid motor progressors"
        mechanism = mechanism or "neuroprotection"
        treatment = treatment or "combination strategy"

    return {"subgroup": subgroup, "mechanism": mechanism, "treatment": treatment}


def _row_text(row: dict) -> str:
    return " ".join(
        filter(
            None,
            [
                row.get("title") or "",
                row.get("abstract") or "",
                row.get("key_result") or "",
                row.get("evidence_snippet") or "",
            ],
        )
    )


def _link_subgroup_evidence(conn, evidence_id: int, subgroup_name: str) -> None:
    conn.execute("SELECT subgroup_id FROM subgroups WHERE name = ?", (subgroup_name,))
    sg_row = conn.fetchone()
    if not sg_row:
        return
    conn.execute(
        insert_ignore_sql(
            "subgroup_evidence",
            ["subgroup_id", "evidence_id"],
            ["subgroup_id", "evidence_id"],
        ),
        (sg_row["subgroup_id"], evidence_id),
    )


def backfill_evidence_tags(conn) -> int:
    """
    Fill missing subgroup/mechanism/treatment from title text and ensure
    subgroup_evidence links exist for scored rows.
    """
    conn.execute(
        "SELECT evidence_id, title, abstract, key_result, evidence_snippet, "
        "subgroup, mechanism, treatment FROM evidence"
    )
    updated = 0
    for row in conn.fetchall():
        inferred = infer_tags_from_text(_row_text(row))
        subgroup = row.get("subgroup") or inferred.get("subgroup")
        mechanism = row.get("mechanism") or inferred.get("mechanism")
        treatment = row.get("treatment") or inferred.get("treatment")
        if not subgroup:
            continue
        if (
            subgroup == row.get("subgroup")
            and mechanism == row.get("mechanism")
            and treatment == row.get("treatment")
        ):
            _link_subgroup_evidence(conn, row["evidence_id"], subgroup)
            continue
        conn.execute(
            "UPDATE evidence SET subgroup = ?, mechanism = ?, treatment = ? "
            "WHERE evidence_id = ?",
            (subgroup, mechanism, treatment, row["evidence_id"]),
        )
        _link_subgroup_evidence(conn, row["evidence_id"], subgroup)
        updated += 1
    return updated
