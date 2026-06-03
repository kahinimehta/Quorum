"""LIVE-2 tests — `ArgumentSynthesizer` live body (corpus-driven) + the spine trace-guard.

Deterministic + offline: the live LLM call is mocked (either `cua.llm.complete` for the parse/merge
units, or the lower `cua.llm._call_model` seam for the end-to-end trace-guard proof) — no network, no
real key (a dummy `ANTHROPIC_API_KEY` only flips `is_live()`). Asserts: the live branch is inert with
`CUA_LIVE` unset (surrogate is the default); a live produce() yields the same-shaped `DraftFragment`
with F1 role claims citing only corpus ids; inv-1 holds (or the Grounder lists the orphan); exactly ONE
TraceEvent per produce() on both paths (the ruling); and the §2.1 envelope validates on live output.

Owner: LIVE-2 (builder 1). Governing: contracts.md §1.6/§2.2/§3.1/§1.10; decisions live-bodies-wave /
demo-v1-corpus-only-scope / trace-recording-ownership.
"""

from __future__ import annotations

import pytest

import cua.llm as llm
from cua.generation import _produce_one, run_generator
from cua.nih.framework import Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.obligations import compile_obligations, planned_aim_ids
from cua.nih.proposal import Proposal
from cua.nih.run import RUN_CONFIG
from cua.nih.task import NIHGrantTask
from cua.orchestrator import Orchestrator
from cua.roles import BlueprintPlanner, InternalCritic, Reviser
from cua.roles.critic import _CritiqueOut
from cua.roles.synthesizer import ArgumentSynthesizer, _AimStub, _CitedClaim, _F1Argument
from cua.trace import TraceRecorder
from cua.types import Draft, EvidenceScores, SourceSet


# --- fixtures: a tiny real-shaped corpus + obligations --------------------------------------------


def _corpus() -> SourceSet:
    return SourceSet([
        Paper(id="p1", authors=[], year=2020, title="Microglia in PD", venue="J", resolvable_id="10.1/p1", key_finding="microglial activation tracks progression", real=True),
        Paper(id="p2", authors=[], year=2021, title="GCase trial", venue="J", resolvable_id="NCT2", key_finding="GCase modulation in a phase 2 cohort", real=True),
        Paper(id="p3", authors=[], year=2019, title="Alpha-synuclein", venue="J", resolvable_id="10.1/p3", key_finding="aggregation in dopaminergic neurons", real=True),
    ])


class _Task:  # minimal carrier for compile_obligations (reads grant_call.mechanism/title)
    grant_call = default_grant_call()


def _obligations():
    return compile_obligations(_Task())


def _sample_output(*, sig_ids=("p1",), central_ids=("p2",), innov_ids=(), aims=None) -> _F1Argument:
    return _F1Argument(
        gap="A specific barrier to progress remains unresolved.",
        significance=_CitedClaim(text="We will investigate whether microglial activation affects progression.", cited_corpus_ids=list(sig_ids)),
        central_hypothesis=_CitedClaim(text="We will examine whether GCase modulation alters the clinical outcome.", cited_corpus_ids=list(central_ids)),
        innovation=_CitedClaim(text="A specific departure from current symptomatic-only practice.", cited_corpus_ids=list(innov_ids)),
        aims=aims if aims is not None else [_AimStub(title="Aim A", cited_corpus_ids=["p1"]), _AimStub(title="Aim B", cited_corpus_ids=["p3"])],
    )


def _live_inputs(recorder: TraceRecorder | None = None, round: int = 0) -> dict:
    inputs = {"corpus": _corpus(), "grant_call": default_grant_call(), "evidence_scores": EvidenceScores()}
    if recorder is not None:
        inputs["_recorder"] = recorder
        inputs["_round"] = round
    return inputs


# --- offline default: the live branch is inert ----------------------------------------------------


def test_offline_unset_takes_surrogate_not_complete(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)

    def boom(*a, **k):
        raise AssertionError("complete() must not be called when CUA_LIVE is unset")

    monkeypatch.setattr(llm, "complete", boom)
    rec = TraceRecorder()
    frag = ArgumentSynthesizer().produce(_obligations(), _live_inputs(rec), Draft(), None)
    assert frag.stage == "synthesizer" and frag.provides["skeleton"]  # surrogate ran, valid fragment


# --- live produce(): parse + merge (mocked complete) ----------------------------------------------


