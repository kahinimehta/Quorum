"""LIVE-6 tests — `Reviser` live body (the overclaim resister) — mirrors LIVE-2/3/5.

Deterministic + offline: the live LLM call is mocked (`cua.llm.complete` for the hedge/drop units, or the
lower `cua.llm._call_model` seam for the trace-guard + end-to-end proofs) — no network, no real key. The
RESISTANCE proof (`decisions/2026-06-02-live-reviser-overclaim-finding.md`): the surrogate Reviser re-phrases
via the claim's `phrase()` handles, but a LIVE writer claim is real Opus prose with NO handles, so an
overclaim is detected-not-resisted. The live Reviser RE-WRITES the flagged claim down to its permitted rung —
after a live revise round a planted L2 overclaim measures L1 and `overclaim_check[...].ok` flips True.

Owner: LIVE-6 (builder 1). Governing: contracts.md §1.5/§1.11/§1.12/§3.1; design §3; decisions
live-reviser-overclaim-finding / trace-recording-ownership / critic-scoring-rubric.
"""

from __future__ import annotations

import cua.llm as llm
from cua.grounding import Grounder, build_overclaim_check, level
from cua.nih.framework import F1, F2, Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.proposal import ArgumentSkeleton, Proposal
from cua.nih.run import RUN_CONFIG
from cua.nih.task import NIHGrantTask
from cua.orchestrator import Orchestrator
from cua.roles import BlueprintPlanner, InternalCritic, Reviser
from cua.roles._repair import parse_directives
from cua.roles.aim_architect import _AimExpansion
from cua.roles.critic import _CritiqueOut
from cua.roles.reviser import _HedgedClaim, _RevisedDraft, _live_revise_prompt
from cua.roles.synthesizer import _AimStub, _CitedClaim, _F1Argument
from cua.trace import TraceRecorder
from cua.types import Claim, Draft, DraftFragment, EvidenceScores, Level, ObligationPublic, SourceSet, Status


# --- fixtures -------------------------------------------------------------------------------------


_OVERCLAIM = "Microglial activation could reorient early intervention."   # level() → L2 ('could')
_HEDGED = "We will investigate whether microglial activation informs early intervention."  # → L1


def _corpus() -> SourceSet:
    return SourceSet([
        Paper(id="p1", authors=[], year=2020, title="Microglia in PD", venue="J", resolvable_id="10.1/p1", key_finding="microglial activation tracks progression", real=True),
        Paper(id="p2", authors=[], year=2021, title="GCase trial", venue="J", resolvable_id="NCT2", key_finding="GCase modulation in a phase 2 cohort", real=True),
    ])


def _claim(cid: str, text: str, refs, dim: str) -> Claim:
    # a LIVE-style claim: NO subject/predicate handles (the surrogate Reviser can't re-phrase it)
    return Claim(id=cid, text=text, evidence_ids=list(refs), reference_ids=list(refs), serves_dimension=dim)


def _overclaim_draft(*, sig_text=_OVERCLAIM, aim_refs=("p2",)) -> Draft:
    """An F1 fragment whose `significance` is a live-style L2 overclaim (embedded in the fragment text AND
    the skeleton payload, to prove the hedge propagates everywhere) + one F2 aim fragment."""
    sig = _claim("significance", sig_text, ("p1",), F1)
    central = _claim("central-hypothesis", "We will examine whether GCase modulation alters the outcome.", ("p2",), F1)
    innov = _claim("innovation", "A specific departure from symptomatic-only practice.", (), F1)
    skeleton = ArgumentSkeleton(
        gap="A specific barrier remains unresolved.",
        central_hypothesis=central.text,
        aim_stubs=[{"id": "aim-1", "title": "Aim 1", "evidence_keys": ["p1"]}],
        significance=sig_text,
        innovation=innov.text,
    )
    f1 = DraftFragment(stage="synthesizer", section="significance_innovation", text=sig_text + " " + innov.text,
                       claims=[sig, central, innov], serves_dimension=F1,
                       provides={"skeleton": [skeleton], "aim_stubs": skeleton.aim_stubs})
    aim_claim = _claim("aim-1::hypothesis", "We will examine whether the mechanism alters the outcome.", aim_refs, F2)
    f2 = DraftFragment(stage="aim_architect", section="aims", text=aim_claim.text, segment_id="aim-1",
                       claims=[aim_claim], serves_dimension=F2, provides={"aims": []})
    return Draft(fragments=[f1, f2])


def _obs_public() -> list[ObligationPublic]:
    return [
        ObligationPublic(id="X-1", dimension=F1, requirement="every reference resolves", satisfied_by=[], evidence_ids=[], status=Status.UNSATISFIED),
        ObligationPublic(id="X-2", dimension=F1, requirement="no claim overclaims its evidence", satisfied_by=[], evidence_ids=[], status=Status.UNSATISFIED),
    ]


