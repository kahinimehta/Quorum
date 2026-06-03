"""CONTENT-CAP — gated content-capture audit (`<run>.content.json`; observation-only).

`build/live/CONTENT-CAP_relay.md`: persist the intermediate content the Trace (flow) and Audit
(ratification) drop — the best-of-N REJECTED candidates + scores, the per-round draft evolution, the
Reviser hedge diffs, and the full per-round critique — in a GATED, SEPARATE artifact. The load-bearing
invariant: capture is OBSERVATION-ONLY and OUT of the trust path, so a run with capture ON and a run
with it OFF produce BYTE-IDENTICAL proposal/trace/audit; capture-ON merely ADDS `<run>.content.json`.

Owner: CONTENT-CAP (builder 1). Offline + deterministic (surrogate roles; no network, no key).
"""

from __future__ import annotations

import json
import sqlite3

from cua.capture import ContentCapture
from cua.nih.run_db import _capture_enabled, run_db
from cua.types import Claim, Draft, DraftFragment, ScoredFragment


# === a small neurodiscover-shaped SQLite the adapter can read (8 evidence rows → a real revise loop) ==


def _mini_db(path: str) -> None:
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


def _run(tmp_path, *, capture, sub):
    """Run run_db offline into a fresh out-dir; return (rc, out_dir)."""
    db = tmp_path / "m.db"
    if not db.exists():
        _mini_db(str(db))
    out = tmp_path / sub
    rc = run_db(db=str(db), run_id="cap", out_dir=out, capture_content=capture)
    return rc, out


# === the load-bearing invariant: capture-ON ≡ capture-OFF for proposal/trace/audit ================


