"""test_review.py — the review-report pytest suite (part C) [tester, builder 3].

Implements: test_review_contract.md part C done-criteria — (1) competitiveness gap reported per factor
            on MATCHED pairs (blinded); (2) the ReviewReport covers obligations + overclaim + citation +
            calibration + go/no-go; (3) REVIEW-ONLY — never edits the proposal (Boundaries). Plus: the
            calibration summary is filled from `Audit.calibration` via `fill_calibration`, and the
            report is against the LIVE Critic state (base-7; dev-5 deferred). Decisions:
            2026-06-02-eval-methodology.md, 2026-06-02-critic-range-retune.md.
Owner: S8 (builder 3, terminal). Offline, deterministic — no network, no LLM (CONVENTIONS rule 2: each
       test cites the part-C done-criterion it covers).
"""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from competitiveness import competitiveness_stratified
from review import ReviewReport, review, review_all


@pytest.fixture(scope="module")
def reviewed():
    """Run the full part-C review once (offline, deterministic) and share it across the suite."""
    return review_all()


# === done-criterion 2 — the ReviewReport covers every required section ==========================


def test_review_report_covers_all_required_sections(reviewed):
    """part C: a ReviewReport carries which obligations failed + overclaim list + citation issues +
    calibration summary + a go/no-go."""
    reports, _summary = reviewed
    assert len(reports) == 5
    for r in reports:
        assert isinstance(r, ReviewReport)
        assert r.decision in {"go", "no-go"}  # go/no-go
        assert r.rationale  # …and why
        assert set(r.invariants) == {"inv-1", "inv-2", "inv-3", "all_passed"}
        assert set(r.citation_issues) == {"all_in_source_set", "orphan_ids", "n_references"}  # citation
        assert set(r.calibration_summary) >= {"mae", "rank_corr", "critic_state"}  # calibration summary
        assert isinstance(r.overclaims, list)  # overclaim list
        assert isinstance(r.unmet_obligations, list)  # which obligations failed/unmet
        assert r.to_text()  # human-readable


def test_build_decision_go_all_five_resisted(reviewed):
    """part C / S6: the resisted final proposals pass all three hard invariants → GO on all 5; the
    build-level decision is GO."""
    reports, summary = reviewed
    assert summary["build_decision"] == "go"
    assert all(r.decision == "go" for r in reports)
    assert all(r.invariants["all_passed"] for r in reports)
    # the 3 negatives resisted (revised to round 1); clean/thin passed at round 0
    rounds = {r.proposal_title: r.revision_round for r in reports}
    assert sum(1 for v in rounds.values() if v == 1) == 3
    assert sum(1 for v in rounds.values() if v == 0) == 2


def test_calibration_summary_filled_via_fill_calibration(reviewed):
    """part C / dispatch: the calibration summary is filled from `Audit.calibration.{mae,rank_corr}`
    via `fill_calibration` (the agent leaves them None; the eval — part B — fills them)."""
    reports, _summary = reviewed
    cal = reports[0].calibration_summary
    assert cal["mae"] == {"F1": 1.0, "F2": pytest.approx(0.6667, abs=1e-3)}
    assert cal["rank_corr"]["F1"] == pytest.approx(1.0)
    assert "base-7" in cal["critic_state"]  # reported against the LIVE Critic state (dev-5 deferred)


# === done-criterion 3 — review-only, never edits the proposal ===================================


def test_review_never_edits_the_proposal():
    """part C / Boundaries: review reads the Proposal/Audit and mutates NOTHING. Verified by a deep
    snapshot before/after; `fill_calibration` returns a copy, so `Audit.calibration` is untouched too."""
    from cua.nih.run import _build_orchestrator, RUN_CONFIG
    from cua.nih.task import build_task
    from testdata import all_fixtures
    from invariants import run_invariants
    from eval_report import build_eval_report
    from critic_calibration import CalibrationResult

    fx = next(iter(all_fixtures()))
    proposal, trace, audit = _build_orchestrator().run(build_task(fx), RUN_CONFIG)
    eval_report = build_eval_report()
    cal_result = CalibrationResult.from_dict(eval_report.calibration)

    before_proposal = copy.deepcopy(proposal)
    before_cal = copy.deepcopy(audit.calibration)

    review(proposal, trace, audit, run_invariants(audit),
           calibration_result=cal_result, competitiveness=eval_report.competitiveness,
           mechanism=getattr(fx.grant_call, "mechanism", ""))

    assert proposal == before_proposal, "review must not edit the proposal (part C Boundaries)"
    assert audit.calibration == before_cal, "review must not mutate the Audit (fill returns a copy)"
    assert audit.calibration.mae is None  # the agent's Audit still carries None (eval fills a copy)