def test_live_produce_builds_f1_fragment(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _sample_output())

    obligations = _obligations()
    rec = TraceRecorder()
    frag = ArgumentSynthesizer().produce(obligations, _live_inputs(rec), Draft(), None)

    # the three F1 role claims the ledger binds, all serves_dimension=F1
    ids = {c.id for c in frag.claims}
    assert ids == {"significance", "central-hypothesis", "innovation"}
    assert all(c.serves_dimension == "F1" for c in frag.claims)
    # corpus-only: evidence_ids == reference_ids == cited corpus ids; all ⊆ corpus
    corpus_ids = _corpus().ids()
    for c in frag.claims:
        assert c.evidence_ids == c.reference_ids
        assert set(c.reference_ids) <= corpus_ids
    # aim_stubs: exactly the planned count (R01 → 3), each carrying an id + title
    stubs = frag.provides["aim_stubs"]
    assert [s["id"] for s in stubs] == planned_aim_ids(obligations)  # ['aim-1','aim-2','aim-3']
    assert all(s["title"] for s in stubs)
    # the third aim (not supplied by the model) is anchored so it stays groundable
    assert stubs[2]["evidence_keys"]
    assert frag.provides["skeleton"][0].central_hypothesis == "We will examine whether GCase modulation alters the clinical outcome."


def test_live_produce_grounds_clean_then_orphan(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    from cua.grounding import Grounder

    # clean: cites only corpus ids → inv-1 holds
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _sample_output(sig_ids=("p1",), central_ids=("p2",)))
    frag = ArgumentSynthesizer().produce(_obligations(), _live_inputs(TraceRecorder()), Draft(), None)
    draft = Draft(); draft.fragments.append(frag)
    _, report = Grounder().ground(draft, _corpus())
    assert report.all_in_source_set and report.orphan_ids == []

    # fabrication: a cited id not in the corpus → the Grounder lists it as an orphan (the trust gate)
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _sample_output(sig_ids=("p1", "FAKE-999"), central_ids=("p2",)))
    frag2 = ArgumentSynthesizer().produce(_obligations(), _live_inputs(TraceRecorder()), Draft(), None)
    draft2 = Draft(); draft2.fragments.append(frag2)
    _, report2 = Grounder().ground(draft2, _corpus())
    assert not report2.all_in_source_set and "FAKE-999" in report2.orphan_ids


# --- trace-guard: exactly one TraceEvent per produce(), both paths --------------------------------


def _fake_response(output: _F1Argument):
    tool_name = llm._tool_name(_F1Argument)

    class _Block:
        type = "tool_use"
        name = tool_name
        input = output.model_dump()

    class _Usage:
        input_tokens = 1500
        output_tokens = 400

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def _critique_payload() -> dict:
    """A valid `_CritiqueOut` — the live Critic (LIVE-5) goes live too once CUA_LIVE is set. Clean,
    fundable scores so a clean draft clears the §1.11 bar (an orphan still forces revise via the
    code-owned all_in_source_set gate, independent of these scores)."""
    return {
        "f1": {"score": 7, "justification": "grounded and calibrated"},
        "f2": {"score": 7, "justification": "rigorous and feasible"},
        "f3": {"score": 7, "justification": "qualified team and environment"},
        "segment_scores": [],
        "decision": "pass",
        "flagged_obligation_ids": [],
    }


def _schema_aware_response(request):
    """Dispatch the mocked tool-call by the requested tool name — Synthesizer (`_F1Argument`),
    AimArchitect (`_AimExpansion`, LIVE-3), and Critic (`_CritiqueOut`, LIVE-5) all go live when
    CUA_LIVE is set."""
    tool = request["tool_choice"]["name"]
    if tool == llm._tool_name(_F1Argument):
        payload = _sample_output().model_dump()
    elif tool == llm._tool_name(_CritiqueOut):
        payload = _critique_payload()
    else:  # AimArchitect's _AimExpansion (validated against whatever schema that call passed)
        payload = {
            "hypothesis": "We will examine whether the targeted mechanism alters the outcome.",
            "rationale": "Grounded in the cited corpus.",
            "approach": "Methods and design at rigor-judgable specificity.",
            "expected_outcomes": "Outcomes tied to the hypothesis.",
            "pitfalls_alternatives": "Pitfalls and alternative strategies.",
            "citation_ids": ["p1"],
        }

    class _Block:
        type = "tool_use"
        name = tool
        input = payload

    class _Usage:
        input_tokens = 1820
        output_tokens = 560

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp()


def test_trace_guard_live_path_records_exactly_one(monkeypatch):
    # real complete() runs (records its own event); only the network seam is mocked.
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setattr(llm, "_call_model", lambda request: _fake_response(_sample_output()))

    rec = TraceRecorder()
    inputs = _live_inputs(rec)
    frag = _produce_one(ArgumentSynthesizer(), _obligations(), inputs, Draft(), None, None, rec, 0, "synthesizer")

    assert frag.provides["skeleton"]                       # live fragment built
    assert len(rec.trace) == 1                             # exactly ONE event (no double-record)
    ev = rec.trace[0]
    assert ev.role == "synthesizer"
    assert ev.model == "claude-opus-4-8" and ev.sampling == "effort=xhigh"
    assert ev.output_ref == "synthesizer:live" and ev.tokens == 1900  # real usage from complete()


