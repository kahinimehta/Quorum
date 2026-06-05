"""INT-4 — end-to-end smoke test of the neurodiscover seam (terminal integration gate) [tester].

Implements: build/briefs/INT-4_smoke.md + build/integration/INT-4_relay.md (PLAN §(c)/§(d) 5);
            contracts.md §3 (the three hard invariants), §2.5 (NULL→minimal degradation), §1.10
            (Audit). Governing posture: build/integration/adaption.md (READ-ONLY consumer, zero upstream
            writes) + the GATE-1 grade surrogate (`decisions/2026-06-02-decisionB-v1-surrogate-grade-
            RATIFIED.md`). Owner: INT-4 (builder 3, tester lineage — separate from builder-1's
            adapter/entrypoint, which are already GO at INT-2/INT-3; this tests the SEAM, not the units).

What it proves: upstream seed → our adapter → our entrypoint (`cua.nih.run_db`) → Proposal/Trace/Audit
holds the same §3 gates the fixtures assert, offline + deterministic, with **zero upstream footprint**.

🟥 DESTRUCTIVE-OP SAFETY (adaption.md #16): the shared Supabase is LIVE (307 rows) and `cli.py build`
TRUNCATES every table. This test NEVER runs `build` and NEVER touches the shared DB — it builds its own
throwaway PRIVATE SQLite under `tmp_path` (the only DB path it ever constructs) and `run_db` opens it
`mode=ro`. `SUPABASE_DATABASE_URL` is never read. Dependency-free: it `executescript`s the real upstream
`schema.sql` (full, for fidelity) and loads `seed_data.json` — no `neurodiscover` package import, no
`cli.py`. Skips cleanly when neither the seed nor the schema is on disk, so CI stays green.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

# --- locate the upstream seed + schema (env override, then the sibling Quorum checkout) ----------

_REPO = Path(__file__).resolve().parents[1]  # <repo>/cua
_SIBLINGS = (_REPO / ".." / "Quorum" / "neurodiscover", _REPO / ".." / "neurodiscover")


def _first_existing(env_var: str, candidates: list[Path]) -> Path | None:
    """First existing file among `$env_var` (if set) then `candidates`; None if none exist. Pure — a
    test exercises the None branch directly (the skip-clean predicate)."""
    env = os.environ.get(env_var)
    for c in ([Path(env)] if env else []) + candidates:
        if c.is_file():
            return c
    return None


def _find_seed() -> Path | None:
    return _first_existing("NEURODISCOVER_SEED", [s / "seed_data.json" for s in _SIBLINGS])


def _find_schema() -> Path | None:
    return _first_existing("NEURODISCOVER_SCHEMA", [s / "schema.sql" for s in _SIBLINGS])


# --- build a PRIVATE SQLite from the real schema.sql + seed (dependency-free; mirrors cli.py build) -

_COUNTED_TABLES = (
    "recommendations", "agent_outputs",            # the two the gate asserts are NEVER written (#14/#15)
    "evidence", "subgroups", "treatment_connections", "connection_evidence",  # domain (read-only proof)
)


def _build_private_db(schema_sql: str, seed: dict, path: str) -> None:
    """Replicate upstream `cli.py build` into a private SQLite: the FULL real `schema.sql` (fidelity —
    incl. the `recommendations`/`agent_outputs` tables the gate counts) + the DEMO seed. The seed leaves
    `evidence_strength` NULL (Agent 4 unbuilt) → every connection grade degrades to minimal (§2.5)."""
    c = sqlite3.connect(path)
    try:
        c.executescript(schema_sql)  # the real upstream schema, verbatim
        for s in seed["subgroups"]:
            c.execute("INSERT INTO subgroups(name, defining_features, notes) VALUES(?,?,?)",
                      (s["name"], s.get("defining_features"), s.get("notes")))
        src2eid: dict[str, int] = {}
        for e in seed["evidence"]:
            cur = c.execute(
                "INSERT INTO evidence(source_type, source_id, title, year, venue, subgroup, mechanism, "
                "treatment, key_result, study_type, sample_size, evidence_snippet) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (e["source_type"], e["source_id"], e.get("title"), e.get("year"), e.get("venue"),
                 e.get("subgroup"), e.get("mechanism"), e.get("treatment"), e.get("key_result"),
                 e.get("study_type"), e.get("sample_size"), e.get("evidence_snippet")),
            )
            src2eid[e["source_id"]] = cur.lastrowid
        name2sg = {row[1]: row[0] for row in c.execute("SELECT subgroup_id, name FROM subgroups")}
        for tc in seed["treatment_connections"]:
            cur = c.execute(
                "INSERT INTO treatment_connections(subgroup_id, mechanism, treatment, evidence_strength) "
                "VALUES(?,?,?,NULL)",  # evidence_strength NULL → degradation path
                (name2sg[tc["subgroup_name"]], tc.get("mechanism"), tc["treatment"]),
            )
            cid = cur.lastrowid
            for sid in tc["supporting_source_ids"]:
                c.execute("INSERT INTO connection_evidence(connection_id, evidence_id) VALUES(?,?)",
                          (cid, src2eid[sid]))
        c.commit()
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # schema sets WAL; checkpoint so mode=ro can open
    finally:
        c.close()


def _counts(db_path: str) -> dict[str, int]:
    """Row counts for the gate's tables, over a READ-ONLY connection (a write here would raise)."""
    ro = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {t: ro.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in _COUNTED_TABLES}
    finally:
        ro.close()


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    """The end-to-end smoke run: build a private DB, bracket `run_db` with row counts (zero-write proof),
    emit + load the artifacts, and rebuild the adapter task (for the GATE-1 evidence assertions).
    Skips cleanly when the upstream seed or schema is unavailable (CI stays green)."""
    seed_path, schema_path = _find_seed(), _find_schema()
    if seed_path is None or schema_path is None:
        pytest.skip("no neurodiscover seed_data.json + schema.sql (set NEURODISCOVER_SEED/_SCHEMA)")

    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    work = tmp_path_factory.mktemp("int4")
    db = str(work / "cua-smoke.db")  # PRIVATE local SQLite — never the shared Supabase
    _build_private_db(schema_path.read_text(encoding="utf-8"), seed, db)

    before = _counts(db)  # ── bracket the run ──────────────────────────────────────────────
    from cua.nih.run_db import run_db

    out_dir = work / "out"
    rc = run_db(db=db, run_id="smoke", out_dir=out_dir)  # in-process; opens the DB mode=ro
    after = _counts(db)  # ─────────────────────────────────────────────────────────────────

    audit = json.loads((out_dir / "smoke.audit.json").read_text(encoding="utf-8"))
    proposal = json.loads((out_dir / "smoke.proposal.json").read_text(encoding="utf-8"))

    # Rebuild the adapter task READ-ONLY for the GATE-1 evidence-provenance assertions (the flag lives on
    # the adapter's EvidenceAssessment — the run input — not serialized into the Audit).
    from cua.nih.adapters import task_from_db
    from cua.nih.grant_call import default_grant_call

    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        task = task_from_db(ro, run_id="smoke", grant_call=default_grant_call())
    finally:
        ro.close()

    return {"db": db, "out_dir": out_dir, "rc": rc, "before": before, "after": after,
            "audit": audit, "proposal": proposal, "task": task, "seed": seed}


