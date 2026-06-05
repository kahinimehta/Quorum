"""test_local_runner.py — LOCAL-RUNNER: the local SQLite grades snapshot from the agents2 logic.

`build/live/LOCAL-RUNNER_relay.md` + `build/decisions/2026-06-03-local-grades-snapshot.md`: a standalone
runner pulls the shared evidence READ-ONLY, drives the vendored agents2 logic (subgroup → connection →
scoring) in memory, RESCALES evidence_strength ×10 ([0,10] → [0,100], the silent-bug fix), and writes a
LOCAL SQLite snapshot CUA consumes via the UNCHANGED adapter. These tests run against a tiny fixture
(no prod DB, no credential): the 4 adapter tables populate, evidence_strength lands in [0,100], the
snapshot opens READ-ONLY, CUA's adapter reads it, and the only shared-DB code path (psycopg) is lazy.

Owner: LOCAL-RUNNER (builder). Offline + deterministic; no network, no shared-DB access.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_INTEG = _ROOT / "build" / "integration"
if str(_INTEG) not in sys.path:  # the runner lives outside src/cua; put it on the path for this test
    sys.path.insert(0, str(_INTEG))

import build_local_grades as blg
from build_local_grades import EVIDENCE_COLS, GRADE_SCALE, build_local_grades


# === fixtures (tiny evidence sets shaped like the neurodiscover `evidence` table) ================


def _ev(eid, st, sid, *, subgroup=None, mechanism=None, treatment=None, study_type="cohort", n=40):
    return {
        "evidence_id": eid, "source_type": st, "source_id": sid,
        "title": f"{sid} title", "year": 2024, "publication_year": 2024, "venue": "Jrnl",
        "subgroup": subgroup, "mechanism": mechanism, "treatment": treatment,
        "key_result": f"{sid} finding", "study_type": study_type, "sample_size": n,
        "evidence_snippet": f"{sid} snippet", "url": None, "doi": None,
        "access_status": "open", "abstract": f"{sid} abstract", "access_type": "published_oa",
    }


def _fixture() -> list[dict]:
    """3 subgroups, 3 connections; mixed source_types; a subgroup-only row + a no-subgroup row.

    Expected scoring (×10): GBA-PD/Ambroxol 83.0 (count3, lit+trial+grant), GBA-PD/Rapamycin 73.0
    (count1, same subgroup types), LRRK2-PD/LRRK2 inhibitor 58.0 (count2, lit-only)."""
    return [
        _ev(1, "literature", "L1", subgroup="GBA-PD", mechanism="GCase deficiency", treatment="Ambroxol"),
        _ev(2, "literature", "L2", subgroup="GBA-PD", mechanism="GCase deficiency", treatment="Ambroxol"),
        _ev(3, "trial", "T1", subgroup="GBA-PD", mechanism="GCase deficiency", treatment="Ambroxol", study_type="Phase 2"),
        _ev(4, "grant", "G1", subgroup="GBA-PD", mechanism="Autophagy", treatment="Rapamycin"),
        _ev(5, "literature", "L3", subgroup="LRRK2-PD", mechanism="Kinase hyperactivity", treatment="LRRK2 inhibitor"),
        _ev(6, "literature", "L4", subgroup="LRRK2-PD", mechanism="Kinase hyperactivity", treatment="LRRK2 inhibitor"),
        _ev(7, "literature", "L5", subgroup="Idiopathic-PD"),  # subgroup only → subgroup, no connection
        _ev(8, "literature", "L6"),                            # no subgroup → ignored by the subgroup agent
    ]


def _dump(db: Path) -> dict:
    """Read the clock-free columns of all 4 adapter tables (ordered) for structural/determinism checks."""
    c = sqlite3.connect(str(db))
    try:
        return {
            "evidence": c.execute(
                "SELECT evidence_id, source_type, source_id, subgroup, mechanism, treatment "
                "FROM evidence ORDER BY evidence_id").fetchall(),
            "subgroups": c.execute(
                "SELECT subgroup_id, name, defining_features, notes FROM subgroups ORDER BY subgroup_id").fetchall(),
            "treatment_connections": c.execute(
                "SELECT connection_id, subgroup_id, mechanism, treatment, evidence_strength, commercial_potential "
                "FROM treatment_connections ORDER BY connection_id").fetchall(),
            "connection_evidence": c.execute(
                "SELECT connection_id, evidence_id FROM connection_evidence "
                "ORDER BY connection_id, evidence_id").fetchall(),
        }
    finally:
        c.close()


# === the four tables populate + the ×10 rescale ==================================================


def test_build_populates_four_tables_and_rescales(tmp_path):
    db = tmp_path / "local.sqlite"
    summary = build_local_grades(_fixture(), db)

    assert summary["evidence"] == 8
    assert summary["subgroups"] == 3                  # GBA-PD, LRRK2-PD, Idiopathic-PD (no-subgroup row dropped)
    assert summary["treatment_connections"] == 3
    assert summary["connection_evidence"] == 6        # Ambroxol←3, Rapamycin←1, LRRK2 inhibitor←2
    assert summary["skipped_connections"] == 0

    # the rescale: strengths are ×10 of the [0,10] scores (8.3/7.3/5.8), NOT the raw scores.
    strengths = sorted(r[4] for r in _dump(db)["treatment_connections"])
    assert strengths == [58.0, 73.0, 83.0]
    assert summary["evidence_strength_min"] == 58.0 and summary["evidence_strength_max"] == 83.0


def test_evidence_strength_in_0_100(tmp_path):
    db = tmp_path / "local.sqlite"
    build_local_grades(_fixture(), db)
    for (_cid, _sg, _mech, _treat, strength, _comm) in _dump(db)["treatment_connections"]:
        assert 0.0 <= strength <= 100.0          # the relay's explicit lands-in-[0,100] check
        assert strength >= 50.0                  # the heuristic's 5/10 floor → ≥50 after ×10 (decision: over-grades risk)


def test_connection_evidence_links_back_to_valid_evidence(tmp_path):
    db = tmp_path / "local.sqlite"
    build_local_grades(_fixture(), db)
    d = _dump(db)
    evidence_ids = {r[0] for r in d["evidence"]}
    per_conn: dict[int, int] = {}
    for cid, eid in d["connection_evidence"]:
        assert eid in evidence_ids               # every link references a real evidence row (FK-valid)
        per_conn[cid] = per_conn.get(cid, 0) + 1
    assert sorted(per_conn.values()) == [1, 2, 3]  # Rapamycin←1, LRRK2 inhibitor←2, Ambroxol←3


def test_subgroup_only_row_makes_subgroup_without_connection(tmp_path):
    db = tmp_path / "local.sqlite"
    build_local_grades(_fixture(), db)
    d = _dump(db)
    names = {r[1] for r in d["subgroups"]}
    assert "Idiopathic-PD" in names              # the subgroup-only row still forms a subgroup
    # …but no treatment_connection references it (its row had no mechanism/treatment).
    idiopathic_sgid = next(r[0] for r in d["subgroups"] if r[1] == "Idiopathic-PD")
    assert all(tc[1] != idiopathic_sgid for tc in d["treatment_connections"])


# === the UNIQUE(subgroup_id, treatment) merge: same subgroup+treatment, different mechanism ======


def test_merge_collapses_same_subgroup_treatment_different_mechanism(tmp_path):
    db = tmp_path / "local.sqlite"
    rows = [
        _ev(1, "literature", "S1", subgroup="X", mechanism="M1", treatment="Tt"),
        _ev(2, "trial", "S2", subgroup="X", mechanism="M2", treatment="Tt", study_type="Phase 1"),
    ]
    summary = build_local_grades(rows, db)  # two triples collide on (X, Tt) → ONE connection (no UNIQUE crash)
    assert summary["treatment_connections"] == 1
    assert summary["connection_evidence"] == 2   # backing = the union of both merged triples (both rows)
    tc = _dump(db)["treatment_connections"][0]
    assert tc[4] == 68.0                          # max merged strength (6.8) ×10


# === determinism =================================================================================


def test_deterministic(tmp_path):
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    build_local_grades(_fixture(), a)
    build_local_grades(_fixture(), b)
    assert _dump(a) == _dump(b)


# === ZERO shared-DB write: the only shared-DB path (psycopg) is lazy + read-only =================


def test_no_module_level_db_driver_and_runs_without_a_url(tmp_path, monkeypatch):
    # importing/using the runner must not require psycopg — it is imported lazily, ONLY inside the
    # read-only pull. The fixture path never touches a shared DB.
    assert "psycopg" not in vars(blg)            # no module-level driver binding
    monkeypatch.delenv("SUPABASE_DATABASE_URL", raising=False)
    db = tmp_path / "local.sqlite"
    summary = build_local_grades(_fixture(), db)  # no URL, no env → builds purely from the rows
    assert summary["treatment_connections"] == 3
    # the source confirms the only shared-DB statement is a SELECT (no INSERT/UPDATE/DELETE on the pull).
    import inspect
    src = inspect.getsource(blg.pull_evidence)
    assert "SELECT" in src and "FROM evidence" in src
    for write in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE"):
        assert write not in src.upper().replace("READ_ONLY", "")


# === CUA consumes the snapshot READ-ONLY (the adapter reads it; grades bucket correctly) =========


def test_cua_adapter_consumes_snapshot_readonly(tmp_path):
    from cua.nih.adapters.neurodiscover import bucket_grade, task_from_db
    from cua.nih.grant_call import default_grant_call
    from cua.types import Grade

    db = tmp_path / "local.sqlite"
    build_local_grades(_fixture(), db)

    # open EXACTLY as run_db does — file:…?mode=ro — proving the single-file (DELETE-journal) snapshot
    # opens read-only without the WAL trap; the unchanged adapter reads it without error.
    ro_uri = f"file:{db.resolve()}?mode=ro"
    task = task_from_db(ro_uri, "local-runner-rt", default_grant_call())
    assert task is not None

    # the rescale is what makes grades bucket meaningfully: 8.3 (raw) would bucket MINIMAL; 83.0 → STRONG.
    assert bucket_grade(8.3) == Grade.MINIMAL
    strengths = [r[4] for r in _dump(db)["treatment_connections"]]
    assert any(bucket_grade(s) == Grade.STRONG for s in strengths)      # the rescaled 83.0
    assert all(bucket_grade(s) != Grade.MINIMAL for s in strengths)     # nothing collapses to minimal


# === the fixture columns cover the adapter's read set ============================================


def test_fixture_rows_carry_the_adapter_read_columns():
    # a guard that EVIDENCE_COLS (what the runner copies) covers what the fixture supplies.
    sample = _fixture()[0]
    for col in EVIDENCE_COLS:
        assert col in sample
    assert GRADE_SCALE == 10.0