def test_trace_guard_surrogate_path_records_exactly_one(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    rec = TraceRecorder()
    inputs = _live_inputs(rec)
    _produce_one(ArgumentSynthesizer(), _obligations(), inputs, Draft(), None, None, rec, 0, "synthesizer")
    assert len(rec.trace) == 1                             # spine records the surrogate's fallback event
    assert rec.trace[0].output_ref == "fragment:synthesizer"


# --- end-to-end (mocked live Synthesizer through the real Orchestrator) ---------------------------


def test_end_to_end_live_synth_envelope_and_inv1(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    monkeypatch.setattr(llm, "_call_model", _schema_aware_response)  # both live writers (Synth + Aim)

    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    # selection_scorer=None → single-shot live call (the demo's n=1; LIVE-4 owns best-of-N)
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)
    artifact, trace, audit = orch.run(task, RUN_CONFIG)

    # the §2.1 envelope validated inside assemble_artifact (else run() would have raised)
    assert isinstance(artifact, Proposal)
    assert artifact.central_hypothesis == "We will examine whether GCase modulation alters the clinical outcome."
    # inv-1: every reference ∈ corpus (real LLM output, audit-proven)
    assert audit.grounding_report.all_in_source_set
    assert {p.id for p in artifact.references} <= _corpus().ids()
    # exactly one live synthesizer event in the trace (trace-guard end to end)
    synth_live = [e for e in trace if e.role == "synthesizer" and e.output_ref == "synthesizer:live"]
    assert len(synth_live) == 1


# --- significance prompt tightened to exploratory (LIVE-INT_B inv-3 finding) -----------------------


def test_exploratory_significance_measures_l1_old_style_l2():
    """The code-owned hedge-cue lexicon (level(), §1.12) is what the prompt steers toward L1. A
    significance written per the tightened prompt (open question + unmet need, no asserted relationship)
    measures L1 (== permitted for unscored evidence); the previously-flagged suggestive style ('could …')
    measures L2 — the overclaim the live demo flagged (reviews/LIVE-INT_B.md). NOTE: the real proof is a
    live re-run (the model's actual prose); this only pins the lexicon target the prompt aims at."""
    from cua.grounding import level
    from cua.types import Level

    exploratory = (
        "We will investigate whether peripheral LRRK2 signaling relates to alpha-synuclein pathology; "
        "resolving this open question would address a major unmet need in early Parkinson disease."
    )
    flagged = "Peripheral LRRK2 signaling and GCase capacity could reorient where early intervention is attempted."
    assert level(exploratory) is Level.L1
    assert level(flagged) is Level.L2


def test_live_prompt_bans_suggestive_and_relational_cues():
    """The tightened `_live_prompt` frames significance as the open question and names the suggestive-hedge
    + relational cues to avoid (the L2 culprits, e.g. 'could', that slipped past the old causal-only ban)."""
    from cua.roles.synthesizer import _live_prompt

    p = _live_prompt("Parkinson's disease", _corpus(), _obligations(), 3).lower()
    assert "exploratory" in p and "open question" in p
    for cue in ("could", "may", "might", "intersect with", "co-occur"):
        assert cue in p
    assert "significance included" in p  # the rule explicitly binds significance to the exploratory rung


# --- live-schema tolerance: model flattens a nested field to a string (live-structured-output-robustness) --


def test_cited_claim_tolerates_flattened_string():
    """A bare string (the dem2 failure) coerces into a valid _CitedClaim — the inline [type:id] cite is
    recovered into cited_corpus_ids (so the Grounder still checks it) and the visible text is cleaned."""
    c = _CitedClaim.model_validate("We will investigate whether X relates to Y [literature:39666171].")
    assert c.cited_corpus_ids == ["literature:39666171"]
    assert c.text == "We will investigate whether X relates to Y." and "[" not in c.text


def test_cited_claim_object_passthrough_and_inline_recover():
    # a clean object is unchanged
    c = _CitedClaim.model_validate({"text": "clean text", "cited_corpus_ids": ["literature:1"]})
    assert c.text == "clean text" and c.cited_corpus_ids == ["literature:1"]
    # an object that inlined the cite into text but left the list empty → recovered (no cite lost)
    c2 = _CitedClaim.model_validate({"text": "We will examine whether Z. [trial:NCT01]", "cited_corpus_ids": []})
    assert c2.cited_corpus_ids == ["trial:NCT01"]


def test_aim_stub_tolerates_flattened_string():
    s = _AimStub.model_validate("Aim 1: microglia [literature:42]")
    assert s.title == "Aim 1: microglia" and s.cited_corpus_ids == ["literature:42"]


def test_f1argument_nested_str_significance_validates():
    """The exact dem2 hard-fail: significance came back a bare string. The nested before-validator now
    coerces it, so _F1Argument validates instead of raising after the paid call."""
    f = _F1Argument.model_validate({
        "gap": "g",
        "significance": "We will investigate whether A relates to B [literature:39666171].",
        "central_hypothesis": {"text": "We will examine whether C.", "cited_corpus_ids": ["trial:NCT2"]},
        "innovation": "A departure.",
        "aims": ["Aim A [literature:1]", {"title": "Aim B", "cited_corpus_ids": ["grant:R01"]}],
    })
    assert f.significance.cited_corpus_ids == ["literature:39666171"]
    assert [a.cited_corpus_ids for a in f.aims] == [["literature:1"], ["grant:R01"]]


def test_end_to_end_str_significance_completes_and_cite_in_deck(monkeypatch):
    """A live run where significance comes back as a STRING now COMPLETES (no ValidationError) and the
    recovered cite survives into the references deck (inv-1 still checks it)."""
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    corpus = SourceSet([
        Paper(id="literature:39666171", authors=[], year=2020, title="LRRK2", venue="J", resolvable_id="39666171", key_finding="k", real=True),
        Paper(id="trial:NCT2", authors=[], year=2021, title="GCase", venue="J", resolvable_id="NCT2", key_finding="k", real=True),
    ])

    def call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_F1Argument):
            payload = {
                "gap": "A gap.",
                "significance": "We will investigate whether peripheral LRRK2 signaling relates to pathology [literature:39666171].",
                "central_hypothesis": {"text": "We will examine whether GCase modulation alters the outcome.", "cited_corpus_ids": ["trial:NCT2"]},
                "innovation": {"text": "A specific departure.", "cited_corpus_ids": []},
                "aims": [{"title": "Aim 1", "cited_corpus_ids": ["literature:39666171"]}],
            }
        elif tool == llm._tool_name(_CritiqueOut):
            payload = _critique_payload()
        else:
            payload = {"hypothesis": "We will examine whether M alters O.", "rationale": "r", "approach": "a",
                       "expected_outcomes": "e", "pitfalls_alternatives": "p", "citation_ids": ["literature:39666171"]}

        class _B:
            type = "tool_use"; name = tool; input = payload

        class _U:
            input_tokens = 900; output_tokens = 300

        class _R:
            content = [_B()]; stop_reason = "tool_use"; usage = _U()

        return _R()

    monkeypatch.setattr(llm, "_call_model", call)
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=corpus, evidence=EvidenceScores())
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)
    artifact, _trace, audit = orch.run(task, RUN_CONFIG)

    assert isinstance(artifact, Proposal)                                    # completed — no ValidationError
    assert "literature:39666171" in {p.id for p in artifact.references}      # recovered cite survived to the deck
    assert audit.grounding_report.all_in_source_set                          # inv-1 still holds on it