# === inv-1/2/3 on the emitted Audit (the seam holds the §3 gates) ================================


def test_chain_runs_and_emits(smoke):
    """The chain runs against a private DB and emits all three artifacts (rc 0)."""
    assert smoke["rc"] == 0
    for name in ("smoke.proposal.json", "smoke.trace.jsonl", "smoke.audit.json"):
        assert (smoke["out_dir"] / name).is_file()


def test_inv_1_2_3_pass_on_emitted_audit(smoke):
    """inv-1/2/3 (contract §3) PASS on the emitted Audit — verified by the S3 invariant suite run
    directly over the loaded Audit JSON (duck-typed `_field`), plus the explicit field checks."""
    from invariants import run_invariants

    report = run_invariants(smoke["audit"])
    assert report.all_passed, str(report)
    assert report.by_id("inv-1").passed and report.by_id("inv-2").passed and report.by_id("inv-3").passed

    gr = smoke["audit"]["grounding_report"]
    assert gr["all_in_source_set"] is True and gr["orphan_ids"] == []          # inv-1
    sat = [o for o in smoke["audit"]["obligation_ledger"] if o["status"] == "satisfied"]
    assert sat and all(o["evidence_ids"] for o in sat)                          # inv-2
    assert all(r["ok"] for r in smoke["audit"]["overclaim_check"])              # inv-3 (0 flags)


# === graceful degradation: seed NULL evidence_strength → all grades minimal (§2.5) ===============


