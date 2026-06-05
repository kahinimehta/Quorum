"""LIVE-3 tests — `AimArchitect` live body (corpus-driven) — mirrors LIVE-2.

Deterministic + offline: the live LLM call is mocked (`cua.llm.complete` for parse/merge units, or the
lower `cua.llm._call_model` seam for the trace-guard + end-to-end proofs) — no network, no real key.
Asserts: the live branch is inert with `CUA_LIVE` unset; a live mapped produce() yields the same-shaped
`ExpandedAim`/`DraftFragment` (five non-empty parts, citation_ids ⊆ corpus); exactly one `aim_architect`
TraceEvent per mapped produce() (the LIVE-2 trace-guard covers the map_over loop); and end-to-end (live
Synthesizer + live AimArchitect) inv-1/2/3 hold on clean cites, a fabricated citation is DETECTED
(max_rounds=1) and SCRUBBED (max_rounds=3), and the §2.1 envelope validates.

Owner: LIVE-3 (builder 1). Governing: contracts.md §1.6/§2.2/§3.1/§1.10; decisions live-bodies-wave /
demo-v1-corpus-only-scope / trace-recording-ownership.
"""

from __future__ import annotations

import cua.llm as llm
from cua.generation import run_generator
from cua.grounding import Grounder
from cua.nih.framework import Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.obligations import compile_obligations
from cua.nih.proposal import Proposal
from cua.nih.task import NIHGrantTask
from cua.orchestrator import Orchestrator
from cua.roles import BlueprintPlanner, InternalCritic, Reviser
from cua.roles.aim_architect import AimArchitect, _AimExpansion
from cua.roles.critic import _CritiqueOut
from cua.roles.reviser import _RevisedDraft
from cua.roles.synthesizer import _AimStub, _CitedClaim, _F1Argument
from cua.trace import TraceRecorder
from cua.types import Draft, EvidenceScores, RunConfig, SourceSet, Status


# --- fixtures -------------------------------------------------------------------------------------


def _corpus() -> SourceSet:
    return SourceSet([
        Paper(id="p1", authors=[], year=2020, title="Microglia in PD", venue="J", resolvable_id="10.1/p1", key_finding="microglial activation tracks progression", real=True),
        Paper(id="p2", authors=[], year=2021, title="GCase trial", venue="J", resolvable_id="NCT2", key_finding="GCase modulation in a phase 2 cohort", real=True),
        Paper(id="p3", authors=[], year=2019, title="Alpha-synuclein", venue="J", resolvable_id="10.1/p3", key_finding="aggregation in dopaminergic neurons", real=True),
    ])


class _T:
    grant_call = default_grant_call()


def _obligations():
    return compile_obligations(_T())


def _aim_stub(aim_id="aim-1", evidence_keys=("p1",)):
    return {"id": aim_id, "title": f"{aim_id}: targeted mechanism", "evidence_keys": list(evidence_keys)}


def _live_inputs(recorder: TraceRecorder, round: int = 0) -> dict:
    return {
        "corpus": _corpus(),
        "grant_call": default_grant_call(),
        "evidence_scores": EvidenceScores(),
        "_recorder": recorder,
        "_round": round,
    }


def _aim_expansion(citation_ids=("p1",)) -> _AimExpansion:
    return _AimExpansion(
        hypothesis="We will examine whether the targeted mechanism alters the clinical outcome.",
        rationale="Grounded in the cited corpus key findings.",
        approach="Methods and design specified to a rigor-judgable level.",
        expected_outcomes="Outcomes tied directly to the hypothesis.",
        pitfalls_alternatives="Explicit pitfalls and alternative strategies.",
        citation_ids=list(citation_ids),
    )


def _synth_output() -> _F1Argument:
    return _F1Argument(
        gap="A specific barrier remains unresolved.",
        significance=_CitedClaim(text="We will investigate whether microglial activation affects progression.", cited_corpus_ids=["p1"]),
        central_hypothesis=_CitedClaim(text="We will examine whether GCase modulation alters the outcome.", cited_corpus_ids=["p2"]),
        innovation=_CitedClaim(text="A specific departure from symptomatic-only practice.", cited_corpus_ids=[]),
        aims=[_AimStub(title="Aim 1: microglia", cited_corpus_ids=["p1"]), _AimStub(title="Aim 2: GCase", cited_corpus_ids=["p2"])],
    )


