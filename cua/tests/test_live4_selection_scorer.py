"""LIVE-4 tests — `SelectionScorer` live body + best-of-N — mirrors LIVE-2/3/5/6.

Deterministic + offline: the live LLM call is mocked (`cua.llm.complete` for the rank units, or the lower
`cua.llm._call_model` seam for the trace-guard + end-to-end proofs) — no network, no real key. Asserts:
the live branch is inert with `CUA_LIVE` unset (surrogate is the default); a live `score()` ranks N
candidates and returns the top by dimension; best-of-N over identical surrogate candidates picks the first
(Proposal/Audit unchanged → only the Trace gains sample/selection events); exactly ONE
`selection_scorer:live` event per produce (trace-guard); the Selection Scorer is a SEPARATE judge from the
Critic (principle 2); `run_db` re-enables best-of-N (n=3).

Owner: LIVE-4 (builder 1). Governing: contracts.md §1.5/§1.6/§1.8; design §0/§5/principle 2; decisions
live-bodies-wave / trace-recording-ownership / selection-scorer-prompt.
"""

from __future__ import annotations

import cua.llm as llm
from cua.generation import _produce_one, run_generator
from cua.nih.framework import F1, Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.obligations import compile_obligations
from cua.nih.proposal import Proposal
from cua.nih.run import RUN_CONFIG
from cua.nih.task import NIHGrantTask
from cua.orchestrator import Orchestrator
from cua.roles import BlueprintPlanner, InternalCritic, Reviser, SelectionScorer
from cua.roles.aim_architect import _AimExpansion
from cua.roles.critic import _CritiqueOut, InternalCritic as _CriticClass
from cua.roles.reviser import _RevisedDraft
from cua.roles.selection_scorer import _CandidateScore, _RankingOut, _rank_prompt
from cua.roles.synthesizer import ArgumentSynthesizer, _AimStub, _CitedClaim, _F1Argument
from cua.trace import TraceRecorder
from cua.types import Claim, Draft, DraftFragment, EvidenceScores, ScoredFragment, SourceSet


# --- fixtures -------------------------------------------------------------------------------------


def _corpus() -> SourceSet:
    return SourceSet([
        Paper(id="p1", authors=[], year=2020, title="Microglia in PD", venue="J", resolvable_id="10.1/p1", key_finding="microglial activation tracks progression", real=True),
        Paper(id="p2", authors=[], year=2021, title="GCase trial", venue="J", resolvable_id="NCT2", key_finding="GCase modulation in a phase 2 cohort", real=True),
    ])


class _T:
    grant_call = default_grant_call()


def _obligations():
    return compile_obligations(_T())


def _candidate(cid_suffix: str, *, refs=("p1",)) -> DraftFragment:
    """A minimal F1 candidate fragment (distinct id so the ranker can tell candidates apart)."""
    claim = Claim(id=f"significance-{cid_suffix}", text=f"We will investigate whether {cid_suffix} relates to progression.",
                  evidence_ids=list(refs), reference_ids=list(refs), serves_dimension=F1)
    return DraftFragment(stage="synthesizer", section="significance_innovation", text=claim.text,
                         claims=[claim], serves_dimension=F1, provides={})


