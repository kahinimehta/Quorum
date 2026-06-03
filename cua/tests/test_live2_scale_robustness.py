"""LIVE-2/0 scale-robustness tests — writer structured-output at full corpus scale.

`build/live/LIVE-2-scale-robustness_relay.md`: at ~400 papers the Synthesizer's `_F1Argument` came back
MISSING required fields and the LIVE-0 retry couldn't recover a PERSISTENT omission. Four live-path-only
fixes, all proven here (offline byte-identical — these never touch the surrogate path):
(1) the writer prompts serialize a BOUNDED findings view + the FULL citable id-list (inv-1 unchanged);
(2) the writers raise `max_tokens` (Opus xhigh + a full structured argument needs headroom);
(3) the retry re-prompt NAMES the missing/invalid fields explicitly;
(4) a persistent failure raises `LiveStructuredOutputError` with diagnostics (stop_reason → truncation
    vs omission, the named fields, a raw-input snippet).

Owner: LIVE-2 scale-robustness (builder 1). No network, no real key (a dummy key only flips is_live()).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

import cua.llm as llm
from cua.nih.framework import Paper
from cua.nih.grant_call import default_grant_call
from cua.nih.obligations import compile_obligations
from cua.nih.ingestion import IngestionConfig, attach_writer_view, ingest
from cua.roles import _corpus
from cua.roles._corpus import FINDINGS_CAP, findings_block, id_list_block, recent_sources
from cua.roles.aim_architect import AimArchitect, _aim_prompt
from cua.roles.synthesizer import ArgumentSynthesizer, _AimStub, _CitedClaim, _F1Argument, _live_prompt
from cua.trace import TraceRecorder
from cua.types import Draft, EvidenceScores, SourceSet


# --- fixtures -------------------------------------------------------------------------------------


def _big_corpus(n: int = 150) -> SourceSet:
    """A scale corpus: `n` papers with strictly increasing years (1900+i) → p{n-1} is the most-recent."""
    return SourceSet([
        Paper(id=f"p{i}", authors=[], year=1900 + i, title=f"T{i}", venue="J", resolvable_id=f"10/{i}", key_finding=f"finding{i}", real=True)
        for i in range(n)
    ])


class _Task:
    grant_call = default_grant_call()


def _obligations():
    return compile_obligations(_Task())


def _live(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")


def _sample_f1() -> _F1Argument:
    return _F1Argument(
        gap="A gap.",
        significance=_CitedClaim(text="We will investigate whether X relates to Y.", cited_corpus_ids=["p149"]),
        central_hypothesis=_CitedClaim(text="We will examine whether Z.", cited_corpus_ids=["p148"]),
        innovation=_CitedClaim(text="A departure.", cited_corpus_ids=[]),
        aims=[_AimStub(title="Aim 1", cited_corpus_ids=["p0"])],  # cites a LONG-TAIL id (finding not shown)
    )


def _resp(payload: dict, tool: str, *, stop_reason: str = "tool_use", usage=(10, 10)):
    class _Block:
        type = "tool_use"
        name = tool
        input = payload

    class _Usage:
        input_tokens, output_tokens = usage

    class _Resp:
        content = [_Block()]

    r = _Resp()
    r.stop_reason = stop_reason
    r.usage = _Usage()
    return r


# === (1) bounded corpus — the bound is now the INGESTION top-K (INGEST-1 v2 supersedes the recency cap) ===
# The LIVE-2 interim `FINDINGS_CAP` recency cap is SUPERSEDED: `findings_block` now serializes the Ingestion
# Layer's attached `writer_view` (the diversified top-K). `recent_sources` is retained as a recency helper.


def test_recent_sources_caps_to_most_recent_by_year():
    corpus = _big_corpus(150)
    recent = recent_sources(corpus, FINDINGS_CAP)
    assert len(recent) == FINDINGS_CAP                          # the recency helper still caps at 120 of 150
    ids = {p.id for p in recent}
    assert "p149" in ids and "p30" in ids                      # the 120 most-recent (years 1930..2049)
    assert "p0" not in ids and "p29" not in ids                # the oldest 30 are dropped from the view


def test_findings_block_uses_ingestion_view_id_list_complete():
    """INGEST-1 v2: with NO ingestion attached, `findings_block` shows ALL findings (the recency cap is
    gone); once the Ingestion Layer attaches a bounded `writer_view`, only the diversified top-K is shown —
    while `id_list_block` stays the FULL corpus (inv-1 citability, ID-PRESERVING)."""
    corpus = _big_corpus(150)
    assert "finding0" in findings_block(corpus) and "finding149" in findings_block(corpus)  # no recency cap
    attach_writer_view(corpus, ingest(corpus, topic="T149 T148", config=IngestionConfig(top_k=40)))
    findings = findings_block(corpus)
    ids = id_list_block(corpus)
    assert findings.count("\n") + 1 <= 40                      # bounded to the ingestion top-K view
    assert "finding149" in findings and "finding0" not in findings
    # FULL id-list: EVERY corpus id is citable (inv-1 unchanged — even ids whose finding isn't shown)
    assert all(p.id in ids for p in corpus.sources)
    assert "p0" in ids and "p149" in ids


def test_findings_block_handles_missing_year():
    # a None/absent year sinks to the end rather than crashing the sort
    corpus = SourceSet([
        Paper(id="a", authors=[], year=None, title="A", venue="J", resolvable_id="x", key_finding="ka", real=True),
        Paper(id="b", authors=[], year=2020, title="B", venue="J", resolvable_id="y", key_finding="kb", real=True),
    ])
    assert recent_sources(corpus, 1)[0].id == "b"               # the dated one ranks first
    assert "a" in id_list_block(corpus)                         # still citable


# === (1) the writer prompts carry the bounded view + the full id-list =============================


def test_synth_prompt_bounds_findings_keeps_full_id_list():
    corpus = _big_corpus(150)
    attach_writer_view(corpus, ingest(corpus, topic="Parkinson's disease", config=IngestionConfig(top_k=40)))
    prompt = _live_prompt("Parkinson's disease", corpus, _obligations(), 3)
    assert "finding149" in prompt and "finding0" not in prompt  # bounded to the ingestion top-K view
    assert "FULL CITABLE IDS" in prompt
    assert "p0" in prompt and "p149" in prompt                  # the full id-list (inv-1 citability intact)
    # the cite rule points at the full id-list, not the (bounded) findings block
    assert "Cite ONLY ids from the FULL CITABLE IDS list" in prompt


def test_aim_prompt_bounds_findings_keeps_full_id_list():
    corpus = _big_corpus(150)
    attach_writer_view(corpus, ingest(corpus, topic="Parkinson's disease", config=IngestionConfig(top_k=40)))
    prompt = _aim_prompt("Parkinson's disease", "Aim 1", ["p0"], corpus, _obligations())
    # the aim's PRE-ASSIGNED evidence (p0) is shown in FULL even though it's long-tail / not in the top-K view
    assert "[p0]" in prompt and "finding0" in prompt
    assert "finding149" in prompt                              # the bounded top-K corpus findings
    assert "FULL CITABLE IDS" in prompt and "p149" in prompt
    assert "Cite ONLY ids from the FULL CITABLE IDS list" in prompt


def test_bounding_is_prompt_only_sourceset_untouched():
    corpus = _big_corpus(150)
    _live_prompt("t", corpus, _obligations(), 3)
    assert len(corpus.sources) == 150                           # the SourceSet is never mutated (principle 6)


# === (2) the writers pass a bounded max_tokens (INGEST-1 v2 lowered it from 32768 → 16384) ==========


def test_synth_passes_writer_max_tokens(monkeypatch):
    _live(monkeypatch)
    captured = {}
    monkeypatch.setattr(llm, "complete", lambda config, **kw: captured.update(kw) or _sample_f1())
    inputs = {"corpus": _big_corpus(150), "grant_call": default_grant_call(), "evidence_scores": EvidenceScores(),
              "_recorder": TraceRecorder(), "_round": 0}
    ArgumentSynthesizer().produce(_obligations(), inputs, Draft(), None)
    assert captured["max_tokens"] == 16384                      # INGEST-1 v2: lowered from 32768 (bounded view fits)


def test_aim_passes_writer_max_tokens(monkeypatch):
    _live(monkeypatch)
    captured = {}
    from cua.roles.aim_architect import _AimExpansion
    aim_out = _AimExpansion(hypothesis="We will examine whether M.", rationale="r", approach="a",
                            expected_outcomes="e", pitfalls_alternatives="p", citation_ids=["p0"])
    monkeypatch.setattr(llm, "complete", lambda config, **kw: captured.update(kw) or aim_out)
    inputs = {"corpus": _big_corpus(150), "grant_call": default_grant_call(), "evidence_scores": EvidenceScores(),
              "_recorder": TraceRecorder(), "_round": 0}
    AimArchitect().produce(_obligations(), inputs, Draft(), {"id": "aim-1", "title": "Aim 1", "evidence_keys": ["p0"]})
    assert captured["max_tokens"] == 16384                      # INGEST-1 v2: lowered from 32768 (bounded view fits)


# === (3) the retry re-prompt names the missing fields =============================================


class _Two(BaseModel):
    title: str
    count: int


def test_feedback_turns_names_missing_fields():
    try:
        _Two.model_validate({"title": "t"})  # 'count' missing
    except ValidationError as exc:
        err = exc
    tool = llm._tool_name(_Two)
    turns = llm._feedback_turns(_resp({"title": "t"}, tool), tool, err)
    tr = turns[1]["content"][0]
    assert tr["is_error"] is True
    assert "count" in tr["content"] and "EVERY field" in tr["content"]   # names the field + demands all


# === (4) persistent-omission failure → LiveStructuredOutputError with diagnostics ================


def test_persistent_omission_raises_diagnostics_naming_fields(monkeypatch):
    """The `full1` hard-fail reproduced: `central_hypothesis` + `innovation` persistently absent. The
    retry can't recover → a diagnostic error that NAMES both fields + the stop_reason, chaining the cause."""
    _live(monkeypatch)
    tool = llm._tool_name(_F1Argument)
    # gap + significance + aims present; central_hypothesis + innovation OMITTED every attempt
    payload = {"gap": "g", "significance": {"text": "We will investigate whether X.", "cited_corpus_ids": ["p1"]}, "aims": []}
    calls = {"n": 0}

    def call(request):
        calls["n"] += 1
        return _resp(payload, tool, stop_reason="end_turn")

    monkeypatch.setattr(llm, "_call_model", call)
    with pytest.raises(llm.LiveStructuredOutputError) as ei:
        llm.complete(ArgumentSynthesizer.config, system="s", user="u", schema=_F1Argument,
                     trace_role="synthesizer", recorder=TraceRecorder())
    msg = str(ei.value)
    assert calls["n"] == 3                                      # retried to the cap
    assert "central_hypothesis" in msg and "innovation" in msg # both omissions named
    assert "stop_reason=end_turn" in msg
    assert isinstance(ei.value.__cause__, ValidationError)


