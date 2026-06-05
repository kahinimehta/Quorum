"""LIVE-5 tests — `InternalCritic` live body (the reward engine) — mirrors LIVE-2/3.

Deterministic + offline: the live LLM call is mocked (`cua.llm.complete` for the score/shape units, or
the lower `cua.llm._call_model` seam for the trace-guard + end-to-end proofs) — no network, no real key
(a dummy `ANTHROPIC_API_KEY` only flips `is_live()`). Asserts: the live branch is inert with `CUA_LIVE`
unset (surrogate is the default); the BLIND guard (raw `Obligation` → AssertionError) fires on the live
path too; a live critique yields a same-shaped `CritiqueReport` (F1/F2/F3 scores, segment_scores,
decision, flagged); the LLM SCORES but the CODE owns the non-fabricable repair directives
(drop-orphan/hedge) + the calibration deductions, so the Reviser still gets trustworthy targets and the
§1.11 loop pass/revises on the live scores; exactly ONE `critic:live` TraceEvent per critic call.

Owner: LIVE-5 (builder 1). Governing: contracts.md §1.5/§1.7/§1.11; design §3/principle 2; decisions
live-bodies-wave / trace-recording-ownership / critic-scoring-rubric.
"""

from __future__ import annotations

import pytest

import cua.llm as llm
from cua.grounding import Grounder
from cua.nih.framework import F1, F2, F3, Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.proposal import Proposal
from cua.nih.run import RUN_CONFIG
from cua.nih.task import NIHGrantTask
from cua.orchestrator import Orchestrator
from cua.roles import BlueprintPlanner, InternalCritic, Reviser
from cua.roles._repair import parse_directives
from cua.roles.aim_architect import _AimExpansion
from cua.roles.critic import _CritiqueOut, _DimensionJudgment, _SegmentJudgment, _live_critique_prompt
from cua.roles.reviser import _RevisedDraft
from cua.roles.synthesizer import _AimStub, _CitedClaim, _F1Argument
from cua.trace import TraceRecorder
from cua.types import (
    Claim,
    Draft,
    DraftFragment,
    EvidenceScores,
    Obligation,
    ObligationPublic,
    SourceSet,
    Status,
)


# --- fixtures -------------------------------------------------------------------------------------


def _corpus() -> SourceSet:
    return SourceSet([
        Paper(id="p1", authors=[], year=2020, title="Microglia in PD", venue="J", resolvable_id="10.1/p1", key_finding="microglial activation tracks progression", real=True),
        Paper(id="p2", authors=[], year=2021, title="GCase trial", venue="J", resolvable_id="NCT2", key_finding="GCase modulation in a phase 2 cohort", real=True),
        Paper(id="p3", authors=[], year=2019, title="Alpha-synuclein", venue="J", resolvable_id="10.1/p3", key_finding="aggregation in dopaminergic neurons", real=True),
    ])


def _claim(cid: str, text: str, refs, dim: str) -> Claim:
    return Claim(id=cid, text=text, evidence_ids=list(refs), reference_ids=list(refs), serves_dimension=dim)


def _draft(*, aim_text="We will examine whether the mechanism alters the outcome.", aim_refs=("p2",)) -> Draft:
    """An F1 fragment (significance/innovation/central, exploratory L1) + one F2 aim fragment. `aim_text`
    / `aim_refs` are knobs: an L4 text makes the aim an overclaim; an off-corpus ref makes it an orphan."""
    sig = _claim("significance", "We will investigate whether microglial activation relates to progression.", ("p1",), F1)
    central = _claim("central-hypothesis", "We will examine whether GCase modulation alters the outcome.", ("p2",), F1)
    innov = _claim("innovation", "A specific departure from symptomatic-only practice.", (), F1)
    f1 = DraftFragment(stage="synthesizer", section="significance_innovation",
                       text=sig.text + " " + innov.text, claims=[sig, central, innov], serves_dimension=F1, provides={})
    aim_claim = _claim("aim-1::hypothesis", aim_text, aim_refs, F2)
    f2 = DraftFragment(stage="aim_architect", section="aims", text=aim_text, segment_id="aim-1",
                       claims=[aim_claim], serves_dimension=F2, provides={"aims": []})
    return Draft(fragments=[f1, f2])


def _grounded(draft: Draft, corpus: SourceSet | None = None):
    return Grounder().ground(draft, corpus or _corpus())[0]


