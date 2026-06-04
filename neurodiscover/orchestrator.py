"""
Pipeline orchestrator — wires agents 1→6 against the shared DB blackboard.

Modes:
  demo / scan — literature via cli.py subprocess, then agents 2–6 in-process
  full        — literature_agent.run (live pull) + optional grants, then agents 2–6

Agent 1 generates its own run_id; agents 2–6 use scan_state.last_run_id after step 1.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

from db import connect, insert_ignore_sql, is_postgres
from timestamps import format_ts_for_api

AGENT_LITERATURE = "Literature Synthesis Agent"
AGENT_SUBGROUP = "Patient Subgroup Agent"
AGENT_TREATMENT = "Treatment Connection Agent"
AGENT_EVIDENCE = "Evidence Scoring Agent"
AGENT_COMMERCIAL = "Commercial Discovery Agent"
AGENT_CONCLUSION = "Conclusion Update Agent"

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "cli.py")


def _scale_score(value: float | int | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 10.0, 1)


def _tier(confidence: float) -> str:
    if confidence >= 80:
        return "Prioritize"
    if confidence >= 65:
        return "Monitor"
    return "Reject"


def _confidence(es: float | None, cp: float | None) -> float | None:
    if es is None or cp is None:
        return None
    return round(es * 0.55 + cp * 0.45, 1)


def log_step(
    conn,
    run_id: str,
    agent_name: str,
    step_order: int,
    summary: str,
    payload: dict | None = None,
) -> None:
    conn.execute(
        "INSERT INTO agent_outputs (run_id, agent_name, step_order, summary, payload) "
        "VALUES (?,?,?,?,?)",
        (run_id, agent_name, step_order, summary, json.dumps(payload) if payload else None),
    )


def _get_canonical_run_id(conn, fallback: str) -> str:
    conn.execute("SELECT last_run_id FROM scan_state WHERE id = 1")
    row = conn.fetchone()
    if row and row.get("last_run_id"):
        return str(row["last_run_id"])
    conn.execute(
        "SELECT run_id FROM agent_outputs WHERE agent_name = ? "
        "ORDER BY output_id DESC LIMIT 1",
        (AGENT_LITERATURE,),
    )
    row = conn.fetchone()
    if row and row.get("run_id"):
        return str(row["run_id"])
    return fallback


def _evidence_counts(conn) -> dict[str, int]:
    conn.execute("SELECT source_type, COUNT(*) AS count FROM evidence GROUP BY source_type")
    counts = {r["source_type"]: int(r["count"]) for r in conn.fetchall()}
    literature = counts.get("literature", 0)
    trial = counts.get("trial", 0)
    grant = counts.get("grant", 0)
    return {
        "literature": literature,
        "trial": trial,
        "grant": grant,
        "total": literature + trial + grant,
    }


def _fetch_evidence_rows(conn, max_papers: int | None = None) -> list[dict[str, Any]]:
    conn.execute(
        "SELECT evidence_id, source_type, source_id, title, subgroup, mechanism, treatment, "
        "key_result, study_type, sample_size, access_status "
        "FROM evidence WHERE subgroup IS NOT NULL ORDER BY evidence_id"
    )
    rows = conn.fetchall()
    if not max_papers or max_papers <= 0:
        return rows
    filtered: list[dict[str, Any]] = []
    lit_seen = 0
    for row in rows:
        if row.get("source_type") == "literature":
            if lit_seen >= max_papers:
                continue
            lit_seen += 1
        filtered.append(row)
    return filtered


def _count_rows_by_type(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"literature": 0, "trial": 0, "grant": 0, "total": len(rows)}
    for row in rows:
        st = row.get("source_type")
        if st in counts:
            counts[st] += 1
    return counts


def _parse_literature_step(steps: list[dict[str, Any]]) -> dict[str, int]:
    out = {
        "published": 0,
        "preprints": 0,
        "trials": 0,
        "newStored": 0,
        "demoDbTotal": 0,
    }
    for step in steps:
        name = step.get("agentName") or ""
        if AGENT_LITERATURE not in name:
            continue
        summary = step.get("summary") or ""
        payload = step.get("payload") or {}
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
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
        m = re.search(r"using (\d+) of (\d+) seeded", summary)
        if m:
            out["demoUsed"] = int(m.group(1))
            out["demoDbTotal"] = int(m.group(2))
        elif "Demo" in summary:
            m = re.search(r"(\d+)", summary)
            if m:
                out["demoDbTotal"] = int(m.group(1))
        if isinstance(payload, dict) and payload.get("new_evidence") is not None:
            out["newStored"] = int(payload["new_evidence"])
    return out


def _build_run_stats(
    mode: str,
    max_papers: int,
    before: dict[str, int],
    after: dict[str, int],
    steps: list[dict[str, Any]],
    evidence_used: dict[str, int],
) -> dict[str, Any]:
    lit = _parse_literature_step(steps)
    delta = {
        "literature": after["literature"] - before["literature"],
        "trial": after["trial"] - before["trial"],
        "grant": after["grant"] - before["grant"],
        "total": after["total"] - before["total"],
    }
    pulled_lit = lit["published"] + lit["preprints"]
    if mode == "demo":
        processed_lit = lit.get("demoUsed") or evidence_used["literature"]
    else:
        cap = max_papers if max_papers > 0 else pulled_lit
        processed_lit = min(cap, pulled_lit) if pulled_lit else delta["literature"]
    return {
        "mode": mode,
        "maxPapersRequested": max_papers,
        "databaseTotals": after,
        "databaseBefore": before,
        "delta": delta,
        "pulled": {
            "literature": pulled_lit,
            "preprints": lit["preprints"],
            "trials": lit["trials"],
        },
        "added": {
            "literature": delta["literature"],
            "trial": delta["trial"],
            "grant": delta["grant"],
            "total": delta["total"],
            "stored": lit["newStored"],
        },
        "processed": {
            "literature": processed_lit,
            "trial": lit["trials"] if lit["trials"] else evidence_used["trial"],
            "grant": evidence_used["grant"],
            "total": evidence_used["total"],
        },
        "evidenceUsed": evidence_used,
    }


def _subprocess_cli(
    mode: str,
    *,
    disease: str,
    query: str | None,
    max_papers: int,
    include_preprints: int,
    with_fulltext: bool,
    extract_backend: str | None,
) -> None:
    cmd = [sys.executable, CLI, mode, "--disease", disease, "--max", str(max_papers)]
    if query:
        cmd.extend(["--query", query])
    if mode == "pull" or mode == "full":
        pass
    if include_preprints and mode in ("pull", "full"):
        cmd.extend(["--include-preprints", str(include_preprints)])
    if with_fulltext and mode in ("pull", "full"):
        cmd.append("--with-fulltext")

    env = os.environ.copy()
    if extract_backend:
        env["EXTRACT_BACKEND"] = extract_backend

    result = subprocess.run(
        cmd,
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "cli failed").strip()
        raise RuntimeError(f"cli.py {mode} failed: {err}")


def _persist_subgroups(conn, output: dict[str, Any], run_id: str) -> None:
    for sg in output.get("subgroups", []):
        name = sg.get("name")
        if not name:
            continue
        rationale = sg.get("rationale", "")
        conn.execute(
            "SELECT subgroup_id FROM subgroups WHERE name = ?",
            (name,),
        )
        existing = conn.fetchone()
        if existing:
            conn.execute(
                "UPDATE subgroups SET defining_features = COALESCE(defining_features, ?) "
                "WHERE subgroup_id = ?",
                (rationale[:500] if rationale else None, existing["subgroup_id"]),
            )
        else:
            conn.execute(
                "INSERT INTO subgroups (name, defining_features, notes) VALUES (?,?,?)",
                (name, rationale[:500] if rationale else None, "Discovered by pipeline"),
            )

    log_step(
        conn,
        run_id,
        AGENT_SUBGROUP,
        2,
        output.get("summary", "Patient subgroups updated."),
        {"count": len(output.get("subgroups", []))},
    )


def _connection_id(
    conn,
    subgroup_name: str,
    mechanism: str | None,
    treatment: str,
) -> int | None:
    conn.execute(
        "SELECT tc.connection_id FROM treatment_connections tc "
        "JOIN subgroups s ON s.subgroup_id = tc.subgroup_id "
        "WHERE s.name = ? AND tc.treatment = ?",
        (subgroup_name, treatment),
    )
    row = conn.fetchone()
    if row:
        return int(row["connection_id"])

    conn.execute("SELECT subgroup_id FROM subgroups WHERE name = ?", (subgroup_name,))
    sg = conn.fetchone()
    if not sg:
        return None

    if is_postgres():
        conn.execute(
            "INSERT INTO treatment_connections (subgroup_id, mechanism, treatment) "
            "VALUES (?,?,?) ON CONFLICT (subgroup_id, treatment) DO UPDATE "
            "SET mechanism = EXCLUDED.mechanism RETURNING connection_id",
            (sg["subgroup_id"], mechanism, treatment),
        )
    else:
        conn.execute(
            "INSERT INTO treatment_connections (subgroup_id, mechanism, treatment) "
            "VALUES (?,?,?) ON CONFLICT(subgroup_id, treatment) DO UPDATE SET mechanism = ?",
            (sg["subgroup_id"], mechanism, treatment, mechanism),
        )
        conn.execute(
            "SELECT connection_id FROM treatment_connections "
            "WHERE subgroup_id = ? AND treatment = ?",
            (sg["subgroup_id"], treatment),
        )
    row = conn.fetchone()
    return int(row["connection_id"]) if row else None


def _persist_treatment_connections(conn, output: dict[str, Any], run_id: str) -> None:
    linked = 0
    for conn_row in output.get("connections", []):
        subgroup = conn_row.get("subgroup")
        mechanism = conn_row.get("mechanism")
        treatment = conn_row.get("treatment_strategy") or conn_row.get("treatment")
        if not subgroup or not treatment:
            continue
        cid = _connection_id(conn, subgroup, mechanism, treatment)
        if not cid:
            continue
        for source_id in conn_row.get("evidence_sources", []):
            conn.execute(
                "SELECT evidence_id FROM evidence WHERE source_id = ?",
                (source_id,),
            )
            ev = conn.fetchone()
            if ev:
                conn.execute(
                    insert_ignore_sql(
                        "connection_evidence",
                        ["connection_id", "evidence_id"],
                        ["connection_id", "evidence_id"],
                    ),
                    (cid, ev["evidence_id"]),
                )
                linked += 1

    log_step(
        conn,
        run_id,
        AGENT_TREATMENT,
        3,
        output.get("summary", "Treatment connections updated."),
        {"connections": len(output.get("connections", [])), "links": linked},
    )


def _persist_evidence_scores(conn, output: dict[str, Any], run_id: str) -> None:
    updated = 0
    for scored in output.get("scored_connections", []):
        subgroup = scored.get("subgroup")
        treatment = scored.get("treatment_strategy") or scored.get("treatment")
        mechanism = scored.get("mechanism")
        if not subgroup or not treatment:
            continue
        cid = _connection_id(conn, subgroup, mechanism, treatment)
        if not cid:
            continue
        strength = _scale_score(scored.get("evidence_strength"))
        if strength is not None:
            conn.execute(
                "UPDATE treatment_connections SET evidence_strength = ? WHERE connection_id = ?",
                (strength, cid),
            )
            updated += 1

    log_step(
        conn,
        run_id,
        AGENT_EVIDENCE,
        4,
        output.get("summary", "Evidence strength scores updated."),
        {"updated": updated},
    )


def _persist_commercial_scores(conn, output: dict[str, Any], run_id: str) -> None:
    updated = 0
    for opp in output.get("opportunities", []):
        subgroup = opp.get("subgroup")
        treatment = opp.get("treatment_strategy") or opp.get("treatment")
        mechanism = opp.get("mechanism")
        if not subgroup or not treatment:
            continue
        cid = _connection_id(conn, subgroup, mechanism, treatment)
        if not cid:
            continue
        commercial = _scale_score(opp.get("commercial_potential"))
        if commercial is not None:
            conn.execute(
                "UPDATE treatment_connections SET commercial_potential = ? WHERE connection_id = ?",
                (commercial, cid),
            )
            updated += 1

    log_step(
        conn,
        run_id,
        AGENT_COMMERCIAL,
        5,
        output.get("summary", "Commercial potential scores updated."),
        {"updated": updated},
    )


def _persist_recommendations(conn, run_id: str) -> list[dict[str, Any]]:
    conn.execute(
        "SELECT tc.connection_id, s.name AS subgroup, tc.mechanism, tc.treatment, "
        "tc.evidence_strength, tc.commercial_potential "
        "FROM treatment_connections tc "
        "JOIN subgroups s ON s.subgroup_id = tc.subgroup_id "
        "WHERE tc.evidence_strength IS NOT NULL AND tc.commercial_potential IS NOT NULL"
    )
    rows = conn.fetchall()
    recs: list[dict[str, Any]] = []

    for row in rows:
        conf = _confidence(row["evidence_strength"], row["commercial_potential"])
        if conf is None:
            continue
        tier = _tier(conf)
        rationale = (
            f"{row['subgroup']} → {row['treatment']} via {row['mechanism'] or 'mechanism TBD'}. "
            f"Confidence {conf} ({tier})."
        )
        conn.execute(
            "INSERT INTO recommendations "
            "(run_id, connection_id, subgroup, treatment, confidence, tier, rationale) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                row["connection_id"],
                row["subgroup"],
                row["treatment"],
                conf,
                tier,
                rationale,
            ),
        )
        recs.append(
            {
                "subgroup": row["subgroup"],
                "treatment": row["treatment"],
                "mechanism": row["mechanism"],
                "confidence": conf,
                "tier": tier,
                "rationale": rationale,
            }
        )

    recs.sort(key=lambda r: r["confidence"], reverse=True)
    log_step(
        conn,
        run_id,
        AGENT_CONCLUSION,
        6,
        f"Wrote {len(recs)} recommendations for run {run_id}.",
        {"count": len(recs)},
    )
    return recs


def _run_agents_2_through_6(
    conn, run_id: str, *, max_papers: int | None = None
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    from agents.commercial_discovery_agent import CommercialDiscoveryAgent
    from agents.evidence_scoring_agent import EvidenceScoringAgent
    from agents.patient_subgroup_agent import PatientSubgroupAgent
    from agents.treatment_connection_agent import TreatmentConnectionAgent

    evidence_rows = _fetch_evidence_rows(conn, max_papers=max_papers)
    evidence_used = _count_rows_by_type(evidence_rows)

    sg_agent = PatientSubgroupAgent()
    sg_out = sg_agent.run(evidence_rows)
    _persist_subgroups(conn, sg_out, run_id)

    tc_agent = TreatmentConnectionAgent()
    tc_out = tc_agent.run(sg_out, evidence_rows)
    _persist_treatment_connections(conn, tc_out, run_id)

    es_agent = EvidenceScoringAgent()
    es_out = es_agent.run(tc_out, evidence_rows)
    _persist_evidence_scores(conn, es_out, run_id)

    cd_agent = CommercialDiscoveryAgent()
    cd_out = cd_agent.run(es_out)
    _persist_commercial_scores(conn, cd_out, run_id)

    recs = _persist_recommendations(conn, run_id)
    return recs, evidence_used


def _run_literature_full(
    *,
    disease: str,
    query: str | None,
    max_papers: int,
    include_preprints: int,
    with_fulltext: bool,
    pull_grants: bool,
    extract_backend: str | None,
) -> None:
    if extract_backend:
        os.environ["EXTRACT_BACKEND"] = extract_backend

    from agents.literature_agent import run as run_literature

    run_literature(
        None,
        disease,
        2020,
        max_papers,
        demo=False,
        incremental=False,
        query=query,
        include_preprints=include_preprints or 0,
        with_fulltext=with_fulltext,
    )

    if pull_grants:
        from ingestion.grants_pull import run as run_grants

        run_grants(None, None, 30)


def _fetch_steps(conn, run_id: str) -> list[dict[str, Any]]:
    conn.execute(
        "SELECT agent_name, step_order, summary, payload, created_at "
        "FROM agent_outputs WHERE run_id = ? ORDER BY output_id",
        (run_id,),
    )
    steps = []
    for row in conn.fetchall():
        payload = row.get("payload")
        if isinstance(payload, str) and payload:
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        created = row.get("created_at")
        steps.append(
            {
                "agentName": row["agent_name"],
                "stepOrder": row["step_order"],
                "summary": row["summary"],
                "payload": payload,
                "createdAt": format_ts_for_api(created),
            }
        )
    return steps


def run(
    run_id: str,
    mode: str,
    *,
    query: str | None = None,
    max_papers: int = 150,
    disease: str = "Parkinson disease",
    include_preprints: int = 0,
    with_fulltext: bool = False,
    extract_backend: str | None = None,
    pull_grants: bool = True,
) -> dict[str, Any]:
    """
    Execute the discovery pipeline. Returns run_id, recommendations, agent_outputs, synthetic_cohort.
    """
    mode = (mode or "demo").lower()
    if mode not in ("demo", "scan", "full"):
        raise ValueError(f"Unknown mode: {mode}")

    with connect(None) as conn:
        before = _evidence_counts(conn)

    if mode in ("demo", "scan"):
        _subprocess_cli(
            mode,
            disease=disease,
            query=query,
            max_papers=max_papers,
            include_preprints=include_preprints if mode == "full" else 0,
            with_fulltext=with_fulltext,
            extract_backend=extract_backend,
        )
    elif mode == "full":
        _run_literature_full(
            disease=disease,
            query=query,
            max_papers=max_papers,
            include_preprints=include_preprints,
            with_fulltext=with_fulltext,
            pull_grants=pull_grants,
            extract_backend=extract_backend,
        )

    with connect(None) as conn:
        after = _evidence_counts(conn)
        canonical_run_id = _get_canonical_run_id(conn, run_id)

        agent_max = max_papers if mode == "demo" else None
        recommendations, evidence_used = _run_agents_2_through_6(
            conn, canonical_run_id, max_papers=agent_max
        )
        conn.commit()

        steps = _fetch_steps(conn, canonical_run_id)
        run_stats = _build_run_stats(
            mode, max_papers, before, after, steps, evidence_used
        )

        from synthetic_cohort import generate_synthetic_cohort

        synthetic_cohort = generate_synthetic_cohort(canonical_run_id, conn)

    return {
        "run_id": canonical_run_id,
        "recommendations": recommendations,
        "agent_outputs": steps,
        "steps": steps,
        "synthetic_cohort": synthetic_cohort,
        "runStats": run_stats,
    }