def _critique(draft: Draft, corpus: SourceSet | None = None):
    """The code-owned critique (surrogate Critic, offline) — carries the real hedge/drop directives the
    live Reviser consumes."""
    grounded = Grounder().ground(draft, corpus or _corpus())[0]
    return InternalCritic().critique(grounded, _obs_public(), EvidenceScores(), [])


def _live(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


# --- offline default: the live branch is inert ----------------------------------------------------


def test_offline_unset_takes_surrogate_not_complete(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no complete() offline")))
    draft = _overclaim_draft()
    revised = Reviser().revise(draft, _critique(draft), [], [], recorder=TraceRecorder(), round=0)
    # surrogate ran: a live-style claim has no phrase() handle → the overclaim is NOT resisted (the finding)
    sig = next(c for f in revised.fragments for c in f.claims if c.id == "significance")
    assert sig.text == _OVERCLAIM and level(sig.text) is Level.L2


def test_live_inert_without_recorder(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no recorder → surrogate")))
    draft = _overclaim_draft()
    Reviser().revise(draft, _critique(draft), [], [])      # no recorder → surrogate, no complete()


# --- the RESISTANCE proof (unit): a live overclaim is RE-WRITTEN to L1 ----------------------------


def test_live_hedges_overclaim_to_l1(monkeypatch):
    draft = _overclaim_draft()
    critique = _critique(draft)
    # the Critic emitted the code-owned hedge directive for the overclaiming significance claim
    hedges, drops = parse_directives(s for ds in critique.dimension_scores.values() for s in ds.spans)
    assert hedges == {"significance": "L1"} and drops == []

    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RevisedDraft(hedged_claims=[_HedgedClaim(claim_id="significance", text=_HEDGED)]))
    revised = Reviser().revise(draft, critique, [], critique.flagged_obligations, recorder=TraceRecorder(), round=0)

    sig = next(c for f in revised.fragments for c in f.claims if c.id == "significance")
    assert sig.text == _HEDGED and level(sig.text) is Level.L1          # re-written DOWN to L1
    # propagated into the rendered prose AND the skeleton payload (no hollow pass)
    assert all("could reorient" not in f.text for f in revised.fragments)
    assert all("could reorient" not in sk.significance for f in revised.fragments for sk in f.provides.get("skeleton", []))
    # the re-overclaim-check now PASSES for significance — inv-3 RESISTED on live prose, not just flagged
    rows = build_overclaim_check([c for f in revised.fragments for c in f.claims], EvidenceScores())
    assert next(r for r in rows if r.claim == "significance").ok is True


def test_live_surgical_preserves_unflagged(monkeypatch):
    draft = _overclaim_draft()
    critique = _critique(draft)
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RevisedDraft(hedged_claims=[_HedgedClaim(claim_id="significance", text=_HEDGED)]))
    revised = Reviser().revise(draft, critique, [], critique.flagged_obligations, recorder=TraceRecorder(), round=0)
    # every claim that was NOT flagged is byte-identical (surgical edit — design §3)
    before = {c.id: c.text for f in draft.fragments for c in f.claims}
    after = {c.id: c.text for f in revised.fragments for c in f.claims}
    for cid in before:
        if cid == "significance":
            continue
        assert after[cid] == before[cid]


def test_live_drops_orphan(monkeypatch):
    # a fabricated citation (orphan) → the code-owned drop directive removes it (no LLM rewrite needed)
    draft = _overclaim_draft(sig_text="We will investigate whether microglia relate to progression.", aim_refs=("p2", "FAKE-9"))
    grounded = Grounder().ground(draft, _corpus())[0]
    assert "FAKE-9" in grounded.grounding_report.orphan_ids
    critique = InternalCritic().critique(grounded, _obs_public(), EvidenceScores(), [])

    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RevisedDraft(hedged_claims=[]))  # nothing to hedge
    revised = Reviser().revise(draft, critique, [], critique.flagged_obligations, recorder=TraceRecorder(), round=0)
    assert all("FAKE-9" not in c.reference_ids for f in revised.fragments for c in f.claims)


def test_live_falls_back_to_phrase_when_llm_omits(monkeypatch):
    """If the model doesn't return a rewrite for a flagged claim that DOES carry phrase() handles (a
    surrogate-style claim), the code falls back to the deterministic re-phrase — no flagged claim is left
    un-hedged."""
    sig = Claim(id="significance", text="The program causes the outcome.", evidence_ids=["p1"], reference_ids=["p1"],
                serves_dimension=F1, subject="The program", predicate="the outcome")  # L4, has handles
    f1 = DraftFragment(stage="synthesizer", section="significance_innovation", text="The program causes the outcome.",
                       claims=[sig], serves_dimension=F1, provides={})
    draft = Draft(fragments=[f1])
    critique = InternalCritic().critique(Grounder().ground(draft, _corpus())[0], _obs_public(), EvidenceScores(), [])

    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RevisedDraft(hedged_claims=[]))  # LLM returns nothing
    revised = Reviser().revise(draft, critique, [], critique.flagged_obligations, recorder=TraceRecorder(), round=0)
    out = next(c for f in revised.fragments for c in f.claims if c.id == "significance")
    assert level(out.text) is Level.L1 and "causes" not in out.text   # deterministic phrase() fallback fired