def test_review_no_go_when_a_hard_invariant_fails():
    """part C go/no-go gate: an Audit failing a hard invariant (here inv-1, an injected orphan) yields
    a NO-GO. Uses a read-only modified copy of a real Audit — the live agent never produces this."""
    from cua.nih.run import _build_orchestrator, RUN_CONFIG
    from cua.nih.task import build_task
    from testdata import all_fixtures
    from invariants import run_invariants
    from eval_report import build_eval_report
    from critic_calibration import CalibrationResult

    fx = next(iter(all_fixtures()))
    proposal, trace, audit = _build_orchestrator().run(build_task(fx), RUN_CONFIG)
    bad_gr = replace(audit.grounding_report, all_in_source_set=False, orphan_ids=["SYNTH-FABRICATED"])
    bad_audit = replace(audit, grounding_report=bad_gr)  # copy — original untouched

    eval_report = build_eval_report()
    rep = review(proposal, trace, bad_audit, run_invariants(bad_audit),
                 calibration_result=CalibrationResult.from_dict(eval_report.calibration),
                 competitiveness=eval_report.competitiveness,
                 mechanism=getattr(fx.grant_call, "mechanism", ""))
    assert rep.decision == "no-go"
    assert rep.invariants["inv-1"] is False
    assert rep.citation_issues["orphan_ids"] == ["SYNTH-FABRICATED"]


# === done-criterion 1 — competitiveness gap on matched strata (blinded) =========================


def test_competitiveness_reported_on_matched_strata(reviewed):
    """part C / B4: the competitiveness gap is reported per factor on MATCHED strata (by mechanism),
    blinded. Each stratum is mechanism-consistent with ≥1 item per arm."""
    _reports, summary = reviewed
    strat = competitiveness_stratified()
    mechs = {s.mechanism for s in strat.strata}
    assert mechs == {"R01", "R21"}  # the fixtures' mechanisms, matched
    for s in strat.strata:
        assert set(s.gap) == {"F1", "F2"}
        assert s.n_ai >= 1 and s.n_human >= 1  # a matched stratum has both arms
        for d in ("F1", "F2"):
            assert s.gap[d] == pytest.approx(s.ai_mean[d] - s.human_mean[d], abs=1e-6)
    assert "matched by mechanism" in strat.method
    assert summary["competitiveness_pooled_gap"] is not None


def test_review_surfaces_competitiveness_per_proposal_stratum(reviewed):
    """part C: each ReviewReport carries its proposal's MATCHED-stratum gap (by mechanism) + the pooled
    gap — so a reviewer sees the AI-vs-funded-human bar for that exact mechanism."""
    reports, _summary = reviewed
    for r in reports:
        cs = r.competitiveness_summary
        assert cs["mechanism"] in {"R01", "R21"}
        assert cs["stratum_gap"] is not None and set(cs["stratum_gap"]) == {"F1", "F2"}
        assert set(cs["pooled_gap"]) == {"F1", "F2"}


def test_live_judge_is_gated_offline():
    """B2 / decision §B: the live Sonnet judge is network-gated — selecting it offline raises (the
    suite uses the deterministic surrogate)."""
    with pytest.raises(NotImplementedError):
        competitiveness_stratified(use_live_judge=True)


# === determinism =================================================================================


def test_review_is_deterministic():
    """Offline determinism (S2–S6 posture): the whole review is byte-reproducible."""
    r1, s1 = review_all()
    r2, s2 = review_all()
    assert s1 == s2
    assert [r.decision for r in r1] == [r.decision for r in r2]
    assert [r.to_text() for r in r1] == [r.to_text() for r in r2]