def _critique_payload() -> dict:
    """A valid `_CritiqueOut` (the live Critic now goes live too once CUA_LIVE is set): clean, fundable
    scores so a clean draft passes the §1.11 bar; an orphan still forces revise via all_in_source_set."""
    return {
        "f1": {"score": 7, "justification": "grounded and calibrated"},
        "f2": {"score": 7, "justification": "rigorous and feasible"},
        "f3": {"score": 7, "justification": "qualified team and environment"},
        "segment_scores": [],
        "decision": "pass",
        "flagged_obligation_ids": [],
    }


def _call_model_factory(aim_citation_ids=("p1",)):
    """A schema-aware `_call_model` mock: Synthesizer → `_F1Argument`; Critic → `_CritiqueOut`;
    AimArchitect → `_AimExpansion` (citing `aim_citation_ids`, which a fabrication test can point off-corpus)."""

    def _call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_F1Argument):
            payload = _synth_output().model_dump()
        elif tool == llm._tool_name(_CritiqueOut):
            payload = _critique_payload()
        elif tool == llm._tool_name(_RevisedDraft):
            payload = {"hedged_claims": []}  # fabrication case → only an orphan drop (code-owned); nothing to hedge
        else:
            payload = _aim_expansion(aim_citation_ids).model_dump()

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


def _live_env(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


# --- offline default ------------------------------------------------------------------------------


def test_offline_unset_takes_surrogate_not_complete(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("complete() must not run offline")))
    frag = AimArchitect().produce(_obligations(), _live_inputs(TraceRecorder()), Draft(), _aim_stub())
    assert frag.section == "aims" and frag.provides["aims"]  # surrogate ran


# --- live mapped produce(): parse + merge ---------------------------------------------------------


def test_live_produce_builds_expanded_aim(monkeypatch):
    _live_env(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _aim_expansion(("p1", "p2")))
    frag = AimArchitect().produce(_obligations(), _live_inputs(TraceRecorder()), Draft(), _aim_stub("aim-2"))

    assert frag.stage == "aim_architect" and frag.section == "aims" and frag.segment_id == "aim-2"
    aim = frag.provides["aims"][0]
    # all five §2.1 parts non-empty
    assert all([aim.hypothesis, aim.rationale, aim.approach, aim.expected_outcomes, aim.pitfalls_alternatives])
    assert set(aim.citation_ids) <= _corpus().ids()
    # the bound claim: evidence_ids == reference_ids == cited corpus ids, serves F2 (binds the per-aim ledger)
    c = frag.claims[0]
    assert c.id == "aim-2::hypothesis" and c.serves_dimension == "F2"
    assert c.evidence_ids == c.reference_ids == aim.citation_ids


def test_live_aim_grounds_clean_then_orphan(monkeypatch):
    _live_env(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _aim_expansion(("p1",)))
    frag = AimArchitect().produce(_obligations(), _live_inputs(TraceRecorder()), Draft(), _aim_stub())
    d = Draft(); d.fragments.append(frag)
    assert Grounder().ground(d, _corpus())[1].all_in_source_set

    monkeypatch.setattr(llm, "complete", lambda config, **kw: _aim_expansion(("p1", "FAKE-9")))
    frag2 = AimArchitect().produce(_obligations(), _live_inputs(TraceRecorder()), Draft(), _aim_stub())
    d2 = Draft(); d2.fragments.append(frag2)
    rep = Grounder().ground(d2, _corpus())[1]
    assert not rep.all_in_source_set and "FAKE-9" in rep.orphan_ids


# --- trace-guard: one aim_architect event per mapped produce() ------------------------------------


def test_trace_guard_one_event_per_mapped_aim(monkeypatch):
    _live_env(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _call_model_factory(("p1",)))
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    rec = TraceRecorder()
    run_generator(task, _obligations(), task.inputs(), None, rec, round=0)

    aim_evts = [e for e in rec.trace if e.role == "aim_architect"]
    assert len(aim_evts) == 3  # R01 → 3 aim stubs → 3 mapped produce() → 3 events (no double-record)
    assert all(e.output_ref == "aim_architect:live" and e.sampling == "effort=high" for e in aim_evts)
    assert len([e for e in rec.trace if e.role == "synthesizer"]) == 1


