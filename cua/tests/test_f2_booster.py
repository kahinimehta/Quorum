"""F2-BOOSTER tests — the in-loop rigor booster (mine the UN-SELECTED corpus → harden pitfalls/outcomes).

Deterministic + offline: the live LLM call is mocked (`cua.llm.complete` for the apply/validation units, or
the lower `cua.llm._call_model` seam for the trace-event proof) — no network, no real key. The contract
(`build/decisions/2026-06-03-f2-booster-design.md`): live-only / inert-offline; FEEDS the Reviser (content),
never the Critic; does NOT re-grade evidence; cites ∈ corpus (inv-1) and content hedged (inv-3).

Owner: F2-BOOSTER (builder 1). Governing: relay `build/live/F2-BOOSTER_relay.md`; design doc above;
evidence `build/decisions/2026-06-03-graded2-cap-vs-base.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

import cua.llm as llm
from cua.grounding import Grounder, build_overclaim_check
from cua.nih.framework import F2, Paper
from cua.nih.ingestion import (
    CONTRADICTION_IDS_ATTR,
    WRITER_VIEW_ATTR,
    attach_contradiction_ids,
    attach_writer_view,
    ingest,
)
from cua.nih.proposal import ExpandedAim
from cua.roles import Reviser
from cua.roles._rigor_booster import (
    _AimRigor,
    _RigorBoost,
    boost_rigor,
    select_unselected_subset,
)
from cua.trace import TraceRecorder
from cua.types import (
    Claim,
    Draft,
    DraftFragment,
    EvidenceEntry,
    EvidenceScores,
    Grade,
    SourceSet,
)


# --- fixtures -------------------------------------------------------------------------------------


@dataclass
class _ViewRow:
    """A minimal writer-view row stand-in (the booster reads only `.id`)."""

    id: str


def _paper(pid: str, *, year: int = 2020, kf: str = "a distinct finding", title: str | None = None) -> Paper:
    return Paper(id=pid, authors=[], year=year, title=title or f"T-{pid}", venue="J",
                 resolvable_id=f"10/{pid}", key_finding=kf, real=True)


def _corpus_with_view(papers, selected_ids, contra_ids=()) -> SourceSet:
    """A corpus with the booster's two binding-side attrs attached directly (precise control of which
    papers are 'selected' vs un-selected, and which carry the contradiction signal)."""
    corpus = SourceSet(list(papers))
    setattr(corpus, WRITER_VIEW_ATTR, [_ViewRow(i) for i in selected_ids])
    setattr(corpus, CONTRADICTION_IDS_ATTR, set(contra_ids))
    return corpus


def _aim_fragment(aim_id: str, cite: str, *, pitfalls: str = "Pitfalls and alternative strategies (filler).",
                  outcomes: str = "Expected outcomes tied to the hypothesis (filler).") -> DraftFragment:
    """An aim fragment shaped like the AimArchitect's output: one ExpandedAim payload + a hypothesis claim
    carrying `evidence_ids = reference_ids = [cite]` (so a real grade resolves)."""
    aim = ExpandedAim(
        id=aim_id,
        hypothesis=f"We will investigate whether the {aim_id} mechanism alters the outcome.",
        rationale="Grounded in the cited corpus.",
        approach=f"Methods/design for {aim_id} at a rigor-judgable level.",
        expected_outcomes=outcomes,
        pitfalls_alternatives=pitfalls,
        citation_ids=[cite],
    )
    claim = Claim(id=f"{aim_id}::hypothesis", text=aim.hypothesis, evidence_ids=[cite],
                  reference_ids=[cite], serves_dimension=F2)
    return DraftFragment(stage="aim_architect", section="aims", text=aim.approach, segment_id=aim_id,
                         claims=[claim], serves_dimension=F2, provides={"aims": [aim]})


def _draft(*aim_frags) -> Draft:
    return Draft(fragments=list(aim_frags))


def _live(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


def _tool_response(payload: dict):
    """A schema-shaped Anthropic response carrying ONE forced tool_use block (for the `_call_model` seam)."""

    class _Block:
        type = "tool_use"
        name = None  # set per-call below
        input = payload

    class _Usage:
        input_tokens = 900
        output_tokens = 150

    class _Resp:
        content = [_Block()]
        stop_reason = "tool_use"
        usage = _Usage()

    return _Resp


# === un-selected subset selection (pure) =============================================================


def test_subset_is_full_corpus_minus_writer_view():
    papers = [_paper(f"p{i}", kf=f"finding number {i} distinct topic") for i in range(6)]
    corpus = _corpus_with_view(papers, selected_ids=["p0", "p1"])
    subset, dropped = select_unselected_subset(corpus, cap=10)
    assert {p.id for p in subset} == {"p2", "p3", "p4", "p5"}  # exactly corpus − writer_view
    assert dropped == 0  # cap not binding


def test_subset_contradiction_prioritized_first():
    papers = [_paper(f"p{i}", year=2000 + i, kf=f"finding number {i} distinct topic") for i in range(6)]
    # p5 (lowest recency-priority by id, but a contradiction) must lead the subset.
    corpus = _corpus_with_view(papers, selected_ids=["p0"], contra_ids=["p5"])
    subset, _dropped = select_unselected_subset(corpus, cap=10)
    assert subset[0].id == "p5"  # contradiction member sorts ahead of everything else


def test_subset_caps_and_reports_dropped():
    papers = [_paper(f"p{i}", kf=f"finding number {i} distinct topic") for i in range(8)]
    corpus = _corpus_with_view(papers, selected_ids=["p0"])  # 7 un-selected
    subset, dropped = select_unselected_subset(corpus, cap=3)
    assert len(subset) == 3 and dropped == 4  # 7 un-selected, cap 3 → 4 dropped (logged, not silent)


def test_subset_diversifies_by_distinct_finding():
    # p1/p2 share a near-identical finding; with a binding cap the duplicate is deferred (not picked first).
    papers = [
        _paper("p1", kf="tau aggregation drives progressive neuronal loss in cortex"),
        _paper("p2", kf="tau aggregation drives progressive neuronal loss in the cortex region"),
        _paper("p3", kf="a wholly unrelated microglial activation mechanism"),
    ]
    corpus = _corpus_with_view(papers, selected_ids=[])
    subset, dropped = select_unselected_subset(corpus, cap=2)
    ids = [p.id for p in subset]
    assert ids[0] == "p1" and "p3" in ids and "p2" not in ids  # the near-duplicate p2 is dropped, not p3
    assert dropped == 1


def test_subset_empty_when_all_selected():
    papers = [_paper("p1"), _paper("p2")]
    corpus = _corpus_with_view(papers, selected_ids=["p1", "p2"])
    subset, dropped = select_unselected_subset(corpus, cap=5)
    assert subset == [] and dropped == 0


def test_ingestion_attaches_contradiction_ids_complement():
    # the real ingestion wiring: attach_writer_view + attach_contradiction_ids populate the booster's attrs,
    # and the un-selected subset is the complement of the writer view.
    papers = [_paper(f"p{i}", kf=f"finding {i} distinct topic area") for i in range(5)]
    corpus = SourceSet(list(papers))
    result = ingest(corpus, topic="distinct topic")
    attach_writer_view(corpus, result)
    attach_contradiction_ids(corpus, result)
    assert hasattr(corpus, WRITER_VIEW_ATTR) and hasattr(corpus, CONTRADICTION_IDS_ATTR)
    view_ids = {r.id for r in getattr(corpus, WRITER_VIEW_ATTR)}
    subset, _dropped = select_unselected_subset(corpus, cap=100)
    assert {p.id for p in subset} == ({p.id for p in papers} - view_ids)


# === inert-offline / no-corpus: the booster never runs ==============================================


def test_inert_offline_noop(monkeypatch):
    """Offline (not live): the Reviser takes the surrogate path and the booster never fires — the aims'
    pitfalls/outcomes are byte-unchanged and no LLM call is made."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no complete() offline")))
    corpus = _corpus_with_view([_paper("p1"), _paper("p2", kf="other distinct finding")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    from cua.roles import InternalCritic
    crit = InternalCritic().critique(Grounder().ground(draft, corpus)[0], [], EvidenceScores(), [])
    revised = Reviser(corpus=corpus, topic="t").revise(draft, crit, [], [], recorder=TraceRecorder(), round=0)
    aim = revised.fragments[0].provides["aims"][0]
    assert "filler" in aim.pitfalls_alternatives and "filler" in aim.expected_outcomes  # unchanged


def test_no_corpus_inert_even_when_live(monkeypatch):
    """A bare `Reviser()` (no injected corpus — the fixture oracle + every existing test) never invokes the
    booster, even live: the booster import is short-circuited by the `self._corpus is None` gate."""
    _live(monkeypatch)
    import cua.roles.reviser as reviser_mod
    monkeypatch.setattr(reviser_mod, "boost_rigor", lambda *a, **k: (_ for _ in ()).throw(AssertionError("booster ran without a corpus")))
    # the hedge complete() still returns a (no-op) revised draft
    from cua.roles.reviser import _RevisedDraft
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RevisedDraft(hedged_claims=[]))
    draft = _draft(_aim_fragment("aim-1", "p1"))
    from cua.roles import InternalCritic
    crit = InternalCritic().critique(Grounder().ground(draft, SourceSet([_paper("p1")]))[0], [], EvidenceScores(), [])
    Reviser().revise(draft, crit, [], [], recorder=TraceRecorder(), round=0)  # must not raise


# === live apply: rewrites the two fields, validates cites, leaves claims/grades untouched ============


def _boost_via_complete(monkeypatch, aims_out):
    """Monkeypatch `llm.complete` to return a fixed `_RigorBoost` (no trace event — that is the real
    complete's job, proved separately)."""
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RigorBoost(aims=aims_out))


