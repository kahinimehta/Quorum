"""test_calibration_live.py — CALIB-LIVE: blinded-judge proposal scoring + the calibration runner.

`build/live/CALIB-LIVE_relay.md`: the blinded judge gains a live Sonnet path that scores a REAL proposal's
TEXT (gated by CUA_LIVE+key; surrogate default offline), and `run_calibration.calibrate_runs` scores the
existing drafts to populate the Critic's calibration (MAE + Spearman vs an INDEPENDENT judge). These tests
run OFFLINE (surrogate) — deterministic + byte-identical; the live judge is dead offline. The load-bearing
property checked here: the judge is handed ONLY the proposal, never the Audit / Critic `internal_scores`.

Owner: CALIB-LIVE (builder 3). No network, no key (CUA_LIVE unset → surrogate).
"""

from __future__ import annotations

import json

import pytest

from blinded_judge import BlindedJudge, JudgeScore, _judge_input_from_proposal, _render_proposal
from run_calibration import _parse_n_rounds, calibrate_runs


# === fixtures (minimal proposal/audit shaped like outputs/<run>.{proposal,audit}.json) ===========


def _proposal(title="P", *, hyp=True, innovation=True, n_aims=3, n_refs=30) -> dict:
    return {
        "project_title": title,
        "central_hypothesis": "we hypothesize X" if hyp else "",
        "sections": [
            {"name": "significance", "serves_dimension": "F1", "text": "significance text"},
            {"name": "innovation", "serves_dimension": "F1", "text": "innovation text" if innovation else ""},
        ],
        "aims": [
            {"id": f"aim-{i}", "hypothesis": f"hyp {i}", "rationale": "r", "approach": "a",
             "expected_outcomes": "e", "pitfalls_alternatives": "p", "citation_ids": ["literature:1"]}
            for i in range(1, n_aims + 1)
        ],
        "references": [{"id": f"literature:{i}", "title": f"ref {i}"} for i in range(n_refs)],
        "revision_round": 1,
    }


def _audit(f1, f2, f3, *, n_overclaims=0) -> dict:
    return {
        "calibration": {"internal_scores": {"F1": f1, "F2": f2, "F3": f3},
                        "external_scores": None, "mae": None, "rank_corr": None},
        "overclaim_check": [{"claim": f"bad{i}", "ok": False} for i in range(n_overclaims)]
                           + [{"claim": "good", "ok": True}],
    }


def _write(tmp, rid, proposal, audit):
    (tmp / f"{rid}.proposal.json").write_text(json.dumps(proposal), encoding="utf-8")
    (tmp / f"{rid}.audit.json").write_text(json.dumps(audit), encoding="utf-8")


def _three_run_fixture(tmp):
    # external (surrogate) F1=[8,6,5] F2=[7,6,4]; internal F1=[7,7,4] F2=[5,4,5]
    _write(tmp, "sw_n1_r3", _proposal("A", innovation=True, n_refs=30), _audit(7, 5, 7))
    _write(tmp, "sw_n3_r3", _proposal("B", innovation=False, n_refs=10), _audit(7, 4, 6))
    _write(tmp, "sw_n5_r3", _proposal("C", innovation=True, n_refs=30, n_aims=3), _audit(4, 5, 6, n_overclaims=1))


# === the runner: shape + the calibration math ====================================================


def test_calibrate_runs_shape_and_metrics(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)  # surrogate (offline)
    _three_run_fixture(tmp_path)
    report = calibrate_runs(["sw_n1_r3", "sw_n3_r3", "sw_n5_r3"], outputs_dir=tmp_path)

    assert report["judge"] == "v1-surrogate" and report["model"] == "claude-sonnet-4-6"
    assert "blind" in report["independence"].lower()
    # per-run {internal, external}
    r = report["runs"]["sw_n1_r3"]
    assert r["internal"] == {"F1": 7, "F2": 5, "F3": 7}
    assert r["external"] == {"F1": 8, "F2": 7, "F3": "sufficient"} and r["n_overclaims"] == 0
    assert (r["n"], r["rounds"]) == (1, 3)
    # aggregate MAE + Spearman over F1/F2 (locks the surrogate rubric + the metric)
    agg = report["aggregate"]
    assert agg["n"] == 3
    assert agg["mae"] == {"F1": 1.0, "F2": pytest.approx(1.6667, abs=1e-4)}
    assert set(agg["rank_corr"]) == {"F1", "F2"} and all(-1.0 <= v <= 1.0 for v in agg["rank_corr"].values())
    # compute-curve axes
    assert [row["n"] for row in report["by_axis"]["n_axis"]] == [1, 3, 5]
    assert [row["rounds"] for row in report["by_axis"]["rounds_axis"]] == [3]


