"""test_eval.py — the eval-harness pytest suite (part B) [tester, builder 3].

Implements: test_review_contract.md part B done-criteria — (B1) reference set stored separately +
            contamination rule provably honored; (B2) blinded judge ≠ Internal Critic (different model +
            prompt), deterministic, scores F1/F2 1–9 + F3 sufficiency, source-blind; (B3) per-factor MAE
            + rank-corr on a held-out set, filling `Audit.calibration.{mae,rank_corr}` (§1.10); (B4)
            competitiveness gap; EvalReport emitted. Plus dev-5: the compression is quantified + the
            joint retune reduces MAE. Decisions: 2026-06-02-eval-methodology.md,
            2026-06-02-critic-range-retune.md, 2026-06-02-critic-calibration-anchors.md.
Owner: S7 (builder 3). Offline, deterministic — no network, no LLM (CONVENTIONS rule 2: each test cites
       the B-criterion / done-criterion it covers).
"""

from __future__ import annotations

import pytest

from blinded_judge import BlindedJudge, JudgeInput, JudgeScore
from competitiveness import competitiveness
from critic_calibration import (
    RETUNE,
    calibrate,
    dev5_quantification,
    fill_calibration,
    projected_calibration,
)
from eval_report import EvalReport, build_eval_report
from reporter_reference import (
    REFERENCE_SET,
    assert_contamination_free,
    contamination_report,
    fetch_reference_set,
    matched_subset,
    writer_exemplar_strings,
)


# === B2 — blinded judge ≠ Internal Critic (different model + prompt), deterministic ==============


def test_blinded_judge_differs_from_critic_model_and_prompt():
    """B2 / done-criterion 1: the judge is a DIFFERENT model + prompt from the Internal Critic, and
    deterministic (temperature 0 on a model that supports it)."""
    from cua.roles import InternalCritic

    judge, critic = BlindedJudge(), InternalCritic()
    assert judge.config.model_id != critic.config.model_id, "judge must use a different model (B2)"
    assert judge.config.system_prompt_template != critic.config.system_prompt_template, (
        "judge must use a different prompt (B2)"
    )
    # deterministic settings: Sonnet judge pins temperature 0.0; Opus Critic uses effort (rejects temp).
    assert judge.config.temperature == 0.0
    assert critic.config.temperature is None and critic.config.effort == "high"


def test_blinded_judge_is_blind_to_source():
    """B2 blinding: the judge's score is INVARIANT to the source label (AI vs human) — it scores
    structure only, never `JudgeInput.source`. This is what 'source identity hidden' means in code."""
    judge = BlindedJudge()
    feats = dict(title="t", has_central_hypothesis=True, has_innovation=True, n_aims=3,
                 n_references=40, n_overclaims=0)
    as_ai = judge.score(JudgeInput(source="AI", **feats))
    as_human = judge.score(JudgeInput(source="human", **feats))
    assert as_ai == as_human, "judge must be blind to source identity (B2)"


def test_blinded_judge_scores_three_factors_in_range():
    """B2: the judge scores F1/F2 on 1–9 and F3 as sufficiency."""
    judge = BlindedJudge()
    js = judge.score(JudgeInput("AI", "t", True, True, 3, 40, 0))
    assert isinstance(js, JudgeScore)
    assert 1 <= js.F1 <= 9 and 1 <= js.F2 <= 9
    assert js.F3 in {"sufficient", "insufficient"}


def test_blinded_judge_score_is_monotone_in_overclaims():
    """B2 sanity: more overclaims ⇒ not-higher judge scores (the judge penalizes over-reach), so it is
    a meaningful independent signal, not a constant."""
    judge = BlindedJudge()
    clean = judge.score(JudgeInput("AI", "t", True, True, 3, 40, 0))
    over = judge.score(JudgeInput("AI", "t", True, True, 3, 40, 2))
    assert over.F1 <= clean.F1 and over.F2 <= clean.F2


# === B3 — Critic calibration (per-factor MAE + rank-corr) on the held-out anchor set =============


def test_critic_calibration_mae_and_rank_corr():
    """B3 / done-criterion 2: per-factor MAE + rank correlation of the Critic vs the blinded judge,
    computed on the held-out gap-5 anchor set. THIS number licenses the Critic as a reward signal."""
    cal = calibrate()
    assert set(cal.mae) == {"F1", "F2"} and set(cal.rank_corr) == {"F1", "F2"}
    assert cal.n == len(cal.anchor_ids) == 3  # the gap-5 seed anchors (held-out)
    # The v1 surrogate compresses the top → MAE is poor at the top while rank ordering holds.
    assert cal.mae["F1"] == pytest.approx(1.0)
    assert cal.mae["F2"] == pytest.approx(0.6667, abs=1e-3)
    assert cal.rank_corr["F1"] == pytest.approx(1.0)
    assert cal.rank_corr["F2"] == pytest.approx(0.866, abs=1e-3)


def test_calibration_is_deterministic():
    """Offline determinism (S2–S6 posture): the calibration is byte-reproducible."""
    assert calibrate().as_dict() == calibrate().as_dict()


def test_fill_audit_calibration_fields():
    """B3 / §1.10 / dispatch 'fill Audit.calibration.{mae,rank_corr}': the agent leaves mae/rank_corr
    None; the eval fills them on a COPY (read-only, outside the loop), preserving internal_scores."""
    from cua.nih.run import _build_orchestrator, RUN_CONFIG
    from cua.nih.task import build_task
    from testdata import all_fixtures

    fx = next(iter(all_fixtures()))
    _proposal, _trace, audit = _build_orchestrator().run(build_task(fx), RUN_CONFIG)
    assert audit.calibration.mae is None and audit.calibration.rank_corr is None  # agent leaves None

    cal = calibrate()
    filled = fill_calibration(audit.calibration, cal)
    assert filled.mae == cal.mae and filled.rank_corr == cal.rank_corr  # eval filled them
    assert filled.internal_scores == audit.calibration.internal_scores  # Critic's own scores preserved
    assert audit.calibration.mae is None  # original untouched (a copy was returned)


