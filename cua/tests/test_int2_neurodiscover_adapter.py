"""INT-2 adapter unit test — `cua.nih.adapters.neurodiscover.task_from_db` vs upstream `seed_data.json`.

Builds a PRIVATE local SQLite from the upstream DEMO seed (no dependency on upstream code), opens it
READ-ONLY, and asserts the adapter yields a well-formed `input_contract` per adaption.md #1–#10 +
GATE-1. Deterministic + offline; **skips cleanly** when no seed is available.

Owner: INT-2 (builder 1). This is an integration test of the input boundary — it touches no role body
and no eval, and it never reads/writes the shared upstream DB (it builds its own throwaway SQLite).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from cua.nih.adapters.neurodiscover import (
    Subgroup,
    Treatment,
    _development_stage,
    _stage_rank,
    bucket_grade,
    resolvable_id,
    task_from_db,
)
from cua.nih.grant_call import default_grant_call
from cua.nih.task import NIHGrantTask
from cua.types import Grade

# Minimal schema covering exactly the columns the adapter reads (mirrors neurodiscover/schema.sql).
_SCHEMA = """
CREATE TABLE evidence(
  evidence_id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
  title TEXT, year INTEGER, venue TEXT, key_result TEXT, study_type TEXT, sample_size INTEGER,
  evidence_snippet TEXT, doi TEXT, access_status TEXT, abstract TEXT, publication_year INTEGER,
  UNIQUE(source_type, source_id));
CREATE TABLE subgroups(
  subgroup_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, defining_features TEXT, notes TEXT);
CREATE TABLE treatment_connections(
  connection_id INTEGER PRIMARY KEY AUTOINCREMENT, subgroup_id INTEGER NOT NULL, mechanism TEXT,
  treatment TEXT NOT NULL, evidence_strength REAL, commercial_potential REAL, UNIQUE(subgroup_id, treatment));
CREATE TABLE connection_evidence(
  connection_id INTEGER NOT NULL, evidence_id INTEGER NOT NULL, PRIMARY KEY(connection_id, evidence_id));