def _obs_public() -> list[ObligationPublic]:
    """Public obligations (no self_score/notes). satisfied_by=[] → no unmet-row penalty; X-1/X-2 are the
    cross-cutting integrity rows `_flagged_obligations` names on orphan/overclaim."""
    return [
        ObligationPublic(id="X-1", dimension=F1, requirement="every reference resolves to the corpus", satisfied_by=[], evidence_ids=[], status=Status.UNSATISFIED),
        ObligationPublic(id="X-2", dimension=F1, requirement="no claim overclaims its evidence", satisfied_by=[], evidence_ids=[], status=Status.UNSATISFIED),
        ObligationPublic(id="F1-1", dimension=F1, requirement="significance is established", satisfied_by=[], evidence_ids=[], status=Status.UNSATISFIED),
        ObligationPublic(id="F2-1", dimension=F2, requirement="approach is rigorous", satisfied_by=[], evidence_ids=[], status=Status.UNSATISFIED),
    ]


def _critique_out(*, f1=7, f2=7, f3=7, decision="pass", segs=None, flagged=None) -> _CritiqueOut:
    return _CritiqueOut(
        f1=_DimensionJudgment(score=f1, justification="significance + innovation are sound"),
        f2=_DimensionJudgment(score=f2, justification="approach is rigorous and feasible"),
        f3=_DimensionJudgment(score=f3, justification="qualified team and environment"),
        segment_scores=segs or [],
        decision=decision,
        flagged_obligation_ids=flagged or [],
    )


def _live(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


# --- offline default: the live branch is inert ----------------------------------------------------


def test_offline_unset_takes_surrogate_not_complete(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)

    def boom(*a, **k):
        raise AssertionError("complete() must not be called when CUA_LIVE is unset")

    monkeypatch.setattr(llm, "complete", boom)
    rec = TraceRecorder()
    report = InternalCritic().critique(_grounded(_draft()), _obs_public(), EvidenceScores(), [], recorder=rec, round=0)
    # surrogate ran: the §1.7 shape holds, F1/F2 scored, no live event recorded by the body
    assert set(report.dimension_scores) >= {F1, F2} and report.decision in ("pass", "revise")
    assert len(rec.trace) == 0


def test_live_inert_without_recorder(monkeypatch):
    # is_live() True but no recorder threaded (e.g. the calibration_anchors caller) → surrogate, no complete()
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no recorder → surrogate")))
    report = InternalCritic().critique(_grounded(_draft()), _obs_public(), EvidenceScores(), [])
    assert set(report.dimension_scores) >= {F1, F2}


# --- BLIND guard fires on the live path too (principle 2) -----------------------------------------


def test_blind_guard_fires_on_live_path(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _critique_out())
    # a RAW Obligation (carries self_score/notes) must trip the blind assert before any branch
    raw = [Obligation(id="F1-1", dimension=F1, requirement="significance", self_score=8, notes="writer note")]
    with pytest.raises(AssertionError):
        InternalCritic().critique(_grounded(_draft()), raw, EvidenceScores(), [], recorder=TraceRecorder(), round=0)


# --- live critique: same-shaped report, LLM scores flow through -----------------------------------


def test_live_clean_report_carries_llm_scores(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _critique_out(f1=8, f2=6, f3=9, decision="pass"))
    report = InternalCritic().critique(_grounded(_draft()), _obs_public(), EvidenceScores(), [], recorder=TraceRecorder(), round=0)

    # F1/F2/F3 all surfaced; clean draft → no code penalty → the LLM's base is the score
    assert report.dimension_scores[F1].score == 8
    assert report.dimension_scores[F2].score == 6
    assert report.dimension_scores[F3].score == 9          # F3 surfaced (not gated by §1.11)
    assert report.decision == "pass"                       # clean + LLM said pass
    assert report.flagged_obligations == []                # nothing flagged on a clean draft
    # no code-owned repair directives when there is nothing to repair
    hedges, drops = parse_directives(s for ds in report.dimension_scores.values() for s in ds.spans)
    assert hedges == {} and drops == []


def test_live_segment_scores_use_llm_base(monkeypatch):
    _live(monkeypatch)
    segs = [_SegmentJudgment(aim_id="aim-1", score=5, justification="aim ok")]
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _critique_out(segs=segs))
    report = InternalCritic().critique(_grounded(_draft()), _obs_public(), EvidenceScores(), [], recorder=TraceRecorder(), round=0)
    assert report.segment_scores["aim-1"].dimension == "F2"
    assert report.segment_scores["aim-1"].score == 5       # the LLM's per-aim base (clean → no penalty)


