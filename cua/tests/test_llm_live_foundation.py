"""LIVE-0 unit tests — `cua.llm` live client foundation (offline; no network, no real key).

Proves the operator's LIVE-0 done-criteria WITHOUT a network call: surrogates stay the default
(`is_live()` False, no `anthropic` import on `import cua.llm`); config→API mapping is correct (Opus →
`output_config.effort`, no temperature; Sonnet/Haiku → temperature); forced tool-use returns a
pydantic-validated instance and malformed output raises; one call → one TraceEvent; `LiveUnavailable`
fallback fires when offline. The single network seam `_call_model` is monkeypatched — `anthropic` is
never imported and no key is ever used (the dummy `ANTHROPIC_API_KEY` only flips `is_live()`).

Owner: LIVE-0 (builder 1). Governing: contracts.md §1.8/§1.10; live-bodies wave decisions #1/#2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from cua import llm
from cua.config import RoleConfig
from cua.trace import TraceRecorder

OPUS = RoleConfig(model_id="claude-opus-4-8", effort="xhigh")
SONNET = RoleConfig(model_id="claude-sonnet-4-6", temperature=0.0)
HAIKU = RoleConfig(model_id="claude-haiku-4-5-20251001", temperature=0.1)


class _Sample(BaseModel):
    title: str
    count: int


# --- minimal stand-ins for the Anthropic Message shape (so no SDK/network is touched) -------------


class _Block:
    def __init__(self, type, name=None, input=None):
        self.type, self.name, self.input = type, name, input


class _Usage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens


class _Response:
    def __init__(self, content, stop_reason="tool_use", usage=None):
        self.content, self.stop_reason, self.usage = content, stop_reason, usage


def _go_live(monkeypatch):
    """Flip is_live() True with a DUMMY key (never used — _call_model is always patched)."""
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-not-a-real-key")


def _tool_block(schema, args):
    return _Block("tool_use", name=llm._tool_name(schema), input=args)


# --- offline default: surrogates stay the default -------------------------------------------------


def test_is_live_default_false(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.is_live() is False


def test_is_live_requires_both_and_nonempty(monkeypatch):
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.is_live() is False                 # key missing
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    assert llm.is_live() is True                  # both present
    monkeypatch.setenv("CUA_LIVE", "")            # empty == not set
    assert llm.is_live() is False


def test_import_pulls_no_anthropic_and_no_network():
    # Fresh interpreter: importing cua.llm must not import `anthropic` (lazy seam) nor hit the network.
    src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    env.pop("CUA_LIVE", None)
    code = (
        "import sys; import cua.llm; "
        "assert 'anthropic' not in sys.modules, "
        "sorted(m for m in sys.modules if 'anthropic' in m); "
        "assert cua.llm.is_live() is False"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr


# --- config → API mapping (pure; no network) ------------------------------------------------------


def test_opus_maps_to_effort_no_temperature():
    req = llm._build_request(OPUS, system="s", user="u", schema=_Sample, tool_name="T", max_tokens=99)
    assert req["output_config"] == {"effort": "xhigh"}   # Opus reasoning depth
    assert "temperature" not in req                       # Opus 4.x rejects temperature
    assert req["model"] == "claude-opus-4-8"
    assert req["max_tokens"] == 99
    # forced tool-use → structured output (wave decision #1)
    assert req["tool_choice"] == {"type": "tool", "name": "T"}
    assert req["tools"][0]["name"] == "T"
    assert req["tools"][0]["input_schema"]["type"] == "object"


def test_sonnet_and_haiku_map_to_temperature_no_effort():
    for cfg, temp in ((SONNET, 0.0), (HAIKU, 0.1)):
        req = llm._build_request(cfg, system="s", user="u", schema=_Sample, tool_name="T", max_tokens=10)
        assert req["temperature"] == temp                # included even when 0.0
        assert "output_config" not in req                # never effort for Sonnet/Haiku


def test_sampling_descriptor_flows_into_trace_label():
    assert OPUS.sampling_descriptor() == "effort=xhigh"
    assert SONNET.sampling_descriptor() == "temp=0.0"


# --- forced tool-use returns a validated instance; malformed raises -------------------------------


def test_complete_returns_validated_instance_and_one_trace_event(monkeypatch):
    _go_live(monkeypatch)
    captured = {}

    def fake_call(request):
        captured["request"] = request
        return _Response([_tool_block(_Sample, {"title": "t", "count": 2})], usage=_Usage(10, 20))

    monkeypatch.setattr(llm, "_call_model", fake_call)
    rec = TraceRecorder()
    out = llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="critic", recorder=rec, round=2)

    assert isinstance(out, _Sample) and out.title == "t" and out.count == 2
    # the request that reached the (mocked) API carried the forced tool + Opus effort
    assert captured["request"]["tool_choice"]["type"] == "tool"
    assert captured["request"]["output_config"] == {"effort": "xhigh"}
    # exactly one TraceEvent, with the right role + sampling + real token usage
    assert len(rec.trace) == 1
    ev = rec.trace[0]
    assert ev.role == "critic"
    assert ev.model == "claude-opus-4-8"
    assert ev.sampling == "effort=xhigh"
    assert ev.round == 2
    assert ev.tokens == 30


def test_complete_persistent_malformed_raises_after_retry_cap(monkeypatch):
    _go_live(monkeypatch)
    # a required field is always missing → ValidationError every attempt → raise after the cap (no silent pass)
    calls = {"n": 0}

    def call(request):
        calls["n"] += 1
        return _Response([_tool_block(_Sample, {"title": "t"})], usage=_Usage(5, 5))

    monkeypatch.setattr(llm, "_call_model", call)
    rec = TraceRecorder()
    with pytest.raises(llm.LiveStructuredOutputError) as ei:
        llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="x", recorder=rec)
    assert calls["n"] == 3                                    # 1 + 2 retries, then raise
    assert len(rec.trace) == 1                                # ONE event even on failure (trace-guard holds)
    assert "FAILED" in (rec.trace[0].decision or "") and rec.trace[0].tokens == 30  # 3 × 10 summed
    # the diagnostics name the missing field + stop_reason, and chain the original ValidationError
    assert "count" in str(ei.value) and "stop_reason=" in str(ei.value)
    assert isinstance(ei.value.__cause__, ValidationError)


def test_complete_persistent_protocol_error_raises_after_retry_cap(monkeypatch):
    _go_live(monkeypatch)
    calls = {"n": 0}

    def call(request):
        calls["n"] += 1
        return _Response([_Block("text")], stop_reason="end_turn")  # never the forced tool

    monkeypatch.setattr(llm, "_call_model", call)
    rec = TraceRecorder()
    with pytest.raises(llm.LiveStructuredOutputError) as ei:
        llm.complete(SONNET, system="s", user="u", schema=_Sample, trace_role="x", recorder=rec)
    assert calls["n"] == 3
    assert len(rec.trace) == 1 and "FAILED" in (rec.trace[0].decision or "")
    # the diagnostics flag the missing tool block + stop_reason, chaining the original LiveProtocolError
    assert "no tool_use block" in str(ei.value) and "stop_reason=end_turn" in str(ei.value)
    assert isinstance(ei.value.__cause__, llm.LiveProtocolError)


def test_complete_retries_then_returns_valid_one_event(monkeypatch):
    _go_live(monkeypatch)
    seq = [
        _Response([_tool_block(_Sample, {"title": "t"})], usage=_Usage(5, 5)),               # invalid → ValidationError
        _Response([_tool_block(_Sample, {"title": "t", "count": 2})], usage=_Usage(10, 20)),  # valid on retry
    ]
    calls = {"n": 0}

    def call(request):
        i = calls["n"]; calls["n"] += 1
        return seq[i]

    monkeypatch.setattr(llm, "_call_model", call)
    rec = TraceRecorder()
    out = llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="critic", recorder=rec)
    assert isinstance(out, _Sample) and out.count == 2
    assert calls["n"] == 2                                    # retried once
    assert len(rec.trace) == 1                                # ONE event despite the retry
    assert rec.trace[0].tokens == 40                          # 10 + 30 summed across attempts
    assert "attempts=2" in (rec.trace[0].decision or "")


def test_complete_retries_on_protocol_error_then_succeeds(monkeypatch):
    _go_live(monkeypatch)
    seq = [
        _Response([_Block("text")], stop_reason="end_turn"),                                 # no tool block
        _Response([_tool_block(_Sample, {"title": "t", "count": 3})], usage=_Usage(2, 2)),   # valid on retry
    ]
    calls = {"n": 0}

    def call(request):
        i = calls["n"]; calls["n"] += 1
        return seq[i]

    monkeypatch.setattr(llm, "_call_model", call)
    rec = TraceRecorder()
    out = llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="x", recorder=rec)
    assert out.count == 3 and calls["n"] == 2 and len(rec.trace) == 1


def test_complete_first_try_valid_makes_no_extra_call(monkeypatch):
    _go_live(monkeypatch)
    calls = {"n": 0}

    def call(request):
        calls["n"] += 1
        return _Response([_tool_block(_Sample, {"title": "t", "count": 1})], usage=_Usage(10, 20))

    monkeypatch.setattr(llm, "_call_model", call)
    rec = TraceRecorder()
    out = llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="x", recorder=rec)
    assert out.count == 1 and calls["n"] == 1 and len(rec.trace) == 1
    assert "attempts=1" in (rec.trace[0].decision or "")


# --- LiveUnavailable fallback (offline) -----------------------------------------------------------


def test_complete_raises_liveunavailable_when_offline(monkeypatch):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    rec = TraceRecorder()
    with pytest.raises(llm.LiveUnavailable):
        llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="x", recorder=rec)
    assert len(rec.trace) == 0  # the surrogate path emits no live event


def test_complete_does_not_touch_network_when_offline(monkeypatch):
    # Even if a key is set, CUA_LIVE unset → LiveUnavailable BEFORE any _call_model attempt.
    monkeypatch.delenv("CUA_LIVE", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    def boom(request):
        raise AssertionError("_call_model must not be reached when offline")

    monkeypatch.setattr(llm, "_call_model", boom)
    with pytest.raises(llm.LiveUnavailable):
        llm.complete(OPUS, system="s", user="u", schema=_Sample, trace_role="x", recorder=TraceRecorder())
