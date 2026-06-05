"""SCALE-CFG — `run_db` compute knobs (`--n-samples`, `--max-rounds`, `--bar`) for the scaling demo.

`build/live/SCALE-CFG_relay.md`: sweep the two test-time-compute axes (design §0/§5) from the CLI —
best-of-N (parallel, the Synthesizer's `RoleConfig.n_samples`) and revise rounds (sequential,
`RUN_CONFIG.max_rounds`), plus an optional uniform F1=F2 `--bar`. Hard line: the knobs only WIDEN the
existing §1.8/§1.11 surface — **no flag ⇒ today's run, byte-for-byte** (n=3, max_rounds=3, bar=5); the
fixture path / oracle is untouched.

Owner: SCALE-CFG (builder 1). Offline + deterministic (surrogate roles; no network, no key).
"""

from __future__ import annotations

import json
import sqlite3

from cua.nih.grant_call import default_grant_call
from cua.nih.run import RUN_CONFIG
from cua.nih.run_db import (
    _DEFAULT_BAR,
    _DEFAULT_MAX_ROUNDS,
    _apply_n_samples,
    _run_config,
    main,
    run_db,
)
from cua.roles.synthesizer import ArgumentSynthesizer


def _mini_db(path: str) -> None:
    """An 8-row neurodiscover-shaped SQLite (enough corpus to drive a real best-of-N + revise loop)."""
    c = sqlite3.connect(path)
    try:
        c.executescript(
            """
            CREATE TABLE evidence(evidence_id INTEGER PRIMARY KEY, source_type TEXT, source_id TEXT, title TEXT,
                year INTEGER, publication_year INTEGER, venue TEXT, key_result TEXT, evidence_snippet TEXT,
                abstract TEXT, doi TEXT, study_type TEXT, sample_size INTEGER, access_status TEXT);
            CREATE TABLE subgroups(subgroup_id INTEGER PRIMARY KEY, name TEXT, defining_features TEXT, notes TEXT);
            CREATE TABLE treatment_connections(connection_id INTEGER PRIMARY KEY, subgroup_id INTEGER,
                mechanism TEXT, treatment TEXT, evidence_strength REAL);
            CREATE TABLE connection_evidence(connection_id INTEGER, evidence_id INTEGER);
            """
        )
        rows = [
            (i, "literature", str(100 + i), f"Paper {i}", 2018 + i % 5, None, "J",
             f"finding {i}: gcase pathway result variant {i}", None, None, f"10/{i}", "cohort", 40 + i, None)
            for i in range(1, 9)
        ]
        c.executemany(
            "INSERT INTO evidence(evidence_id,source_type,source_id,title,year,publication_year,venue,"
            "key_result,evidence_snippet,abstract,doi,study_type,sample_size,access_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        c.execute("INSERT INTO subgroups(subgroup_id,name,defining_features,notes) VALUES (1,'g','f','n')")
        c.execute("INSERT INTO treatment_connections(connection_id,subgroup_id,mechanism,treatment,evidence_strength) VALUES (1,1,'GCase','chaperone',NULL)")
        c.executemany("INSERT INTO connection_evidence(connection_id,evidence_id) VALUES (?,?)", [(1, i) for i in range(1, 9)])
        c.commit()
    finally:
        c.close()


def _content(tmp_path, sub, **kw):
    """Run run_db with capture ON into a fresh out-dir; return the parsed content.json."""
    db = tmp_path / "m.db"
    if not db.exists():
        _mini_db(str(db))
    out = tmp_path / sub
    rc = run_db(db=str(db), run_id="s", out_dir=out, capture_content=True, **kw)
    assert rc == 0
    return json.loads((out / "s.content.json").read_text())


# === defaults are DERIVED from RUN_CONFIG (cannot drift) =========================================


def test_defaults_derive_from_run_config():
    assert _DEFAULT_MAX_ROUNDS == RUN_CONFIG.max_rounds == 3
    assert _DEFAULT_BAR == 5
    rc = _run_config(_DEFAULT_MAX_ROUNDS, _DEFAULT_BAR)
    assert rc.max_rounds == RUN_CONFIG.max_rounds
    assert rc.dimension_thresholds == RUN_CONFIG.dimension_thresholds   # {"F1":5,"F2":5}


# === the load-bearing invariant: no flags ⇒ today's run, byte-for-byte ===========================


def test_no_flags_equals_explicit_defaults(monkeypatch, tmp_path):
    """A no-flag run and a run with the knobs set EXPLICITLY to the documented defaults (3/3/5) produce
    BYTE-IDENTICAL proposal/trace/audit/ingestion — so the new code path at default values changes
    nothing, and 'defaults reproduce today's run' holds."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.delenv("CUA_CAPTURE_CONTENT", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    a, b = tmp_path / "noflag", tmp_path / "explicit"
    assert run_db(db=str(db), run_id="s", out_dir=a) == 0
    assert run_db(db=str(db), run_id="s", out_dir=b, n_samples=3, max_rounds=3, bar=5) == 0
    for ext in ("proposal.json", "trace.jsonl", "audit.json", "ingestion.json"):
        assert (a / f"s.{ext}").read_bytes() == (b / f"s.{ext}").read_bytes(), f"{ext} drifted at default knobs"


# === parallel axis: --n-samples scales the Synthesizer's best-of-N ===============================


def test_n_samples_scales_synthesizer_candidates(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    for n in (5, 8):
        c = _content(tmp_path, f"n{n}", n_samples=n)
        bon = c["best_of_n"][0]
        assert bon["label"] == "synthesizer" and bon["n"] == n
        assert len(bon["candidates"]) == n
        assert sum(1 for cand in bon["candidates"] if cand["chosen"]) == 1


def test_n_samples_one_is_single_shot(monkeypatch, tmp_path):
    """n_samples=1 is the valid low end of the sweep (compute=1): the Synthesizer goes single-shot, so
    there is no best-of-N generation point — and the run still completes."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    c = _content(tmp_path, "n1", n_samples=1)
    assert c["best_of_n"] == []


def test_n_samples_override_is_instance_level_no_class_leak(tmp_path):
    """`_apply_n_samples` shadows the synthesizer stage's config INSTANCE-side; the role's class-level
    RoleConfig default stays 3 (no cross-run/global leak)."""
    db = tmp_path / "m.db"
    _mini_db(str(db))
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        from cua.nih.adapters import task_from_db

        task = task_from_db(conn, "s", default_grant_call())
    finally:
        conn.close()
    assert _apply_n_samples(task, 8) == 1                          # exactly the synthesizer stage updated
    stage = next(s for s in task.generator if s.name == "synthesizer")
    assert stage.config.n_samples == 8                            # instance override applied
    assert ArgumentSynthesizer.config.n_samples == 3             # class default UNTOUCHED


# === sequential axis: --max-rounds caps the revise loop; --bar makes it work harder ==============


def test_max_rounds_caps_revise_loop(monkeypatch, tmp_path):
    """With a forcing bar (F1=F2=9 — the surrogate's max base is 7, so the stopping rule never passes)
    the loop runs exactly `max_rounds` rounds → the sequential axis is visible + capped."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    for r in (2, 5):
        c = _content(tmp_path, f"r{r}", max_rounds=r, bar=9)
        assert len(c["rounds"]) == r
        assert len(c["critique"]) == r
        assert [e["round"] for e in c["rounds"]] == list(range(r))


def test_bar_makes_the_loop_work_harder(monkeypatch, tmp_path):
    """At the same max_rounds, a higher bar forces MORE revise rounds (it raises the stopping
    threshold) — the knob the operator uses to exercise the rounds axis."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    default_bar = _content(tmp_path, "barlow", max_rounds=3)            # bar=5: passes early
    high_bar = _content(tmp_path, "barhigh", max_rounds=3, bar=9)       # bar=9: never passes
    assert len(high_bar["rounds"]) > len(default_bar["rounds"])
    assert len(high_bar["rounds"]) == 3                                 # capped at max_rounds


# === CLI: main() threads the flags end-to-end ====================================================


def test_cli_main_threads_compute_flags(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    out = tmp_path / "cli"
    rc = main([
        "--db", str(db), "--run-id", "s", "--out-dir", str(out),
        "--n-samples", "8", "--max-rounds", "6", "--bar", "9", "--capture-content",
    ])
    assert rc == 0
    c = json.loads((out / "s.content.json").read_text())
    assert c["best_of_n"][0]["n"] == 8           # parallel axis parsed + applied
    assert len(c["rounds"]) == 6                  # sequential axis parsed + applied (bar=9 forces all 6)