# --- LLM scores; CODE owns the repair targets + enforces the calibration floor --------------------


def test_live_overclaim_code_hedges_and_penalizes(monkeypatch):
    """An L4 aim over unscored (→minimal/L1) evidence is an overclaim. The LLM scores quality; the CODE
    detects the overclaim, emits the hedge directive (non-fabricable), drops the dimension's score below
    the bar, and forces revise — even though the LLM said pass with a high score."""
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _critique_out(f1=8, f2=8, decision="pass"))
    draft = _draft(aim_text="The targeted mechanism causes the clinical outcome.", aim_refs=("p2",))  # L4
    report = InternalCritic().critique(_grounded(draft), _obs_public(), EvidenceScores(), [], recorder=TraceRecorder(), round=0)

    # code-owned hedge directive for the overclaiming F2 claim, to its permitted rung (L1)
    hedges, drops = parse_directives(s for ds in report.dimension_scores.values() for s in ds.spans)
    assert hedges == {"aim-1::hypothesis": "L1"} and drops == []
    # a FLAGGED dimension takes the surrogate-calibrated DETERMINISTIC score (7 − 3 = 4, sub-bar → the LLM's
    # base 8 can't inflate the overclaim past the gate); the CLEAN F1 keeps the LLM base 8
    assert report.dimension_scores[F2].score == 4 and report.dimension_scores[F1].score == 8
    assert report.decision == "revise"                     # integrity issue → code forces revise
    assert "X-2" in report.flagged_obligations             # the no-overclaim row


def test_live_orphan_code_drops_and_reviser_scrubs(monkeypatch):
    """A fabricated citation is an orphan. The LLM scores; the CODE emits the drop-orphan directive
    (from the GroundingReport, non-fabricable), and the (surrogate) Reviser scrubs it — the repair target
    survives the live critic untouched."""
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _critique_out(f1=7, f2=7, decision="pass"))
    draft = _draft(aim_refs=("p2", "FAKE-9"))               # FAKE-9 ∉ corpus → orphan
    grounded = _grounded(draft)
    assert "FAKE-9" in grounded.grounding_report.orphan_ids
    report = InternalCritic().critique(grounded, _obs_public(), EvidenceScores(), [], recorder=TraceRecorder(), round=0)

    hedges, drops = parse_directives(s for ds in report.dimension_scores.values() for s in ds.spans)
    assert drops == ["FAKE-9"] and hedges == {}
    assert report.decision == "revise" and "X-1" in report.flagged_obligations
    # the Reviser (consumes the live critique) scrubs the fabrication from the claim
    revised = Reviser().revise(draft, report, [], report.flagged_obligations)
    assert all("FAKE-9" not in c.reference_ids for f in revised.fragments for c in f.claims)


def test_live_flagged_unions_llm_ids(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _critique_out(flagged=["F2-1", "BOGUS-99"]))
    report = InternalCritic().critique(_grounded(_draft()), _obs_public(), EvidenceScores(), [], recorder=TraceRecorder(), round=0)
    # the LLM's valid flagged id is unioned in; an id not in the public obligations is dropped
    assert "F2-1" in report.flagged_obligations and "BOGUS-99" not in report.flagged_obligations


# --- prompt is BLIND (no self_score/notes leak) ---------------------------------------------------


def test_live_prompt_is_blind_and_grounded():
    prompt = _live_critique_prompt(_grounded(_draft()), _obs_public(), EvidenceScores(), [])
    assert "self_score" not in prompt and "notes" not in prompt
    assert "significance" in prompt and "aim-1" in prompt           # the grounded draft is serialized
    assert "permitted<=" in prompt                                  # the code-resolved grade context


# --- trace-guard: exactly one critic:live event per critic call -----------------------------------


def _critique_response(out: _CritiqueOut):
    tool_name = llm._tool_name(_CritiqueOut)

    class _Block:
        type = "tool_use"
        name = tool_name
        input = out.model_dump()

    class _Usage:
        input_tokens = 2200
        output_tokens = 300

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def test_live_records_exactly_one_critic_event(monkeypatch):
    # real complete() runs (records its own event); only the network seam is mocked.
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", lambda request: _critique_response(_critique_out()))
    rec = TraceRecorder()
    InternalCritic().critique(_grounded(_draft()), _obs_public(), EvidenceScores(), [], recorder=rec, round=2)

    assert len(rec.trace) == 1
    ev = rec.trace[0]
    assert ev.role == "critic" and ev.output_ref == "critic:live"
    assert ev.model == "claude-opus-4-8" and ev.sampling == "effort=high"
    assert ev.round == 2 and ev.tokens == 2500             # real usage summed by complete()