def test_capture_off_default_emits_no_content_json(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.delenv("CUA_CAPTURE_CONTENT", raising=False)
    rc, out = _run(tmp_path, capture=False, sub="off")
    assert rc == 0
    assert not (out / "cap.content.json").exists()           # default OFF → nothing added
    # the four core artifacts are still there
    for ext in ("proposal.json", "trace.jsonl", "audit.json", "ingestion.json"):
        assert (out / f"cap.{ext}").exists()


def test_capture_on_is_byte_identical_for_core_artifacts(monkeypatch, tmp_path):
    """A run with capture ON and a run with it OFF produce BYTE-IDENTICAL proposal/trace/audit/ingestion;
    capture-ON merely ADDS content.json (the observation-only invariant)."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.delenv("CUA_CAPTURE_CONTENT", raising=False)
    rc_off, off = _run(tmp_path, capture=False, sub="off")
    rc_on, on = _run(tmp_path, capture=True, sub="on")
    assert rc_off == 0 and rc_on == 0
    for ext in ("proposal.json", "trace.jsonl", "audit.json", "ingestion.json"):
        assert (off / f"cap.{ext}").read_bytes() == (on / f"cap.{ext}").read_bytes(), f"{ext} differs with capture on"
    # ONLY the capture run adds content.json
    assert not (off / "cap.content.json").exists()
    assert (on / "cap.content.json").exists()


# === the content.json shape (deterministic, unit-testable) =======================================


def test_content_json_shape_is_complete(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.delenv("CUA_CAPTURE_CONTENT", raising=False)
    rc, out = _run(tmp_path, capture=True, sub="on")
    assert rc == 0
    content = json.loads((out / "cap.content.json").read_text())
    assert set(content) == {"capture", "best_of_n", "rounds", "reviser_hedges", "critique"}

    # best_of_n: the N candidates + each candidate's reward score + the chosen index (the synthesizer is
    # n_samples=3, reward F1) — the only record of the rejected candidates.
    assert content["best_of_n"], "expected at least one best-of-N generation point"
    bon = content["best_of_n"][0]
    assert bon["label"] == "synthesizer" and bon["dimension"] == "F1" and bon["n"] == 3
    assert "reward=F1" in bon["rationale"] and f"candidate {bon['chosen_index']}" in bon["rationale"]
    assert len(bon["candidates"]) == 3
    assert sum(1 for c in bon["candidates"] if c["chosen"]) == 1            # exactly one winner
    assert bon["candidates"][bon["chosen_index"]]["chosen"] is True
    for c in bon["candidates"]:
        assert set(c) == {"index", "score", "chosen", "fragment"}
        assert c["score"] is not None                                       # each candidate is scored
        assert "claims" in c["fragment"] and "text" in c["fragment"]

    # rounds: a per-round draft snapshot (round 0 generated; round n after the nth revise).
    assert content["rounds"], "expected per-round draft snapshots"
    assert [r["round"] for r in content["rounds"]] == sorted(r["round"] for r in content["rounds"])
    assert "fragments" in content["rounds"][0]["draft"]

    # critique: the full per-round critique (per-dimension scores + justification + spans, per-aim
    # segment scores, decision, flagged ids).
    assert content["critique"], "expected per-round critique"
    cr = content["critique"][0]
    assert set(cr) == {"round", "decision", "dimension_scores", "segment_scores", "flagged_obligations"}
    assert {"F1", "F2"} <= set(cr["dimension_scores"])                      # the gated factors
    f1 = cr["dimension_scores"]["F1"]
    assert set(f1) == {"score", "justification", "spans"}

    # reviser_hedges: per round, the exact {claim_id, before, after} changes the Reviser made.
    assert isinstance(content["reviser_hedges"], list)
    for entry in content["reviser_hedges"]:
        assert set(entry) == {"round", "hedges"}
        for h in entry["hedges"]:
            assert set(h) == {"claim_id", "before", "after"}
            assert h["before"] != h["after"]                                # only real changes recorded


def test_content_json_is_reproducible(monkeypatch, tmp_path):
    """Two capture-ON runs on the same DB produce byte-identical content.json (deterministic offline)."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.delenv("CUA_CAPTURE_CONTENT", raising=False)
    _, a = _run(tmp_path, capture=True, sub="a")
    _, b = _run(tmp_path, capture=True, sub="b")
    assert (a / "cap.content.json").read_bytes() == (b / "cap.content.json").read_bytes()


# === the gate (flag and/or env; default OFF) =====================================================


def test_capture_gate_default_off_and_toggles(monkeypatch):
    monkeypatch.delenv("CUA_CAPTURE_CONTENT", raising=False)
    assert _capture_enabled(False) is False                 # default OFF
    assert _capture_enabled(True) is True                   # --capture-content forces ON
    for off in ("", "0", "false", "False", "no", "off"):
        monkeypatch.setenv("CUA_CAPTURE_CONTENT", off)
        assert _capture_enabled(False) is False
    for on in ("1", "true", "yes", "on"):
        monkeypatch.setenv("CUA_CAPTURE_CONTENT", on)
        assert _capture_enabled(False) is True


def test_env_gate_emits_content_json(monkeypatch, tmp_path):
    """`CUA_CAPTURE_CONTENT` ON (no flag) also emits content.json — the env path of the gate."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setenv("CUA_CAPTURE_CONTENT", "1")
    db = tmp_path / "m.db"
    _mini_db(str(db))
    out = tmp_path / "env"
    rc = run_db(db=str(db), run_id="cap", out_dir=out, capture_content=False)  # flag off; env on
    assert rc == 0
    assert (out / "cap.content.json").exists()


# === ContentCapture unit semantics (pure; no run) ================================================


def _claim(cid, text):
    return Claim(id=cid, text=text, evidence_ids=["e1"], reference_ids=["100"], serves_dimension="F1")


def _frag(claims):
    return DraftFragment(stage="s", section="Sec", text=" ".join(c.text for c in claims), claims=claims)


def test_reviser_hedge_diff_records_only_changed_claims():
    prior = Draft(fragments=[_frag([_claim("c1", "X causes Y"), _claim("c2", "stable"), _claim("c3", "gone")])])
    new = Draft(fragments=[_frag([_claim("c1", "X is associated with Y"), _claim("c2", "stable")])])  # c1 hedged, c3 dropped
    cap = ContentCapture()
    cap.record_reviser_hedges(2, prior, new)
    hedges = cap.reviser_hedges[0]["hedges"]
    assert cap.reviser_hedges[0]["round"] == 2
    assert hedges == [{"claim_id": "c1", "before": "X causes Y", "after": "X is associated with Y"}]
    # c2 (unchanged) and c3 (dropped, absent from `after`) are NOT recorded as hedges.


def test_best_of_n_marks_chosen_and_matches_scores_by_identity():
    f0, f1, f2 = _frag([_claim("a", "cand0")]), _frag([_claim("b", "cand1")]), _frag([_claim("c", "cand2")])
    candidates = [f0, f1, f2]
    # ranked deliberately OUT of candidate order — scores must still bind by identity, not position.
    ranked = [ScoredFragment(fragment=f2, score=1.0), ScoredFragment(fragment=f0, score=3.0), ScoredFragment(fragment=f1, score=9.0)]
    cap = ContentCapture()
    cap.record_best_of_n(0, "synthesizer", "F1", candidates, ranked, chosen=f1)
    bon = cap.best_of_n[0]
    assert bon["n"] == 3 and bon["chosen_index"] == 1 and bon["dimension"] == "F1"
    assert [c["score"] for c in bon["candidates"]] == [3.0, 9.0, 1.0]        # f0,f1,f2 — bound by identity
    assert [c["chosen"] for c in bon["candidates"]] == [False, True, False]
    assert "candidate 1 (score=9.0)" in bon["rationale"]                     # winner + its score


def test_empty_capture_to_dict_has_all_keys():
    d = ContentCapture().to_dict()
    assert set(d) == {"capture", "best_of_n", "rounds", "reviser_hedges", "critique"}
    assert d["best_of_n"] == [] and d["rounds"] == [] and d["reviser_hedges"] == [] and d["critique"] == []