def test_boost_rewrites_fields_and_validates_cites(monkeypatch):
    _live(monkeypatch)
    corpus = _corpus_with_view([_paper("p1"), _paper("u9", kf="comparable underpowered cohort")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    _boost_via_complete(monkeypatch, [
        _AimRigor(aim_id="aim-1",
                  pitfalls_alternatives="Comparable cohorts were underpowered at n<50; alternative: a sequential design.",
                  expected_outcomes="Expect a 20-30% effect-size reduction, directionally consistent with comparable work.",
                  drawn_from_ids=["u9", "FAKE-404"]),  # FAKE-404 is not in corpus → must be dropped
    ])
    prov = boost_rigor(corpus, draft.fragments, None, TraceRecorder(), 0, topic="t")

    aim = draft.fragments[0].provides["aims"][0]
    assert "underpowered" in aim.pitfalls_alternatives and "effect-size" in aim.expected_outcomes  # substance landed
    assert "filler" not in aim.pitfalls_alternatives and "filler" not in aim.expected_outcomes
    assert prov[0]["drawn_from"] == ["u9"]                 # validated ∈ corpus
    assert prov[0]["dropped_non_corpus"] == ["FAKE-404"]   # fabrication dropped (inv-1 honesty)


def test_boost_preserves_claims_grades_and_deck(monkeypatch):
    """The inv-1/inv-3 safety proof: the booster touches NO claim/grade/citation — the hypothesis claim,
    its grade, the references deck, and the overclaim check are byte-identical before/after."""
    _live(monkeypatch)
    corpus = _corpus_with_view([_paper("p1"), _paper("u9", kf="comparable cohort")], selected_ids=["p1"])
    evidence = EvidenceScores({"p1": EvidenceEntry(grade=Grade.MODERATE, evidence_features={}, support_source_ids=["p1"])})
    draft = _draft(_aim_fragment("aim-1", "p1"))
    claim = draft.fragments[0].claims[0]
    before_claim = (claim.text, list(claim.evidence_ids), list(claim.reference_ids))
    before_refs = draft.reference_ids()
    before_over = build_overclaim_check(draft.claims(), evidence)

    _boost_via_complete(monkeypatch, [
        _AimRigor(aim_id="aim-1", pitfalls_alternatives="Real failure modes.", expected_outcomes="Quantified outcomes.", drawn_from_ids=["u9"]),
    ])
    boost_rigor(corpus, draft.fragments, None, TraceRecorder(), 0, topic="t")

    claim = draft.fragments[0].claims[0]
    assert (claim.text, list(claim.evidence_ids), list(claim.reference_ids)) == before_claim  # claim untouched
    assert draft.reference_ids() == before_refs                                              # deck untouched (inv-1)
    after_over = build_overclaim_check(draft.claims(), evidence)
    assert [(r.claim, r.evidence_grade, r.permitted_level, r.ok) for r in after_over] == \
           [(r.claim, r.evidence_grade, r.permitted_level, r.ok) for r in before_over]       # overclaim check identical (inv-3)


def test_boost_strips_inline_cites_from_prose(monkeypatch):
    """A model that inlines `[type:id]` cites into the prose → recovered into drawn_from_ids (validated)
    and the visible prose is left clean."""
    _live(monkeypatch)
    corpus = _corpus_with_view([_paper("p1"), _paper("literature:7", kf="x")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    # the schema's mode="before" validator recovers inline cites — emulate a raw dict the way the API returns it
    monkeypatch.setattr(llm, "complete", lambda config, **kw: _RigorBoost.model_validate(
        {"aims": [{"aim_id": "aim-1",
                   "pitfalls_alternatives": "Underpowered cohorts [literature:7] limit inference.",
                   "expected_outcomes": "Modest effects expected."}]}
    ))
    prov = boost_rigor(corpus, draft.fragments, None, TraceRecorder(), 0, topic="t")
    aim = draft.fragments[0].provides["aims"][0]
    assert "[literature:7]" not in aim.pitfalls_alternatives and "Underpowered cohorts" in aim.pitfalls_alternatives
    assert prov[0]["drawn_from"] == ["literature:7"]  # the cite survived as provenance, validated ∈ corpus


# === BOOSTER-POLISH item B — drawn_from id-normalization (provenance-only) =========================


def test_normalize_drawn_from_recovers_bare_and_misprefixed():
    from cua.roles._rigor_booster import _normalize_drawn_from
    corpus_ids = {"literature:42166327", "grant:R01NS058487", "trial:NCT01"}
    valid, dropped = _normalize_drawn_from(
        ["R01NS058487",          # bare (no prefix) → uniquely recovers grant:R01NS058487
         "grant:42166327",       # mis-prefixed (real is literature:42166327) → recovered
         "trial:NCT01",          # already canonical → kept
         "literature:99999",     # unknown source_id → dropped
         "grant:R01NS058487"],   # duplicate of the recovered → de-duped
        corpus_ids,
    )
    assert valid == ["grant:R01NS058487", "literature:42166327", "trial:NCT01"]  # recovered → FULL canonical ids
    assert dropped == ["literature:99999"]


def test_normalize_drawn_from_drops_ambiguous():
    from cua.roles._rigor_booster import _normalize_drawn_from
    # source_id "7" is shared by two corpus ids → ambiguous → never guessed (dropped, the conservative default)
    valid, dropped = _normalize_drawn_from(["7", "NCT9"], {"literature:7", "grant:7", "trial:NCT9"})
    assert valid == ["trial:NCT9"] and dropped == ["7"]


def test_boost_recovers_bare_provenance_end_to_end(monkeypatch):
    """The road-not-taken link is no longer lost when the model drops the prefix: a bare/mis-prefixed
    drawn_from token that uniquely matches a corpus source is recovered into the canonical id."""
    _live(monkeypatch)
    corpus = _corpus_with_view(
        [_paper("literature:42166327"), _paper("grant:R01NS058487", kf="comparable cohort")],
        selected_ids=["literature:42166327"],
    )
    draft = _draft(_aim_fragment("aim-1", "literature:42166327"))
    _boost_via_complete(monkeypatch, [
        _AimRigor(aim_id="aim-1", pitfalls_alternatives="P.", expected_outcomes="O.",
                  drawn_from_ids=["R01NS058487"]),  # bare — real id is grant:R01NS058487
    ])
    prov = boost_rigor(corpus, draft.fragments, None, TraceRecorder(), 0, topic="t")
    assert prov[0]["drawn_from"] == ["grant:R01NS058487"]   # recovered to the FULL canonical id
    assert prov[0]["dropped_non_corpus"] == []


# === BOOSTER-POLISH item A — run_db --no-booster wiring =============================================


def test_no_booster_builds_reviser_without_corpus():
    """`run_db`'s orchestrator builder threads `corpus` to the Reviser: corpus=None (the --no-booster arm)
    → `_corpus is None` → the booster is inert (gated, proven by test_no_corpus_inert_even_when_live);
    corpus present (default) → the booster is active."""
    from cua.nih.run_db import _build_orchestrator
    off = _build_orchestrator(None, corpus=None, topic="t")
    on = _build_orchestrator(None, corpus=SourceSet([_paper("p1")]), topic="t")
    assert off.reviser._corpus is None          # --no-booster → inert
    assert on.reviser._corpus is not None        # default → boost


def test_boost_records_to_content_capture(monkeypatch):
    """CONTENT-CAP-ALL D: when a content_capture sink is threaded in, the booster records its per-round
    provenance + subset stats (None-guarded — absent the sink it is a pure no-op, proven above)."""
    from cua.capture import ContentCapture
    _live(monkeypatch)
    corpus = _corpus_with_view([_paper("p1"), _paper("u9", kf="comparable"), _paper("u8", kf="another distinct comparable")],
                               selected_ids=["p1"], contra_ids=["u9"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    _boost_via_complete(monkeypatch, [
        _AimRigor(aim_id="aim-1", pitfalls_alternatives="Real pitfalls.", expected_outcomes="Quantified.", drawn_from_ids=["u9", "FAKE-1"]),
    ])
    cap = ContentCapture()
    boost_rigor(corpus, draft.fragments, None, TraceRecorder(), 1, topic="t", content_capture=cap)
    assert len(cap.booster) == 1
    b = cap.booster[0]
    assert b["round"] == 1 and b["subset_size"] == 2 and b["unselected_total"] == 2 and b["cap"] == 24
    assert b["aims"] == [{"aim_id": "aim-1", "drawn_from": ["u9"], "dropped_non_corpus": ["FAKE-1"]}]


def test_boost_noop_when_no_unselected(monkeypatch):
    """No un-selected papers (all selected) → the booster returns without any LLM call (no trace event)."""
    _live(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subset → no call")))
    corpus = _corpus_with_view([_paper("p1")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    rec = TraceRecorder()
    assert boost_rigor(corpus, draft.fragments, None, rec, 0, topic="t") == []
    assert len(rec.trace) == 0


# === trace: exactly one reviser_booster:live event per call =========================================


def test_boost_records_one_event(monkeypatch):
    _live(monkeypatch)
    resp = _tool_response({"aims": [{"aim_id": "aim-1", "pitfalls_alternatives": "P", "expected_outcomes": "O", "drawn_from_ids": ["u9"]}]})
    resp.content[0].name = llm._tool_name(_RigorBoost)
    monkeypatch.setattr(llm, "_call_model", lambda request: resp())
    corpus = _corpus_with_view([_paper("p1"), _paper("u9", kf="comparable")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    rec = TraceRecorder()
    boost_rigor(corpus, draft.fragments, None, rec, round=2, topic="t")
    assert len(rec.trace) == 1
    ev = rec.trace[0]
    assert ev.role == "reviser_booster" and ev.output_ref == "reviser_booster:live"
    assert ev.model == "claude-opus-4-8" and ev.round == 2


# === through the Reviser live path: booster THEN hedge; best-effort on failure =======================


def _schema_call_model(*, rigor_payload, hedged_payload, fail_booster=False):
    """A schema-aware `_call_model`: routes the `_RigorBoost` tool to the booster payload (or a malformed
    one to force a persistent failure) and the `_RevisedDraft` tool to the hedge payload."""
    from cua.roles.reviser import _RevisedDraft

    def _call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_RigorBoost):
            # missing the required prose fields → a ValidationError on every attempt → LiveStructuredOutputError
            payload = {"aims": [{"aim_id": "aim-1"}]} if fail_booster else rigor_payload
        elif tool == llm._tool_name(_RevisedDraft):
            payload = hedged_payload
        else:
            payload = {}

        class _Block:
            type = "tool_use"
            name = tool
            input = payload

        class _Usage:
            input_tokens = 700
            output_tokens = 120

        class _Resp:
            content = [_Block()]
            stop_reason = "tool_use"
            usage = _Usage()

        return _Resp()

    return _call


def test_revise_live_runs_booster_then_hedge(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _schema_call_model(
        rigor_payload={"aims": [{"aim_id": "aim-1", "pitfalls_alternatives": "Substantive pitfalls.", "expected_outcomes": "Quantified outcomes.", "drawn_from_ids": ["u9"]}]},
        hedged_payload={"hedged_claims": []},
    ))
    corpus = _corpus_with_view([_paper("p1"), _paper("u9", kf="comparable")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    from cua.roles import InternalCritic
    crit = InternalCritic().critique(Grounder().ground(draft, corpus)[0], [], EvidenceScores(), [])
    rec = TraceRecorder()
    revised = Reviser(corpus=corpus, topic="t").revise(draft, crit, [], [], recorder=rec, round=0)

    aim = revised.fragments[0].provides["aims"][0]
    assert aim.pitfalls_alternatives == "Substantive pitfalls." and aim.expected_outcomes == "Quantified outcomes."
    roles = [e.output_ref for e in rec.trace]
    assert "reviser_booster:live" in roles and "reviser:live" in roles  # both calls happened, in that order
    assert roles.index("reviser_booster:live") < roles.index("reviser:live")


def test_booster_failure_is_best_effort(monkeypatch):
    """A persistent booster structured-output failure must NOT break the revise: the hedge still runs and
    the aims are left unchanged (the booster is enrichment, never an integrity gate)."""
    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _schema_call_model(
        rigor_payload=None, hedged_payload={"hedged_claims": []}, fail_booster=True,
    ))
    corpus = _corpus_with_view([_paper("p1"), _paper("u9", kf="comparable")], selected_ids=["p1"])
    draft = _draft(_aim_fragment("aim-1", "p1"))
    from cua.roles import InternalCritic
    crit = InternalCritic().critique(Grounder().ground(draft, corpus)[0], [], EvidenceScores(), [])
    revised = Reviser(corpus=corpus, topic="t").revise(draft, crit, [], [], recorder=TraceRecorder(), round=0)
    aim = revised.fragments[0].provides["aims"][0]
    assert "filler" in aim.pitfalls_alternatives  # unchanged — the booster failure was swallowed, run completed


# === full Orchestrator loop: the booster's enriched aims reach the assembled Proposal ===============


def _e2e_corpus() -> SourceSet:
    """A small corpus: p1/p2 are SELECTED (writer view); u9 is the un-selected paper the booster mines."""
    corpus = SourceSet([
        _paper("p1", kf="microglial activation tracks progression"),
        _paper("p2", kf="GCase modulation in a phase 2 cohort"),
        _paper("u9", kf="comparable cohort was underpowered at n<40"),
    ])
    setattr(corpus, WRITER_VIEW_ATTR, [_ViewRow("p1"), _ViewRow("p2")])
    setattr(corpus, CONTRADICTION_IDS_ATTR, {"u9"})
    return corpus


def _e2e_call_model_with_booster():
    """Schema-aware `_call_model` for ALL live roles INCLUDING the booster. The Critic forces a revise
    (so the booster + hedge run); the booster rewrites every aim's pitfalls/outcomes drawing on u9."""
    from cua.roles.aim_architect import _AimExpansion
    from cua.roles.critic import _CritiqueOut
    from cua.roles.reviser import _RevisedDraft
    from cua.roles.synthesizer import _AimStub, _CitedClaim, _F1Argument

    def _synth():
        return _F1Argument(
            gap="A specific barrier remains unresolved.",
            significance=_CitedClaim(text="We will investigate whether microglia inform early intervention.", cited_corpus_ids=["p1"]),
            central_hypothesis=_CitedClaim(text="We will examine whether GCase modulation alters the outcome.", cited_corpus_ids=["p2"]),
            innovation=_CitedClaim(text="A specific departure from symptomatic-only practice.", cited_corpus_ids=[]),
            aims=[_AimStub(title="Aim: microglia", cited_corpus_ids=["p1"]), _AimStub(title="Aim: GCase", cited_corpus_ids=["p2"])],
        ).model_dump()

    def _aim():
        return _AimExpansion(
            hypothesis="We will examine whether the targeted mechanism alters the clinical outcome.",
            rationale="Grounded in the cited corpus key findings.",
            approach="Methods and design specified to a rigor-judgable level.",
            expected_outcomes="Outcomes tied to the hypothesis (filler).",
            pitfalls_alternatives="Pitfalls and alternatives (filler).",
            citation_ids=["p1"],
        ).model_dump()

    def _boost():
        return {"aims": [
            {"aim_id": aid,
             "pitfalls_alternatives": "Comparable cohorts were underpowered (n<40); alternative: a pre-registered sequential design.",
             "expected_outcomes": "Expect a 20-30% directional effect, consistent with comparable underpowered work.",
             "drawn_from_ids": ["u9"]}
            for aid in ("aim-1", "aim-2", "aim-3")  # superset; only aims present in the draft are applied
        ]}

    def _call(request):
        tool = request["tool_choice"]["name"]
        if tool == llm._tool_name(_F1Argument):
            payload = _synth()
        elif tool == llm._tool_name(_CritiqueOut):
            # f2=4 (< the bar of 5) forces a revise WITHOUT any overclaim/orphan — so the booster runs each
            # round while inv-1/inv-3 stay clean (the honest case: the gap is rigor CONTENT, not integrity).
            payload = {"f1": {"score": 7, "justification": "j"}, "f2": {"score": 4, "justification": "pitfalls/outcomes thin"},
                       "f3": {"score": 7, "justification": "j"}, "segment_scores": [], "decision": "revise", "flagged_obligation_ids": []}
        elif tool == llm._tool_name(_RigorBoost):
            payload = _boost()
        elif tool == llm._tool_name(_RevisedDraft):
            payload = {"hedged_claims": []}
        else:
            payload = _aim()

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


def test_end_to_end_booster_enriches_assembled_proposal(monkeypatch):
    from cua.nih.grant_call import default_grant_call
    from cua.nih.proposal import Proposal
    from cua.nih.run import RUN_CONFIG
    from cua.nih.task import NIHGrantTask
    from cua.orchestrator import Orchestrator
    from cua.roles import BlueprintPlanner, InternalCritic

    _live(monkeypatch)
    monkeypatch.setattr(llm, "_call_model", _e2e_call_model_with_booster())
    corpus = _e2e_corpus()
    task = NIHGrantTask(grant_call=default_grant_call(), corpus=corpus, evidence=EvidenceScores())
    orch = Orchestrator(
        conditioner=BlueprintPlanner(), critic=InternalCritic(),
        reviser=Reviser(corpus=corpus, topic="t"), selection_scorer=None,
    )
    artifact, trace, audit = orch.run(task, RUN_CONFIG)

    assert isinstance(artifact, Proposal)                         # §2.1 structural envelope held with enriched aims
    assert artifact.aims, "expected at least one aim"
    for aim in artifact.aims:
        assert "underpowered" in aim.pitfalls_alternatives        # the booster's substance reached the Proposal
        assert "directional effect" in aim.expected_outcomes
        assert "filler" not in aim.pitfalls_alternatives
    assert audit.grounding_report.all_in_source_set               # inv-1: every cite still ∈ corpus
    assert all(r.ok for r in audit.overclaim_check)               # inv-3: nothing overclaims (booster content hedged)
    # the booster fired (at least once) on the revise path, as its own live event
    assert any(e.output_ref == "reviser_booster:live" for e in trace)
    # u9 was NOT injected into the references deck / claim graph (provenance only — claims untouched)
    assert "u9" not in {r.id for r in artifact.references}