def test_end_to_end_retry_recovers_missing_field(monkeypatch):
    """The dem2-2 hard-fail: the Synthesizer's first response OMITS the required `innovation` field
    (coercion can't help — nothing to coerce). complete()'s retry re-prompts with the error and the second
    response is valid, so the run COMPLETES instead of hard-failing — still ONE synthesizer:live event."""
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    full = _sample_output().model_dump()
    missing = {k: v for k, v in full.items() if k != "innovation"}  # drop the required field → ValidationError
    state = {"synth": 0}

    def call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_F1Argument):
            state["synth"] += 1
            payload = missing if state["synth"] == 1 else full
        elif tool == llm._tool_name(_CritiqueOut):
            payload = _critique_payload()
        else:
            payload = {"hypothesis": "We will examine whether M alters O.", "rationale": "r", "approach": "a",
                       "expected_outcomes": "e", "pitfalls_alternatives": "p", "citation_ids": ["p1"]}

        class _B:
            type = "tool_use"; name = tool; input = payload

        class _U:
            input_tokens = 100; output_tokens = 50

        class _R:
            content = [_B()]; stop_reason = "tool_use"; usage = _U()

        return _R()

    monkeypatch.setattr(llm, "_call_model", call)
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=_corpus(), evidence=EvidenceScores())
    orch = Orchestrator(conditioner=BlueprintPlanner(), critic=InternalCritic(), reviser=Reviser(), selection_scorer=None)
    artifact, trace, _audit = orch.run(task, RUN_CONFIG)

    assert isinstance(artifact, Proposal)                                    # completed via the retry
    assert state["synth"] == 2                                               # retried once (missing→valid)
    assert len([e for e in trace if e.role == "synthesizer" and e.output_ref == "synthesizer:live"]) == 1