def test_truncation_hint_when_stop_reason_max_tokens(monkeypatch):
    """When the omission coincides with `stop_reason=max_tokens`, the diagnostic flags TRUNCATION — the
    operator's signal to raise the budget rather than chase an omission."""
    _live(monkeypatch)
    tool = llm._tool_name(_F1Argument)
    payload = {"gap": "g", "significance": {"text": "t", "cited_corpus_ids": []}, "aims": []}  # missing central/innov

    monkeypatch.setattr(llm, "_call_model", lambda request: _resp(payload, tool, stop_reason="max_tokens"))
    with pytest.raises(llm.LiveStructuredOutputError) as ei:
        llm.complete(ArgumentSynthesizer.config, system="s", user="u", schema=_F1Argument,
                     trace_role="synthesizer", recorder=TraceRecorder())
    msg = str(ei.value)
    assert "TRUNCATION" in msg and "max_tokens" in msg
    assert "tool_use input:" in msg                             # the raw snippet is included


def test_diagnostics_snippet_when_no_tool_block(monkeypatch):
    _live(monkeypatch)

    class _TextBlock:
        type = "text"
        text = "I cannot comply."

    class _Resp:
        content = [_TextBlock()]
        stop_reason = "end_turn"
        usage = None

    monkeypatch.setattr(llm, "_call_model", lambda request: _Resp())
    with pytest.raises(llm.LiveStructuredOutputError) as ei:
        llm.complete(ArgumentSynthesizer.config, system="s", user="u", schema=_F1Argument,
                     trace_role="synthesizer", recorder=TraceRecorder())
    assert "no tool_use block" in str(ei.value)
    assert isinstance(ei.value.__cause__, llm.LiveProtocolError)
