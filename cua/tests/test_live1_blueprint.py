"""LIVE-1 tests — `BlueprintPlanner` live body (the Conditioner) — the LAST designed LLM role.

Deterministic + offline: the live LLM call is mocked (`cua.llm.complete` for the compile units, or the
lower `cua.llm._call_model` seam for the trace-guard + end-to-end proofs) — no network, no real key.
Asserts: the live branch is inert with `CUA_LIVE` unset (surrogate is the default); a live `compile`
TOPIC-SPECIALIZES each obligation's requirement PROSE while the CODE preserves every structural field
(id / dimension / satisfied_by / status / the F2-x/aim-k id format) — so inv-2's id-bound ledger marking
is untouched and the pipeline runs end-to-end inv-1/2/3-clean; one `blueprint:live` event per compile.

Owner: LIVE-1 (builder 1). Governing: contracts.md §1.2/§1.5; design §3/principle 1; decisions
live-bodies-wave / trace-recording-ownership / obligation-specialization.
"""

from __future__ import annotations

import cua.llm as llm
from cua.nih.framework import F1, F2, F3, Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.obligations import compile_obligations, mark_ledger, planned_aim_ids
from cua.nih.proposal import Proposal
from cua.nih.run import RUN_CONFIG
from cua.nih.task import NIHGrantTask
from cua.orchestrator import Orchestrator
from cua.roles import BlueprintPlanner, InternalCritic, Reviser, SelectionScorer
from cua.roles.aim_architect import _AimExpansion
from cua.roles.blueprint import _blueprint_prompt, _ObligationSet, _SpecializedObligation
from cua.roles.critic import _CritiqueOut
from cua.roles.reviser import _RevisedDraft
from cua.roles.synthesizer import _AimStub, _CitedClaim, _F1Argument
from cua.trace import TraceRecorder
from cua.types import Budget, EvidenceScores, Obligation, SourceSet, Status


# --- fixtures -------------------------------------------------------------------------------------


def _corpus() -> SourceSet:
    return SourceSet([
        Paper(id="p1", authors=[], year=2020, title="Microglia in PD", venue="J", resolvable_id="10.1/p1", key_finding="microglial activation tracks progression", real=True),
        Paper(id="p2", authors=[], year=2021, title="GCase trial", venue="J", resolvable_id="NCT2", key_finding="GCase modulation in a phase 2 cohort", real=True),
    ])


class _T:
    grant_call = default_grant_call()


def _task() -> NIHGrantTask:
    return NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())


def _live(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


def _specialized_set(obligations) -> _ObligationSet:
    """A valid `_ObligationSet` echoing every id with a concrete, topic-specialized requirement."""
    return _ObligationSet(obligations=[
        _SpecializedObligation(id=o.id, dimension=o.dimension, requirement=f"[PD-specialized] {o.requirement}")
        for o in obligations
    ])


# --- offline default: the live branch is inert ----------------------------------------------------


def test_offline_unset_takes_surrogate_not_complete(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no complete() offline")))
    obligations, budget = BlueprintPlanner().compile(_task(), recorder=TraceRecorder(), round=0)
    # surrogate ran: the templated set (same ids/dimensions as compile_obligations) + a Budget
    assert [o.id for o in obligations] == [o.id for o in compile_obligations(_task())]
    assert isinstance(budget, Budget)


def test_live_inert_without_recorder(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no recorder → surrogate")))
    obligations, _b = BlueprintPlanner().compile(_task())     # no recorder → surrogate
    assert obligations


# --- live compile: specialize the PROSE, preserve the STRUCTURE -----------------------------------


def test_live_specializes_requirements_preserving_structure(monkeypatch):
    _live(monkeypatch)
    task = _task()
    template = compile_obligations(task)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _specialized_set(template))
    obligations, budget = BlueprintPlanner().compile(task, recorder=TraceRecorder(), round=0)

    # STRUCTURE preserved exactly (ids / dimensions / satisfied_by / status / the per-aim id format)
    assert [o.id for o in obligations] == [o.id for o in template]
    assert [o.dimension for o in obligations] == [o.dimension for o in template]
    assert [o.satisfied_by for o in obligations] == [o.satisfied_by for o in template]
    assert all(o.status == Status.UNSATISFIED for o in obligations)
    # PROSE specialized — every requirement carries the live topic specialization
    assert all(o.requirement.startswith("[PD-specialized] ") for o in obligations)
    # F1/F2/F3 dimensions all present (the rubric structure is intact)
    assert {o.dimension for o in obligations} >= {F1, F2, F3}
    assert isinstance(budget, Budget)


def test_live_keeps_templated_requirement_when_model_omits_an_id(monkeypatch):
    _live(monkeypatch)
    task = _task()
    template = compile_obligations(task)
    # the model returns only ONE row → every other obligation keeps its templated requirement (no blanks)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _ObligationSet(
        obligations=[_SpecializedObligation(id="F1-1", dimension=F1, requirement="A concrete PD significance predicate with >=1 citation.")]))
    obligations, _b = BlueprintPlanner().compile(task, recorder=TraceRecorder(), round=0)

    by_id = {o.id: o for o in obligations}
    tmpl = {o.id: o for o in template}
    assert by_id["F1-1"].requirement == "A concrete PD significance predicate with >=1 citation."
    assert all(by_id[i].requirement == tmpl[i].requirement for i in tmpl if i != "F1-1")  # others untouched
    assert all(o.requirement for o in obligations)            # never blank