# --- prompt only shows the flagged claims (surgical) ----------------------------------------------


def test_live_prompt_lists_only_flagged():
    draft = _overclaim_draft()
    critique = _critique(draft)
    hedges, drops = parse_directives(s for ds in critique.dimension_scores.values() for s in ds.spans)
    prompt = _live_revise_prompt(draft, hedges, drops, critique, [])
    assert "significance" in prompt and _OVERCLAIM in prompt          # the flagged claim + its current text
    assert "central-hypothesis" not in prompt                        # an un-flagged claim is not shown
    assert "rung L1" in prompt and "exploratory" in prompt           # the rung legend


# --- trace-guard: exactly one reviser:live event per call -----------------------------------------


def _revised_response(out: _RevisedDraft):
    tool_name = llm._tool_name(_RevisedDraft)

    class _Block:
        type = "tool_use"
        name = tool_name
        input = out.model_dump()

    class _Usage:
        input_tokens = 800
        output_tokens = 120

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def test_live_records_exactly_one_reviser_event(monkeypatch):
    _live(monkeypatch)
    out = _RevisedDraft(hedged_claims=[_HedgedClaim(claim_id="significance", text=_HEDGED)])
    monkeypatch.setattr(llm, "_call_model", lambda request: _revised_response(out))
    draft = _overclaim_draft()
    rec = TraceRecorder()
    Reviser().revise(draft, _critique(draft), [], [], recorder=rec, round=1)

    assert len(rec.trace) == 1
    ev = rec.trace[0]
    assert ev.role == "reviser" and ev.output_ref == "reviser:live"
    assert ev.model == "claude-sonnet-4-6" and ev.sampling == "temp=0.25"
    assert ev.round == 1 and ev.tokens == 920


# --- end-to-end RESISTANCE proof (live Critic + live Reviser through the real Orchestrator) -------


def _synth_payload(sig_text: str) -> dict:
    return _F1Argument(
        gap="A specific barrier remains unresolved.",
        significance=_CitedClaim(text=sig_text, cited_corpus_ids=["p1"]),
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


def _e2e_call_model(*, sig_text: str, hedged_text: str):
    """Schema-aware `_call_model`: all four live roles. Synth plants the L2 `sig_text`; the Critic
    detects/penalizes it (code) → forces revise; the Reviser returns `hedged_text` (L1) for significance."""

    def _call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_F1Argument):
            payload = _synth_payload(sig_text)
        elif tool == llm._tool_name(_CritiqueOut):
            payload = {"f1": {"score": 7, "justification": "j"}, "f2": {"score": 7, "justification": "j"},
                       "f3": {"score": 7, "justification": "j"}, "segment_scores": [], "decision": "revise", "flagged_obligation_ids": []}
        elif tool == llm._tool_name(_RevisedDraft):
            payload = {"hedged_claims": [{"claim_id": "significance", "text": hedged_text}]}
        else:
            payload = _aim_payload()

        class _Block:
            type = "tool_use"
            name = tool
            input = payload

        class _Usage:
            input_tokens = 700
            output_tokens = 200

        class _Resp:
            content = [_Block()]
            stop_reason = "tool_use"
            usage = _Usage()

        return _Resp()

    return _call


def test_end_to_end_overclaim_resisted(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _e2e_call_model(sig_text=_OVERCLAIM, hedged_text=_HEDGED))
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)
    artifact, trace, audit = orch.run(task, RUN_CONFIG)

    assert isinstance(artifact, Proposal)                              # §2.1 envelope validated at assembly
    # the RESISTANCE: the planted L2 overclaim is GONE from the artifact's prose, re-written to L1
    sections_text = " ".join(s.text for s in artifact.sections)
    assert "could reorient" not in sections_text                       # the L2 overclaim is gone
    assert "investigate whether microglial activation" in sections_text  # the L1 rewrite landed in the section
    assert all(r.ok for r in audit.overclaim_check)                    # inv-3 RESISTED (not just flagged)
    assert audit.grounding_report.all_in_source_set                   # inv-1
    # the loop converged to pass after the live revise, and the live Reviser ran exactly once
    reviser_live = [e for e in trace if e.role == "reviser" and e.output_ref == "reviser:live"]
    assert len(reviser_live) == 1
    assert [e for e in trace if e.output_ref == "decision@r1" and e.decision == "pass"]


def test_end_to_end_reviser_live_event_per_round(monkeypatch):
    # the trace-guard at the reviser site: one reviser:live event for the (single) revise round
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _e2e_call_model(sig_text=_OVERCLAIM, hedged_text=_HEDGED))
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)
    _artifact, trace, _audit = orch.run(task, RUN_CONFIG)
    assert len([e for e in trace if e.role == "reviser"]) == 1        # no double-record (one event, the live one)
    assert all(e.output_ref == "reviser:live" for e in trace if e.role == "reviser")