def _live(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


def _synth_output() -> _F1Argument:
    return _F1Argument(
        gap="A specific barrier remains unresolved.",
        significance=_CitedClaim(text="We will investigate whether microglial activation affects progression.", cited_corpus_ids=["p1"]),
        central_hypothesis=_CitedClaim(text="We will examine whether GCase modulation alters the outcome.", cited_corpus_ids=["p2"]),
        innovation=_CitedClaim(text="A specific departure from symptomatic-only practice.", cited_corpus_ids=[]),
        aims=[_AimStub(title="Aim 1: microglia", cited_corpus_ids=["p1"]), _AimStub(title="Aim 2: GCase", cited_corpus_ids=["p2"])],
    )


# --- offline default: the live branch is inert ----------------------------------------------------


def test_offline_unset_takes_surrogate_not_complete(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no complete() offline")))
    cands = [_candidate("a"), _candidate("b")]
    ranked = SelectionScorer().score(cands, F1, recorder=TraceRecorder(), round=0)
    assert len(ranked) == 2 and all(isinstance(r, ScoredFragment) for r in ranked)


def test_live_inert_without_recorder(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no recorder → surrogate")))
    ranked = SelectionScorer().score([_candidate("a")], F1)      # no recorder → surrogate
    assert len(ranked) == 1


# --- live score(): ranks N candidates, returns the top by dimension -------------------------------


def test_live_score_ranks_candidates(monkeypatch):
    _live(monkeypatch)
    cands = [_candidate("a"), _candidate("b"), _candidate("c")]
    # rank candidate 1 highest, 0 lowest
    ranking = _RankingOut(rankings=[_CandidateScore(index=0, score=1.0), _CandidateScore(index=1, score=9.0), _CandidateScore(index=2, score=4.0)])
    monkeypatch.setattr(llm, "complete", lambda config, **kw: ranking)
    ranked = SelectionScorer().score(cands, F1, recorder=TraceRecorder(), round=0)

    assert [r.score for r in ranked] == [1.0, 9.0, 4.0]
    best = max(ranked, key=lambda sf: sf.score).fragment
    assert best is cands[1]                                       # the driver's pick = the live top


def test_live_score_unscored_candidate_sinks(monkeypatch):
    _live(monkeypatch)
    cands = [_candidate("a"), _candidate("b")]
    # the model scored only candidate 0 → candidate 1 must sink below it (never an accidental winner)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RankingOut(rankings=[_CandidateScore(index=0, score=5.0)]))
    ranked = SelectionScorer().score(cands, F1, recorder=TraceRecorder(), round=0)
    assert ranked[0].score == 5.0 and ranked[1].score < 5.0
    assert max(ranked, key=lambda sf: sf.score).fragment is cands[0]


def test_live_score_falls_back_when_no_rankings(monkeypatch):
    _live(monkeypatch)
    cands = [_candidate("a"), _candidate("b")]
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RankingOut(rankings=[]))  # no usable ranking
    ranked = SelectionScorer().score(cands, F1, recorder=TraceRecorder(), round=0)
    # fell back to the surrogate → still a full, valid ranking (same length, real scores)
    assert len(ranked) == 2 and all(isinstance(r, ScoredFragment) for r in ranked)


# --- Selection Scorer is NOT the Critic (principle 2) ---------------------------------------------


def test_selection_scorer_is_not_the_critic():
    assert SelectionScorer is not _CriticClass
    # a separate, lighter judge: Sonnet (the picker) vs the Critic's Opus (the measurer)
    assert SelectionScorer.config.model_id != InternalCritic.config.model_id
    assert SelectionScorer.config.model_id == "claude-sonnet-4-6"
    # ranks on the dimension only — its schema carries no rubric scores / pass-revise decision
    assert set(_RankingOut.model_fields) == {"rankings"}


def test_rank_prompt_lists_candidates_and_dimension():
    prompt = _rank_prompt([_candidate("a"), _candidate("b")], F1)
    assert "CANDIDATE 0" in prompt and "CANDIDATE 1" in prompt
    assert f"dimension {F1}" in prompt and "PICKS" in prompt


# --- trace-guard: exactly one selection_scorer:live event per produce -----------------------------


def _live_response(payload: dict, tool: str):
    class _Block:
        type = "tool_use"
        name = tool
        input = payload

    class _Usage:
        input_tokens = 300
        output_tokens = 60

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def _best_of_n_call_model(request):
    """Schema-aware `_call_model` for a best-of-N Synthesizer produce: the writer (`_F1Argument`) and the
    ranker (`_RankingOut`) both go live. The ranker scores every candidate (index 0 highest)."""
    tool = request["tool_choice"]["name"]
    if tool == llm._tool_name(_F1Argument):
        return _live_response(_synth_output().model_dump(), tool)
    # _RankingOut — score 3 candidates (the Synthesizer's n_samples=3), candidate 0 highest
    payload = {"rankings": [{"index": i, "score": 3.0 - i} for i in range(3)]}
    return _live_response(payload, tool)


def test_trace_guard_one_selection_event_live(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _best_of_n_call_model)
    rec = TraceRecorder()
    inputs = {"corpus": _corpus(), "grant_call": default_grant_call(), "evidence_scores": EvidenceScores(),
              "_recorder": rec, "_round": 0}
    frag = _produce_one(ArgumentSynthesizer(), _obligations(), inputs, Draft(), None, SelectionScorer(), rec, 0, "synthesizer")

    assert frag.provides["skeleton"]                                          # a live candidate was picked
    synth_live = [e for e in rec.trace if e.role == "synthesizer" and e.output_ref == "synthesizer:live"]
    sel_live = [e for e in rec.trace if e.role == "selection_scorer" and e.output_ref == "selection_scorer:live"]
    assert len(synth_live) == 3                                              # 3 live writer samples (n=3)
    assert len(sel_live) == 1                                                # ONE live ranking event (no double-record)
    assert sel_live[0].model == "claude-sonnet-4-6" and sel_live[0].sampling == "temp=0.0"
    # the spine did NOT also echo a "best-of-3" selection event (the guard suppressed it)
    assert not [e for e in rec.trace if e.role == "selection_scorer" and e.output_ref != "selection_scorer:live"]


def test_trace_guard_surrogate_selection_event_offline(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    rec = TraceRecorder()
    inputs = {"corpus": _corpus(), "grant_call": default_grant_call(), "evidence_scores": EvidenceScores(),
              "_recorder": rec, "_round": 0}
    _produce_one(ArgumentSynthesizer(), _obligations(), inputs, Draft(), None, SelectionScorer(), rec, 0, "synthesizer")
    # surrogate path: 3 spine sample events + ONE spine selection event ("best-of-3") + the log_pairs event
    sel = [e for e in rec.trace if e.role == "selection_scorer"]
    assert len(sel) == 1 and sel[0].decision == "best-of-3" and sel[0].output_ref == "fragment:synthesizer"
    assert [e for e in rec.trace if e.role == "selection_pairs"]              # log_pairs still recorded


# --- offline best-of-N is byte-identical (picks among identical candidates) ------------------------


def test_offline_best_of_n_picks_first_deterministically(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    # the surrogate Synthesizer is deterministic → 3 identical candidates → the ranker ties → first kept
    rec = TraceRecorder()
    inputs = {"corpus": _corpus(), "grant_call": default_grant_call(), "evidence_scores": EvidenceScores(),
              "_recorder": rec, "_round": 0}
    best = _produce_one(ArgumentSynthesizer(), _obligations(), inputs, Draft(), None, SelectionScorer(), rec, 0, "synthesizer")
    single = ArgumentSynthesizer().produce(_obligations(), inputs, Draft(), None)
    # best-of-N over identical candidates == the single-shot fragment (same skeleton) → Proposal unchanged
    assert best.provides["skeleton"][0].significance == single.provides["skeleton"][0].significance


# --- run_db re-enables best-of-N ------------------------------------------------------------------


def test_run_db_uses_best_of_n():
    from cua.nih.run_db import _build_orchestrator

    orch = _build_orchestrator()
    assert isinstance(orch.selection_scorer, SelectionScorer)    # not None (LIVE-INT-A was None)


# --- end-to-end best-of-N (live Synthesizer + live Selection Scorer through the real Orchestrator) -


def _aim_payload() -> dict:
    return _AimExpansion(
        hypothesis="We will examine whether the targeted mechanism alters the clinical outcome.",
        rationale="Grounded in the cited corpus key findings.",
        approach="Methods and design specified to a rigor-judgable level.",
        expected_outcomes="Outcomes tied directly to the hypothesis.",
        pitfalls_alternatives="Explicit pitfalls and alternative strategies.",
        citation_ids=["p1"],
    ).model_dump()


def _e2e_call_model(request):
    """All five live roles: Synthesizer (`_F1Argument`), Selection Scorer (`_RankingOut`), AimArchitect
    (`_AimExpansion`), Critic (`_CritiqueOut`), Reviser (`_RevisedDraft`)."""
    tool = request["tool_choice"]["name"]
    if tool == llm._tool_name(_F1Argument):
        payload = _synth_output().model_dump()
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
        output_tokens = 120

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def test_end_to_end_best_of_n_live(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _e2e_call_model)
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=SelectionScorer())
    artifact, trace, audit = orch.run(task, RUN_CONFIG)

    assert isinstance(artifact, Proposal)                                    # §2.1 envelope validated
    assert audit.grounding_report.all_in_source_set                          # inv-1 over the picked candidate
    assert {p.id for p in artifact.references} <= _corpus().ids()
    # best-of-N engaged: 3 live writer samples + exactly one live ranking event
    assert len([e for e in trace if e.role == "synthesizer" and e.output_ref == "synthesizer:live"]) == 3
    assert len([e for e in trace if e.role == "selection_scorer" and e.output_ref == "selection_scorer:live"]) == 1