# --- end-to-end (live Synthesizer + live AimArchitect through the real Orchestrator) --------------


def _run(monkeypatch, *, aim_citation_ids=("p1",), max_rounds=3):
    _live_env(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _call_model_factory(aim_citation_ids))
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)
    return orch.run(task, RunConfig(max_rounds=max_rounds, dimension_thresholds={"F1": 5, "F2": 5}))


def test_end_to_end_clean_invariants_and_envelope(monkeypatch):
    artifact, trace, audit = _run(monkeypatch, aim_citation_ids=("p1",), max_rounds=3)

    assert isinstance(artifact, Proposal)                       # §2.1 envelope validated at assembly
    assert audit.grounding_report.all_in_source_set             # inv-1
    sat = [o for o in audit.obligation_ledger if o.status == Status.SATISFIED]
    assert all(o.evidence_ids for o in sat)                     # inv-2
    assert all(r.ok for r in audit.overclaim_check)             # inv-3 (hedged → clean)
    assert {p.id for p in artifact.references} <= _corpus().ids()
    # both writers went live
    assert len([e for e in trace if e.role == "synthesizer" and e.output_ref == "synthesizer:live"]) == 1
    assert len([e for e in trace if e.role == "aim_architect" and e.output_ref == "aim_architect:live"]) == 3


def test_end_to_end_fabrication_detected_at_max_rounds_1(monkeypatch):
    # No revise budget: the fabricated aim citation is DETECTED by the Grounder (inv-1 fails), not scrubbed.
    artifact, trace, audit = _run(monkeypatch, aim_citation_ids=("p1", "FAKE-9"), max_rounds=1)
    assert not audit.grounding_report.all_in_source_set
    assert "FAKE-9" in audit.grounding_report.orphan_ids
    assert isinstance(artifact, Proposal)                       # still assembles; envelope still validates
    assert "FAKE-9" not in {p.id for p in artifact.references}  # the deck never includes the fabrication


def test_end_to_end_fabrication_scrubbed_at_max_rounds_3(monkeypatch):
    # With revise budget: Grounder flags → Critic directs drop → Reviser scrubs → re-ground clean.
    artifact, trace, audit = _run(monkeypatch, aim_citation_ids=("p1", "FAKE-9"), max_rounds=3)
    assert audit.grounding_report.all_in_source_set             # inv-1 holds after the scrub
    assert "FAKE-9" not in audit.grounding_report.orphan_ids
    assert all("FAKE-9" not in a.citation_ids for a in artifact.aims)  # scrubbed from the aim payload too


# --- live-schema tolerance: _AimExpansion (live-structured-output-robustness) ---------------------


def test_aim_expansion_recovers_inline_cite():
    """An object whose prose inlines the cite (and leaves citation_ids empty) → recovered into
    citation_ids (and the prose cleaned), so the aim's citation survives for the Grounder."""
    a = _AimExpansion.model_validate({
        "hypothesis": "We will examine whether M alters O [literature:7].",
        "rationale": "r", "approach": "a", "expected_outcomes": "e", "pitfalls_alternatives": "p",
        "citation_ids": [],
    })
    assert a.citation_ids == ["literature:7"] and "[" not in a.hypothesis


def test_aim_expansion_tolerates_bare_string():
    """A fully-flattened aim (bare string) coerces into a VALID object (all five parts non-empty so the
    §2.1 _AimEnvelope holds) with the inline cite recovered — the run completes rather than hard-failing."""
    a = _AimExpansion.model_validate("An aim blob about microglia [trial:NCT9]")
    assert a.citation_ids == ["trial:NCT9"]
    assert all([a.hypothesis, a.rationale, a.approach, a.expected_outcomes, a.pitfalls_alternatives])


def test_aim_expansion_clean_object_passthrough():
    a = _aim_expansion(("p1", "p2"))
    a2 = _AimExpansion.model_validate(a.model_dump())
    assert a2.citation_ids == ["p1", "p2"] and a2.hypothesis == a.hypothesis