# --- end-to-end (live Critic through the real Orchestrator) ---------------------------------------


def _synth_payload() -> dict:
    return _F1Argument(
        gap="A specific barrier remains unresolved.",
        significance=_CitedClaim(text="We will investigate whether microglial activation affects progression.", cited_corpus_ids=["p1"]),
        central_hypothesis=_CitedClaim(text="We will examine whether GCase modulation alters the outcome.", cited_corpus_ids=["p2"]),
        innovation=_CitedClaim(text="A specific departure from symptomatic-only practice.", cited_corpus_ids=[]),
        aims=[_AimStub(title="Aim 1: microglia", cited_corpus_ids=["p1"]), _AimStub(title="Aim 2: GCase", cited_corpus_ids=["p2"])],
    ).model_dump()


def _aim_payload() -> dict:
    return _AimExpansion(
        hypothesis="We will examine whether the targeted mechanism alters the clinical outcome.",
        rationale="Grounded in the cited corpus key findings.",
        approach="Methods and design specified to a rigor-judgable level.",
        expected_outcomes="Outcomes tied directly to the hypothesis.",
        pitfalls_alternatives="Explicit pitfalls and alternative strategies.",
        citation_ids=["p1"],
    ).model_dump()


def _e2e_call_model(*, f1=7, f2=7):
    """Schema-aware `_call_model`: all three live roles. The critic's score knob lets a test push the
    draft below the §1.11 bar to prove the loop revises on the LIVE scores."""

    def _call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_F1Argument):
            payload = _synth_payload()
        elif tool == llm._tool_name(_CritiqueOut):
            payload = _critique_out(f1=f1, f2=f2, decision="pass" if (f1 >= 5 and f2 >= 5) else "revise").model_dump()
        elif tool == llm._tool_name(_RevisedDraft):
            payload = {"hedged_claims": []}  # clean draft (low score, not an overclaim) → nothing to hedge
        else:
            payload = _aim_payload()

        class _Block:
            type = "tool_use"
            name = tool
            input = payload

        class _Usage:
            input_tokens = 900
            output_tokens = 300

        class _Resp:
            content = [_Block()]
            stop_reason = "tool_use"
            usage = _Usage()

        return _Resp()

    return _call


def _orch() -> Orchestrator:
    return Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)


def test_end_to_end_live_critic_passes_clean(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _e2e_call_model(f1=7, f2=7))
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    artifact, trace, audit = _orch().run(task, RUN_CONFIG)

    assert isinstance(artifact, Proposal)                  # §2.1 envelope validated at assembly
    assert audit.grounding_report.all_in_source_set        # inv-1
    # a clean draft + fundable LIVE scores → the §1.11 loop PASSES at round 0 → exactly one critic:live event
    critic_live = [e for e in trace if e.role == "critic" and e.output_ref == "critic:live"]
    assert len(critic_live) == 1
    assert [e for e in trace if e.output_ref == "decision@r0" and e.decision == "pass"]
    # F1/F2/F3 internal scores surfaced into the Audit calibration
    assert {"F1", "F2", "F3"} <= set(audit.calibration.internal_scores)


def test_end_to_end_live_low_score_revises(monkeypatch):
    # the LIVE critic scores F1 below the bar on an otherwise-clean draft → the §1.11 loop REVISES each
    # round (no repair directive to apply → re-grounds the same draft), proving the loop reads live scores.
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _e2e_call_model(f1=3, f2=7))
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    artifact, trace, audit = _orch().run(task, RUN_CONFIG)            # RUN_CONFIG: max_rounds=3, F1/F2≥5

    assert isinstance(artifact, Proposal)                  # still assembles at the round cap
    critic_live = [e for e in trace if e.role == "critic" and e.output_ref == "critic:live"]
    assert len(critic_live) == RUN_CONFIG.max_rounds        # one critic:live per round (trace-guard), all revised
    assert [e for e in trace if e.output_ref == f"decision@r{RUN_CONFIG.max_rounds - 1}" and e.decision == "revise"]
    assert audit.calibration.internal_scores["F1"] == 3     # the live score drove the decision