"""


def _find_seed() -> Path | None:
    """Locate upstream seed_data.json (env override, then the sibling neurodiscover checkout)."""
    env = os.environ.get("NEURODISCOVER_SEED")
    candidates = [env] if env else []
    here = Path(__file__).resolve()
    repo = here.parents[1]  # <repo>/cua
    candidates += [
        repo / ".." / "Quorum" / "neurodiscover" / "seed_data.json",
        repo / ".." / "neurodiscover" / "seed_data.json",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    return None


def _build_seed_db(seed: dict, path: str) -> None:
    """Replicate the upstream `cli.py build` for the columns the adapter reads (DEMO seed → tables).
    The seed leaves `evidence_strength` NULL (Agent 4 unbuilt) → every connection grade is minimal."""
    c = sqlite3.connect(path)
    try:
        c.executescript(_SCHEMA)
        for s in seed["subgroups"]:
            c.execute(
                "INSERT INTO subgroups(name, defining_features, notes) VALUES(?,?,?)",
                (s["name"], s["defining_features"], s["notes"]),
            )
        src2eid: dict[str, int] = {}
        for e in seed["evidence"]:
            cur = c.execute(
                "INSERT INTO evidence(source_type, source_id, title, year, venue, key_result, "
                "study_type, sample_size, evidence_snippet) VALUES(?,?,?,?,?,?,?,?,?)",
                (e["source_type"], e["source_id"], e["title"], e["year"], e["venue"],
                 e["key_result"], e["study_type"], e["sample_size"], e["evidence_snippet"]),
            )
            src2eid[e["source_id"]] = cur.lastrowid
        name2sg = {row[1]: row[0] for row in c.execute("SELECT subgroup_id, name FROM subgroups")}
        for tc in seed["treatment_connections"]:
            cur = c.execute(
                "INSERT INTO treatment_connections(subgroup_id, mechanism, treatment, evidence_strength) "
                "VALUES(?,?,?,NULL)",
                (name2sg[tc["subgroup_name"]], tc["mechanism"], tc["treatment"]),
            )
            cid = cur.lastrowid
            for sid in tc["supporting_source_ids"]:
                c.execute(
                    "INSERT INTO connection_evidence(connection_id, evidence_id) VALUES(?,?)",
                    (cid, src2eid[sid]),
                )
        c.commit()
    finally:
        c.close()


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    """A read-only SQLite built from the real seed + the task the adapter assembles from it."""
    seed_path = _find_seed()
    if seed_path is None:
        pytest.skip("no neurodiscover seed_data.json available (set NEURODISCOVER_SEED)")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    db = str(tmp_path_factory.mktemp("int2") / "seed.db")
    _build_seed_db(seed, db)
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)  # SELECT-only — a write would raise
    try:
        task = task_from_db(ro, run_id="int2-test", grant_call=default_grant_call())
    finally:
        ro.close()
    return {"seed": seed, "db": db, "task": task}


# --- pure-function units (independent of the seed, which is all-NULL) -----------------------------


def test_bucket_grade_boundaries():
    assert bucket_grade(None) is Grade.MINIMAL          # NULL → minimal (GATE-1)
    assert bucket_grade(0) is Grade.MINIMAL
    assert bucket_grade(24.99) is Grade.MINIMAL
    assert bucket_grade(25) is Grade.WEAK               # round DOWN on ties
    assert bucket_grade(49.99) is Grade.WEAK
    assert bucket_grade(50) is Grade.MODERATE
    assert bucket_grade(74.99) is Grade.MODERATE
    assert bucket_grade(75) is Grade.STRONG
    assert bucket_grade(100) is Grade.STRONG


def test_bucket_grade_emits_ordinal_not_float():
    # No raw float leaks past the adapter — the bucket emits a real ordinal Grade enum (GATE-1).
    for s in (None, 0, 30, 60, 90):
        assert isinstance(bucket_grade(s), Grade)


def test_resolvable_id_scheme_detection():
    assert resolvable_id("literature", "12345678") == "12345678"            # digit → PMID
    assert resolvable_id("literature", "10.1/abc") == "10.1/abc"            # non-digit → DOI (self)
    assert resolvable_id("literature", "DEMO-PMID-001", doi="10.1/x") == "10.1/x"  # prefer doi col
    assert resolvable_id("literature", "DEMO-PMID-001") == "DEMO-PMID-001"  # DOI scheme, no doi col
    assert resolvable_id("trial", "NCT01234567") == "NCT01234567"          # NCT
    assert resolvable_id("grant", "1R01NS123456") == "1R01NS123456"        # core_project_num


def test_development_stage_ordinal():
    assert _stage_rank("preclinical + cohort") == 3        # compound → most-advanced token
    assert _stage_rank("Phase 2") == 6
    assert _stage_rank("phase iii") == 7                   # roman nesting resolves to highest
    assert _stage_rank("registry") == 0                    # unrecognized
    assert _development_stage([{"study_type": "mouse"}, {"study_type": "Phase 2"}]) == "Phase 2"
    assert _development_stage([{"study_type": "registry"}]) == ""   # fallback
    assert _development_stage([]) == ""                             # no backing


# --- against the real seed ------------------------------------------------------------------------


def test_task_is_nihgranttask_with_intake_ok(seeded):
    task = seeded["task"]
    assert isinstance(task, NIHGrantTask)            # build_task called unchanged
    assert task.intake_refusal() is None             # default_grant_call satisfies §2.5


def test_corpus_all_rows_stable_ids_demo_unreal(seeded):
    seed, task = seeded["seed"], seeded["task"]
    corpus = task.source_set.sources
    assert len(corpus) == len(seed["evidence"])      # ALL rows, none dropped (no Agent-6 filter)
    assert all(not p.real for p in corpus)           # every DEMO id → real=False (#3)
    assert {p.id.split(":")[0] for p in corpus} >= {"literature", "trial"}  # all source_types (#6)
    # stable natural key source_type:source_id (#2), and authors empty (#4)
    by_src = {(e["source_type"], e["source_id"]) for e in seed["evidence"]}
    assert {(p.id.split(":", 1)[0], p.id.split(":", 1)[1]) for p in corpus} == by_src
    assert all(p.authors == [] for p in corpus)
    # DEMO literature (non-digit) → DOI scheme == source_id; DEMO trial → NCT == source_id
    for p in corpus:
        st, sid = p.id.split(":", 1)
        assert p.resolvable_id == sid


def test_grades_minimal_and_flagged_uncalibrated(seeded):
    seed, task = seeded["seed"], seeded["task"]
    ev = task.evidence
    assert len(ev) == len(seed["treatment_connections"])   # one entry per connection
    assert all(k.startswith("connection:") for k in ev)    # claim_id = connection key (GATE-1)
    for entry in ev.values():
        assert isinstance(entry.grade, Grade)              # ordinal, never a float
        assert entry.grade is Grade.MINIMAL                # seed NULL scores → minimal
        assert entry.evidence_features["grade_source"] == "neurodiscover_bucket_v1"
        assert entry.evidence_features["calibrated"] is False
        # no raw evidence_strength float leaked into the features
        assert "evidence_strength" not in entry.evidence_features


def test_support_ids_resolve_via_connection_evidence(seeded):
    task = seeded["task"]
    corpus_ids = {p.id for p in task.source_set.sources}
    for entry in task.evidence.values():
        assert entry.support_source_ids                    # each connection has backing
        assert all(sid in corpus_ids for sid in entry.support_source_ids)  # ∈ corpus


def test_subgroups_and_treatments_mapped(seeded):
    seed, task = seeded["seed"], seeded["task"]
    assert {s.name for s in task.subgroups} == {s["name"] for s in seed["subgroups"]}
    assert all(isinstance(s, Subgroup) and s.definition and s.rationale for s in task.subgroups)
    assert all(isinstance(t, Treatment) and t.modality == "" for t in task.treatments)
    # treatment name ← treatment, target ← mechanism
    upstream_names = {tc["treatment"] for tc in seed["treatment_connections"]}
    assert {t.name for t in task.treatments} == upstream_names
    # development_stage is the most-advanced backing study_type (descriptive)
    stages = {t.name: t.development_stage for t in task.treatments}
    assert stages.get("microglial modulation") == "mouse"   # only mouse backing
    assert stages.get("GCase activation") == "Phase 2"      # Phase-2 trial outranks preclinical+cohort


def test_commercial_omitted(seeded):
    assert seeded["task"].commercial is None                # adaption.md #10


def test_deterministic(seeded):
    db = seeded["db"]
    def read():
        ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            t = task_from_db(ro, run_id="x", grant_call=default_grant_call())
        finally:
            ro.close()
        return (
            [p.id for p in t.source_set.sources],
            [(k, t.evidence[k].grade.value, tuple(t.evidence[k].support_source_ids)) for k in t.evidence],
            [(x.name, x.development_stage) for x in t.treatments],
        )
    assert read() == read()


def test_read_only_connection_rejects_writes(seeded):
    # Proves the adapter ran against a SELECT-only connection: a write on it raises.
    ro = sqlite3.connect(f"file:{seeded['db']}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro.execute("INSERT INTO subgroups(name) VALUES('x')")
    finally:
        ro.close()