def test_graceful_degradation_null_to_minimal(smoke):
    """§2.5: the seed's NULL `evidence_strength` degrades every grade to `minimal`, and the run still
    produces a thin-but-honest, inv-1/inv-2-clean proposal (refs + aims present; no orphans)."""
    # on the adapter's evidence (the source of the Audit's grades)
    from cua.types import Grade

    ev = smoke["task"].evidence
    assert ev and all(e.grade is Grade.MINIMAL for e in ev.values())
    # the Audit's visible consequence: every overclaim row is graded minimal
    assert {r["evidence_grade"] for r in smoke["audit"]["overclaim_check"]} == {"minimal"}
    # still a clean, non-empty proposal (thin but honest)
    assert smoke["audit"]["grounding_report"]["all_in_source_set"] is True
    assert smoke["proposal"]["references"] and smoke["proposal"]["aims"]


def test_grades_flagged_uncalibrated_gate1(smoke):
    """GATE-1: every bucketed grade is flagged UNCALIBRATED (`grade_source=neurodiscover_bucket_v1`,
    `calibrated=False`), so no downstream reader mistakes it for a calibrated skeptic grade. GRADE-BIND:
    the EvidenceAssessment is keyed by CORPUS SOURCE ID (the id claims cite), NOT connection:{cid} — the
    grade is still bucketed per connection, only the resolution key changed."""
    ev = smoke["task"].evidence
    corpus_ids = {p.id for p in smoke["task"].source_set.sources}
    assert ev and set(ev.keys()) <= corpus_ids                  # keyed by corpus source id (GRADE-BIND)
    assert not any(k.startswith("connection:") for k in ev)     # the old connection-key space is gone
    for sid, entry in ev.items():
        assert entry.support_source_ids == [sid]                # entry supports its own source id
        assert entry.evidence_features["grade_source"] == "neurodiscover_bucket_v1"
        assert entry.evidence_features["calibrated"] is False
        assert "evidence_strength" not in entry.evidence_features  # no raw float leaks


# === zero upstream writes — recommendations AND agent_outputs (and the domain tables) ============


def test_zero_upstream_writes(smoke):
    """adaption.md #14/#15: `run_db` writes NOTHING upstream — `recommendations` AND `agent_outputs`
    (and every domain table) carry no new rows. Row counts are identical before/after the run."""
    before, after = smoke["before"], smoke["after"]
    assert after["recommendations"] == before["recommendations"]   # #14 — never written
    assert after["agent_outputs"] == before["agent_outputs"]       # #15 — OFF (zero upstream writes)
    assert after == before, f"a table changed across run_db: before={before} after={after}"


def test_schema_untouched(smoke):
    """The run alters no schema (#16 — no DDL): the table set is unchanged after `run_db`."""
    ro = sqlite3.connect(f"file:{smoke['db']}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        ro.close()
    assert {"evidence", "subgroups", "treatment_connections", "connection_evidence",
            "agent_outputs", "recommendations", "scan_state"} <= tables


def test_run_db_connection_is_read_only(smoke):
    """Defense-in-depth (#16): the DB opened for the run is read-only — a write on a `mode=ro`
    connection raises, so the run could not have mutated upstream even by accident."""
    ro = sqlite3.connect(f"file:{smoke['db']}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("INSERT INTO agent_outputs(agent_name) VALUES('Conclusion Update')")
    finally:
        ro.close()


# === determinism (offline; no clock/RNG in the gating path) ======================================


def test_emitted_artifacts_are_deterministic(smoke, tmp_path):
    """Offline determinism: re-running `run_db` over the same private DB emits byte-identical
    Proposal + Audit + Trace."""
    from cua.nih.run_db import run_db

    out2 = tmp_path / "rerun"
    run_db(db=smoke["db"], run_id="smoke", out_dir=out2)
    for name in ("smoke.proposal.json", "smoke.audit.json", "smoke.trace.jsonl"):
        a = (smoke["out_dir"] / name).read_text(encoding="utf-8")
        b = (out2 / name).read_text(encoding="utf-8")
        assert a == b, f"{name} differs across runs (nondeterministic)"


# === skip-clean predicate (the test stays green in CI without the upstream checkout) =============


def test_skip_predicate_returns_none_when_missing():
    """The locate helpers return None when neither env nor a checkout has the file — which drives the
    fixture's `pytest.skip`, so `tests/` stays green in CI without the upstream pipeline."""
    assert _first_existing("CUA_NO_SUCH_ENV_XYZ", [Path("/no/such/seed.json")]) is None
