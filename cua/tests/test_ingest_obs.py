"""INGEST-OBS — live `run_db` progress verbosity (observability CR; STDERR + live-only).

`build/live/INGEST-OBS_relay.md`: a full live `run_db` is silent for minutes. Two surgical, byte-identical-
safe changes: (1) `run_db` prints the `[ingest]` summary UP-FRONT, before the orchestrator; (2) `llm.complete()`
emits a per-call START + FINISH line to STDERR (live-only — `complete()` returns `LiveUnavailable` before any
progress line when not `is_live()`, so OFFLINE emits nothing and the byte oracle is untouched). Gated by
`CUA_VERBOSE` (default ON).

Owner: INGEST-OBS (builder 1). No network, no real key (a dummy key only flips `is_live()`); `_call_model` mocked.
"""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import BaseModel

from cua import llm
from cua.config import RoleConfig
from cua.trace import TraceRecorder

OPUS = RoleConfig(model_id="claude-opus-4-8", effort="high")


class _S(BaseModel):
    x: int


def _mock_live(monkeypatch, *, tokens=(10, 20)):
    """Flip is_live() with a DUMMY key + mock the network seam to return a valid forced tool-use response."""
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    class _Blk:
        type = "tool_use"
        name = llm._tool_name(_S)
        input = {"x": 1}

    class _U:
        input_tokens, output_tokens = tokens

    class _R:
        content = [_Blk()]
        stop_reason = "tool_use"
        usage = _U()

    monkeypatch.setattr(llm, "_call_model", lambda request: _R())


# === per-call STDERR progress (live-only) ========================================================


def test_live_progress_start_and_finish_to_stderr(monkeypatch, capsys):
    _mock_live(monkeypatch)
    out = llm.complete(OPUS, system="s", user="u", schema=_S, trace_role="synthesizer", recorder=TraceRecorder())
    assert out.x == 1
    cap = capsys.readouterr()
    # START + FINISH lines, both on STDERR, naming role + model + round, with tokens/attempts/elapsed
    assert "[live] synthesizer claude-opus-4-8 round=0 start" in cap.err
    assert "[live] synthesizer claude-opus-4-8 done 30 tok, 1 attempt(s)," in cap.err
    assert cap.err.rstrip().endswith("s")              # elapsed seconds suffix
    assert cap.out == ""                                # nothing on STDOUT (the oracle channel)


def test_finish_line_reports_attempts_and_failed(monkeypatch, capsys):
    # a persistent omission → 3 attempts, FAILED marker in the finish line (still STDERR-only)
    monkeypatch.setenv("CUA_LIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")

    class _Blk:
        type = "tool_use"
        name = llm._tool_name(_S)
        input = {}  # missing required 'x' every attempt

    class _U:
        input_tokens, output_tokens = (5, 5)

    class _R:
        content = [_Blk()]
        stop_reason = "end_turn"
        usage = _U()

    monkeypatch.setattr(llm, "_call_model", lambda request: _R())
    with pytest.raises(llm.LiveStructuredOutputError):
        llm.complete(OPUS, system="s", user="u", schema=_S, trace_role="critic", recorder=TraceRecorder())
    cap = capsys.readouterr()
    assert "FAILED:ValidationError" in cap.err and "3 attempt(s)" in cap.err
    assert cap.out == ""


# === the off-switch + the offline silence ========================================================


def test_cua_verbose_off_silences_progress(monkeypatch, capsys):
    _mock_live(monkeypatch)
    monkeypatch.setenv("CUA_VERBOSE", "0")
    llm.complete(OPUS, system="s", user="u", schema=_S, trace_role="r", recorder=TraceRecorder())
    assert capsys.readouterr().err == ""                # silenced, but the call still ran


def test_offline_emits_no_progress(monkeypatch, capsys):
    # complete() is LIVE-ONLY: with CUA_LIVE unset it raises LiveUnavailable BEFORE any progress line.
    monkeypatch.delenv("CUA_LIVE", raising=False)
    with pytest.raises(llm.LiveUnavailable):
        llm.complete(OPUS, system="s", user="u", schema=_S, trace_role="r", recorder=TraceRecorder())
    cap = capsys.readouterr()
    assert cap.err == "" and cap.out == ""              # OFFLINE stays byte-identical (no new output)


def test_verbose_default_on_explicit_off_values(monkeypatch):
    monkeypatch.delenv("CUA_VERBOSE", raising=False)
    assert llm._verbose() is True                       # default ON
    for off in ("0", "false", "False", "no", "off", ""):
        monkeypatch.setenv("CUA_VERBOSE", off)
        assert llm._verbose() is False
    for on in ("1", "true", "yes"):
        monkeypatch.setenv("CUA_VERBOSE", on)
        assert llm._verbose() is True


# === run_db prints [ingest] UP-FRONT (before the orchestrator's [ok]) ============================


def _mini_db(path: str) -> None:
    """A 2-row neurodiscover-shaped SQLite the adapter can read (only the columns it SELECTs)."""
    c = sqlite3.connect(path)
    try:
        c.executescript(
            """
            CREATE TABLE evidence(evidence_id INTEGER PRIMARY KEY, source_type TEXT, source_id TEXT, title TEXT,
                year INTEGER, publication_year INTEGER, venue TEXT, key_result TEXT, evidence_snippet TEXT,
                abstract TEXT, doi TEXT, study_type TEXT, sample_size INTEGER, access_status TEXT);
            CREATE TABLE subgroups(subgroup_id INTEGER PRIMARY KEY, name TEXT, defining_features TEXT, notes TEXT);
            CREATE TABLE treatment_connections(connection_id INTEGER PRIMARY KEY, subgroup_id INTEGER,
                mechanism TEXT, treatment TEXT, evidence_strength REAL);
            CREATE TABLE connection_evidence(connection_id INTEGER, evidence_id INTEGER);
            """
        )
        c.executemany(
            "INSERT INTO evidence(evidence_id,source_type,source_id,title,year,publication_year,venue,"
            "key_result,evidence_snippet,abstract,doi,study_type,sample_size,access_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(1, "literature", "100", "A", 2020, None, "J", "gcase activity correlates with progression", None, None, "10/100", "cohort", 50, None),
             (2, "trial", "200", "B", 2023, None, "J", "phase 2 trial of a gcase chaperone", None, None, "NCT200", "phase 2", 30, None)],
        )
        c.execute("INSERT INTO subgroups(subgroup_id,name,defining_features,notes) VALUES (1,'g','f','n')")
        c.execute("INSERT INTO treatment_connections(connection_id,subgroup_id,mechanism,treatment,evidence_strength) VALUES (1,1,'GCase','chaperone',NULL)")
        c.executemany("INSERT INTO connection_evidence(connection_id,evidence_id) VALUES (?,?)", [(1, 1), (1, 2)])
        c.commit()
    finally:
        c.close()


def test_run_db_prints_ingest_summary_before_ok(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)          # offline (surrogate) — deterministic, no network
    db = tmp_path / "m.db"
    _mini_db(str(db))
    from cua.nih.run_db import run_db

    rc = run_db(db=str(db), run_id="obs", out_dir=tmp_path / "o")
    assert rc == 0
    out = capsys.readouterr().out
    assert "[ingest]" in out and "[ok]" in out
    assert out.index("[ingest]") < out.index("[ok]")      # up-front — before the (long) orchestrator phase