# === B1 — reference set stored separately + contamination rule provably honored (HARD) ===========


def test_reference_set_stored_offline_live_path_gated():
    """B1 / done-criterion 3: the reference set is stored separately; the offline fetch returns it
    without network; the live RePORTER path is gated (not wired in v1)."""
    assert fetch_reference_set() == REFERENCE_SET  # offline default, no network
    with pytest.raises(NotImplementedError):
        fetch_reference_set(allow_network=True)  # live path gated (decision §B)


def test_contamination_rule_honored():
    """B1 / done-criterion 3 (HARD Boundaries): RePORTER reference text never reaches an agent input,
    and the writer few-shot exemplars are disjoint from the reference set — else the comparison is
    rigged. Provably honored over ALL fixtures + both writers."""
    rep = contamination_report()
    assert rep["honored"] is True
    assert rep["exemplar_overlap"] == [], "reference set must be disjoint from writer exemplars"
    assert rep["input_leaks"] == [], "no reference text may appear in any agent input"
    assert_contamination_free()  # raises if violated


def test_writer_exemplars_are_structural_not_funded_text():
    """design §5 / contamination rule: the writer exemplars are structural placeholders, disjoint from
    the funded reference set (so nothing funded leaks). Both are 'structural' skeletons."""
    exemplars = writer_exemplar_strings()
    assert exemplars, "the two writer roles carry few-shot exemplars (§2.4)"
    ref_ids = {r.app_id for r in REFERENCE_SET}
    assert not (exemplars & ref_ids)


# === B4 — competitiveness (matched) ==============================================================


def test_matched_subset_by_mechanism_and_domain():
    """B4 matching: the matched human subset shares the AI proposal's mechanism (and, where available,
    a domain term)."""
    sub = matched_subset("R01", "Urolithin A for cognitive decline in Alzheimer's disease")
    assert sub and all(r.activity_code == "R01" for r in sub)
    assert any("alzheimer's disease" in r.domain_terms for r in sub)  # domain matched
    # mechanism is respected: an R21 topic never returns R01 items
    assert all(r.activity_code == "R21" for r in matched_subset("R21", "rheumatoid arthritis flares"))


def test_competitiveness_gap_computed():
    """B4: AI proposals' blinded factor scores vs matched funded human references; the per-factor gap is
    reported (v1 plumbing; S8 expands the rigor)."""
    comp = competitiveness()
    assert set(comp.gap) == {"F1", "F2"}
    assert comp.n_ai == 5 and comp.n_human >= 1
    for d in ("F1", "F2"):
        assert comp.gap[d] == pytest.approx(comp.ai_mean[d] - comp.human_mean[d], abs=1e-6)


# === EvalReport emitted (done-criterion 4) =======================================================


def test_eval_report_emitted():
    """done-criterion 4: an EvalReport { calibration:{mae,rank_corr}, competitiveness:{…}, n } is
    emitted and JSON-serializable."""
    report = build_eval_report()
    assert isinstance(report, EvalReport)
    assert set(report.calibration["mae"]) == {"F1", "F2"}
    assert set(report.calibration["rank_corr"]) == {"F1", "F2"}
    assert "gap" in report.competitiveness
    assert report.contamination["honored"] is True
    assert report.n == 3
    import json

    json.loads(report.to_json())  # round-trips


# === dev-5 — compression quantified + the joint retune reduces MAE ===============================


def test_dev5_compression_quantified():
    """dev-5: the eval quantifies the top-of-range compression — the high anchor's target is 8 but the
    Critic caps it at base 7 (the compression), while rank ordering holds (rank_corr F1 = 1.0)."""
    cal = calibrate()
    hi = cal.anchor_ids.index("anchor-high")
    assert cal.external["F1"][hi] == 8 and cal.internal["F1"][hi] == 7  # capped one short
    assert cal.external["F2"][hi] == 8 and cal.internal["F2"][hi] == 7
    assert cal.rank_corr["F1"] == pytest.approx(1.0)  # ordering already sound — it's a LEVEL gap


def test_dev5_joint_retune_reduces_mae_preserves_rank():
    """dev-5: the proposed joint base/penalty/bar retune (RETUNE) reduces per-factor MAE while keeping
    rank-corr — quantifying the remedy. Projection only; application is relayed to builder 1 + operator."""
    current = calibrate()
    projected = projected_calibration(RETUNE)
    assert projected.mae["F1"] < current.mae["F1"]
    assert projected.mae["F2"] < current.mae["F2"]
    assert projected.mae["F1"] == pytest.approx(0.0)
    assert projected.mae["F2"] == pytest.approx(0.3333, abs=1e-3)
    for d in ("F1", "F2"):  # rank ordering is preserved (it was already sound)
        assert projected.rank_corr[d] == pytest.approx(current.rank_corr[d], abs=1e-3)
    assert RETUNE["base"] == 8 and RETUNE["bar"] == 6  # joint: base and bar move together


def test_dev5_quantification_payload():
    """dev-5: the EvalReport's dev5 payload carries the current MAE, the projected retune, and the
    relay note (application is builder 1 + operator, not the eval)."""
    d = dev5_quantification()
    assert d["current"]["mae"]["F1"] == pytest.approx(1.0)
    assert d["projected_retune"]["mae"]["F1"] == pytest.approx(0.0)
    assert "relayed" in d["finding"].lower() or "builder 1" in d["finding"].lower()