def test_live_ignores_model_attempt_to_restructure(monkeypatch):
    """The model can only specialize requirement prose — an unknown id it invents is ignored, and it
    cannot drop/renumber the code-owned set (so inv-2's id binding is safe)."""
    _live(monkeypatch)
    task = _task()
    template = compile_obligations(task)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _ObligationSet(obligations=[
        _SpecializedObligation(id="F1-1", dimension=F1, requirement="[PD] significance with >=1 citation."),
        _SpecializedObligation(id="BOGUS-99", dimension="Z", requirement="invented row the model tried to add"),
    ]))
    obligations, _b = BlueprintPlanner().compile(task, recorder=TraceRecorder(), round=0)
    assert [o.id for o in obligations] == [o.id for o in template]   # exactly the code-owned set
    assert "BOGUS-99" not in {o.id for o in obligations}


def test_live_obligations_stay_inv2_checkable(monkeypatch):
    """inv-2 binds by id/dimension/satisfied_by, NOT the requirement text — so specialized requirements
    leave the ledger marking fully checkable (the per-aim rows still bind to their aim ids)."""
    _live(monkeypatch)
    task = _task()
    template = compile_obligations(task)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _specialized_set(template))
    obligations, _b = BlueprintPlanner().compile(task, recorder=TraceRecorder(), round=0)
    # the Synthesizer still recovers the planned aim ids from the id format (principle 1)
    assert planned_aim_ids(obligations) == planned_aim_ids(template)
    assert planned_aim_ids(obligations)                       # non-empty (R01 → 3 aims)


def test_blueprint_prompt_enforces_concreteness():
    prompt = _blueprint_prompt("Parkinson's disease", compile_obligations(_task()))
    assert "Parkinson's disease" in prompt
    assert "concrete" in prompt.lower() and "checkable" in prompt.lower()
    assert "do not add, remove, renumber" in prompt.lower()   # the structure is fixed
    assert "F1-1" in prompt and "F2-1/aim-1" in prompt        # the fixed rubric skeleton is shown


# --- trace-guard: exactly one blueprint:live event per compile ------------------------------------


def _blueprint_response(obligations):
    out = _specialized_set(obligations)
    tool_name = llm._tool_name(_ObligationSet)

    class _Block:
        type = "tool_use"
        name = tool_name
        input = out.model_dump()

    class _Usage:
        input_tokens = 1200
        output_tokens = 600

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def test_live_records_exactly_one_blueprint_event(monkeypatch):
    _live(monkeypatch)
    task = _task()
    template = compile_obligations(task)
    monkeypatch.setattr(llm, "_call_model", lambda request: _blueprint_response(template))
    rec = TraceRecorder()
    BlueprintPlanner().compile(task, recorder=rec, round=0)

    assert len(rec.trace) == 1
    ev = rec.trace[0]
    assert ev.role == "blueprint" and ev.output_ref == "blueprint:live"
    assert ev.model == "claude-haiku-4-5-20251001" and ev.sampling == "temp=0.1"
    assert ev.tokens == 1800


# --- end-to-end (every designed LLM role live, through the real Orchestrator) ---------------------


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


def _all_live_call_model(request):
    """Every designed LLM role live: Blueprint (`_ObligationSet`), Synthesizer (`_F1Argument`), Selection
    Scorer (`_RankingOut`), AimArchitect (`_AimExpansion`), Critic (`_CritiqueOut`), Reviser
    (`_RevisedDraft`)."""
    from cua.roles.selection_scorer import _RankingOut

    tool = request["tool_choice"]["name"]
    if tool == llm._tool_name(_ObligationSet):
        # specialize whatever rows the prompt carried (echo a concrete requirement per id)
        payload = {"obligations": [{"id": "F1-1", "dimension": "F1", "requirement": "PD significance names the barrier with >=1 citation."}]}
    elif tool == llm._tool_name(_F1Argument):
        payload = _synth_payload()
    elif tool == llm._tool_name(_RankingOut):
        payload = {"rankings": [{"index": i, "score": 3.0 - i} for i in range(3)]}
    elif tool == llm._tool_name(_CritiqueOut):
        payload = {"f1": {"score": 7, "justification": "j"}, "f2": {"score": 7, "justification": "j"},
                   "f3": {"score": 7, "justification": "j"}, "segment_scores": [], "decision": "pass", "flagged_obligation_ids": []}
    elif tool == llm._tool_name(_RevisedDraft):
        payload = {"hedged_claims": []}
    else:
        payload = _aim_payload()

    class _Block:
        type = "tool_use"
        name = tool
        input = payload

    class _Usage:
        input_tokens = 500
        output_tokens = 150

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def test_end_to_end_full_pipeline_live(monkeypatch):
    """The full designed pipeline live (Blueprint + Synthesizer + Selection Scorer + AimArchitect + Critic
    + Reviser): a valid Proposal, inv-1/2/3-clean, with one blueprint:live event."""
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _all_live_call_model)
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=SelectionScorer())
    artifact, trace, audit = orch.run(_task(), RUN_CONFIG)

    assert isinstance(artifact, Proposal)                                    # §2.1 envelope validated
    assert audit.grounding_report.all_in_source_set                          # inv-1
    sat = [o for o in audit.obligation_ledger if o.status == Status.SATISFIED]
    assert sat and all(o.evidence_ids for o in sat)                          # inv-2 (still checkable on live obligations)
    assert all(r.ok for r in audit.overclaim_check)                          # inv-3
    # the Blueprint went live (one blueprint:live event), and no surrogate "conditioner" echo
    assert len([e for e in trace if e.role == "blueprint" and e.output_ref == "blueprint:live"]) == 1
    assert not [e for e in trace if e.role == "conditioner"]