def test_calibrate_runs_is_deterministic(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    _three_run_fixture(tmp_path)
    a = calibrate_runs(["sw_n1_r3", "sw_n3_r3", "sw_n5_r3"], outputs_dir=tmp_path)
    b = calibrate_runs(["sw_n1_r3", "sw_n3_r3", "sw_n5_r3"], outputs_dir=tmp_path)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_full3_parse_and_missing_run(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    _write(tmp_path, "full3", _proposal("full"), _audit(7, 4, 6))
    report = calibrate_runs(["full3", "missing_run"], outputs_dir=tmp_path)
    assert (report["runs"]["full3"]["n"], report["runs"]["full3"]["rounds"]) == (None, None)
    assert report["runs"]["missing_run"] == {"error": "missing proposal/audit"}
    assert report["aggregate"]["n"] == 1  # only full3 contributed


def test_parse_n_rounds():
    assert _parse_n_rounds("sw_n5_r3") == (5, 3)
    assert _parse_n_rounds("sw_n3_r12") == (3, 12)
    assert _parse_n_rounds("full3") == (None, None)


# === INDEPENDENCE (load-bearing): the judge is handed ONLY the proposal ==========================


def test_runner_passes_only_the_proposal_to_the_judge(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    _three_run_fixture(tmp_path)

    seen: list[dict] = []

    class _SpyJudge:
        config = BlindedJudge.config
        def score_proposal(self, proposal, n_overclaims=0, *, recorder=None):
            seen.append(proposal)
            return JudgeScore(F1=5, F2=5, F3="sufficient")

    calibrate_runs(["sw_n1_r3", "sw_n3_r3", "sw_n5_r3"], outputs_dir=tmp_path, judge=_SpyJudge())
    assert len(seen) == 3
    for p in seen:
        # each is a PROPOSAL (has the proposal fields) and NOT an Audit (no Critic scores)
        assert "project_title" in p and "aims" in p
        assert "calibration" not in p and "internal_scores" not in p and "overclaim_check" not in p
        assert "internal_scores" not in json.dumps(p)  # nothing Critic-derived anywhere in what the judge saw


def test_render_proposal_is_blind_to_internal_scores():
    # even if a proposal dict carried a bogus internal score, the renderer reads only whitelisted fields
    p = _proposal("Blind")
    p["calibration"] = {"internal_scores": {"F1": 9, "F2": 9}}  # bogus injected field
    text = _render_proposal(p)
    assert "Blind" in text and "aim-1" in text and "REFERENCES" in text
    assert "internal_scores" not in text and "9" not in text.split("REFERENCES")[0]  # no Critic score leaked


# === score_proposal surrogate: range, F3 sufficiency, monotone, deterministic ====================


def test_score_proposal_surrogate_properties(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    judge = BlindedJudge()
    clean = judge.score_proposal(_proposal("X"), n_overclaims=0)
    noisy = judge.score_proposal(_proposal("X"), n_overclaims=2)
    assert 1 <= clean.F1 <= 9 and 1 <= clean.F2 <= 9
    assert clean.F3 in {"sufficient", "insufficient"}
    assert noisy.F1 < clean.F1 and noisy.F2 < clean.F2          # monotone-decreasing in overclaims
    assert judge.score_proposal(_proposal("X")) == judge.score_proposal(_proposal("X"))  # deterministic
    # the surrogate routes through the SAME positive-merit rubric as competitiveness (independence basis)
    ji = _judge_input_from_proposal(_proposal("X"), 0)
    assert judge.score_proposal(_proposal("X"), 0) == judge.score(ji)


# === the LIVE path (mocked seam — no network/key): parses _JudgeOut + stays blind ================


def test_live_judge_scores_proposal_text_and_is_blind(monkeypatch):
    """With is_live() (dummy key) + the network seam mocked, score_proposal takes the LIVE branch: real
    complete() extracts `_JudgeOut` → JudgeScore, and the assembled prompt carries ONLY the proposal text
    (title/aims) — never the Critic `internal_scores` (blindness holds on the live path too)."""
    from cua import llm
    from blinded_judge import _JudgeOut

    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    captured = {}

    class _Blk:
        type = "tool_use"
        name = llm._tool_name(_JudgeOut)
        input = {"F1": 8, "F2": 7, "F3": "insufficient", "justification": "live judge"}

    class _U:
        input_tokens, output_tokens = (10, 20)

    class _R:
        content = [_Blk()]
        stop_reason = "tool_use"
        usage = _U()

    def _fake_call(request):
        captured["request"] = request
        return _R()

    monkeypatch.setattr(llm, "_call_model", _fake_call)

    js = BlindedJudge().score_proposal(_proposal("LiveTitle"))
    assert (js.F1, js.F2, js.F3) == (8, 7, "insufficient")     # live branch taken; _JudgeOut → JudgeScore
    blob = json.dumps(captured["request"])
    assert "LiveTitle" in blob and "aim-1" in blob             # the proposal text reached the model
    assert "internal_scores" not in blob and "calibration" not in blob  # …but no Critic score did (blind)
