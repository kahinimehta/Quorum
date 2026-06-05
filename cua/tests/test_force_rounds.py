"""FORCE-ROUNDS — `--force-rounds N`: run EXACTLY N revise rounds regardless of the pass-based stop.

`build/live/FORCE-ROUNDS_relay.md`: a fixed loop-depth compute knob (peer of `--max-rounds`) that
guarantees the revise leg — and thus the F2 booster — fires, and lets us study the loop at a set depth.
It touches the engine's §1.11 stopping rule, so the load-bearing gate is the offline byte-oracle: with
`force_rounds=None` (the default) the §1.11 pass-based path is UNCHANGED, byte-for-byte (verified at
PYTHONHASHSEED 0 AND 7). Forcing only ADDS revisions — every trust gate (the decide, inv-1/2/3) still
runs each round, so it can never bypass a check.

Owner: FORCE-ROUNDS (builder 1). Offline + deterministic (stub roles / surrogate roles; no network, no key).
"""

from __future__ import annotations

import json

from cua.nih.run import RUN_CONFIG
from cua.nih.run_db import _FORCE_ROUNDS_MAX, _run_config, main, run_db
from cua.orchestrator import Orchestrator
from cua.trace import TraceRecorder
from cua.types import (
    Budget,
    CritiqueReport,
    Draft,
    DraftFragment,
    GenerationStage,
    RunConfig,
    Source,
    SourceSet,
)

# Reuse the SCALE-CFG mini neurodiscover DB (tests/ is on sys.path via conftest).
from test_scale_cfg import _mini_db


# === minimal stub roles + Task: a pass-immediately Critic to prove the override =====================


class _StubStage(GenerationStage):
    """One single-shot generation stage producing an empty (claim-free) fragment → the draft grounds
    clean (no orphans) so `_decide` can pass at round 0."""

    name = "stub"
    config = None  # n_samples defaults to 1 (single-shot); model_id → None
    map_over = None

    def produce(self, obligations, inputs, draft_so_far, item=None):
        return DraftFragment(stage="stub", section="s", text="x")


class _StubConditioner:
    def compile(self, task, recorder=None, round=0):
        return [], Budget()


class _PassCritic:
    """Always returns `pass` — with empty `dimension_thresholds`, `_decide` passes at round 0 (today's
    path would stop immediately). Counts its calls so the test can assert the critique-pass count."""

    def __init__(self) -> None:
        self.calls = 0

    def critique(self, grounded, obligations_public, evidence_scores, external_critiques, recorder=None, round=0):
        self.calls += 1
        return CritiqueReport(decision="pass")


class _CountingReviser:
    def __init__(self) -> None:
        self.calls = 0

    def revise(self, prior_draft, critique, external_critiques, flagged_obligations, recorder=None, round=0):
        self.calls += 1
        return prior_draft


class _StubArtifact:
    def __init__(self, revision_round: int) -> None:
        self.revision_round = revision_round


class _StubTask:
    """A minimal §1.3 Task the engine duck-types: 3 sources (not degraded), one stub stage, no steering."""

    artifact_type = _StubArtifact

    def __init__(self) -> None:
        self.source_set = SourceSet([Source("s1"), Source("s2"), Source("s3")])
        self.generator = [_StubStage()]
        self.steering_sources = []

    def inputs(self):
        return {}

    def assemble_artifact(self, grounded, obligations, revision_round, degraded):
        return _StubArtifact(revision_round)

    def intake_refusal(self):
        return None


def _run(force_rounds, *, max_rounds=3):
    """Drive the stub Orchestrator with a pass-immediately Critic; return (artifact, trace, critic, reviser)."""
    critic, reviser = _PassCritic(), _CountingReviser()
    orch = Orchestrator(conditioner=_StubConditioner(), critic=critic, reviser=reviser, selection_scorer=None)
    cfg = RunConfig(max_rounds=max_rounds, dimension_thresholds={}, force_rounds=force_rounds)
    artifact, trace, _audit = orch.run(_StubTask(), cfg)
    return artifact, trace, critic, reviser


def _decisions(trace):
    return [(e.round, e.decision) for e in trace if e.role == "orchestrator" and (e.output_ref or "").startswith("decision")]


# === the core proof: force_rounds overrides an immediate pass ======================================


def test_force_rounds_runs_exact_depth_even_when_pass_immediately():
    """`force_rounds=2` → exactly 3 critique passes / `r=2` / 2 revises, even though `_decide` PASSES at
    round 0 (the stub Critic passes immediately). The pass is ignored; the exact depth wins."""
    artifact, trace, critic, reviser = _run(2)
    assert artifact.revision_round == 2          # [ok] r=2
    assert critic.calls == 3                      # N+1 critique passes (rounds 0,1,2)
    assert reviser.calls == 2                     # N revise steps (booster would fire each)


def test_force_rounds_zero_is_round_zero_only_no_revise():
    """`N=0` → round 0 only, no revise (the booster never fires)."""
    artifact, trace, critic, reviser = _run(0)
    assert artifact.revision_round == 0
    assert critic.calls == 1 and reviser.calls == 0


def test_force_rounds_overrides_max_rounds():
    """force_rounds is the EXACT count and overrides --max-rounds: force_rounds=4 with max_rounds=2 still
    runs 4 revise rounds (forcing can drive the loop BEYOND the max_rounds cap)."""
    artifact, _trace, critic, reviser = _run(4, max_rounds=2)
    assert artifact.revision_round == 4
    assert critic.calls == 5 and reviser.calls == 4


# === honesty: a forced run must not read as natural convergence ====================================


def test_forced_continue_is_marked_in_trace_when_critic_passed():
    """When the Critic PASSED but the loop continues only because of force_rounds, the decision is
    `pass (forced-continue)` (never a bare `pass`); the FINAL round (where it stops) is a bare `pass`."""
    _artifact, trace, _critic, _reviser = _run(2)
    # the pass-immediately critic passes every round → rounds 0,1 are forced-continue; round 2 stops.
    assert _decisions(trace) == [
        (0, "pass (forced-continue)"),
        (1, "pass (forced-continue)"),
        (2, "pass"),
    ]


def test_default_path_unchanged_no_forced_continue_marker():
    """force_rounds=None → today's pass-based path: the Critic passes at round 0, the loop stops there
    with a BARE `pass` (no forced-continue marker, no extra revise) — the byte-identical default."""
    artifact, trace, critic, reviser = _run(None)
    assert artifact.revision_round == 0
    assert critic.calls == 1 and reviser.calls == 0
    assert _decisions(trace) == [(0, "pass")]


# === _run_config threading =========================================================================


def test_run_config_threads_force_rounds():
    assert _run_config(3, 5).force_rounds is None                 # default ⇒ unchanged
    assert _run_config(3, 5, force_rounds=2).force_rounds == 2
    # defaults are otherwise value-identical to today's RUN_CONFIG (force_rounds is purely additive)
    rc = _run_config(RUN_CONFIG.max_rounds, 5)
    assert rc.max_rounds == RUN_CONFIG.max_rounds and rc.dimension_thresholds == RUN_CONFIG.dimension_thresholds


# === run_db integration: the flag drives the loop end-to-end =======================================


def _content(tmp_path, sub, **kw):
    db = tmp_path / "m.db"
    if not db.exists():
        _mini_db(str(db))
    out = tmp_path / sub
    assert run_db(db=str(db), run_id="s", out_dir=out, capture_content=True, **kw) == 0
    return json.loads((out / "s.content.json").read_text()), out


def test_run_db_force_rounds_forces_loop_past_natural_convergence(monkeypatch, tmp_path):
    """The offline surrogate converges naturally at r=1 (pass at round 1). `--force-rounds 2` drives it
    to exactly r=2 — 3 round snapshots / 3 critiques — and the forced-continue is visible in the trace."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    c, out = _content(tmp_path, "fr2", force_rounds=2)
    assert len(c["rounds"]) == 3 and len(c["critique"]) == 3
    assert [e["round"] for e in c["rounds"]] == [0, 1, 2]
    trace = [json.loads(line) for line in (out / "s.trace.jsonl").read_text().splitlines()]
    decs = [(e["round"], e["decision"]) for e in trace
            if e["role"] == "orchestrator" and e.get("output_ref", "").startswith("decision")]
    assert decs == [(0, "revise"), (1, "pass (forced-continue)"), (2, "pass")]


def test_run_db_force_rounds_zero_is_round_zero_only(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    c, _out = _content(tmp_path, "fr0", force_rounds=0)
    assert len(c["rounds"]) == 1 and [e["round"] for e in c["rounds"]] == [0]


def test_run_db_scale_line_surfaces_force_rounds(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    assert run_db(db=str(db), run_id="s", out_dir=tmp_path / "o", force_rounds=2) == 0
    assert "force_rounds=2" in capsys.readouterr().out               # honesty: the scale line shows it


def test_run_db_force_rounds_out_of_range_clean_nonzero(monkeypatch, tmp_path):
    """Out-of-range N ⇒ clean non-zero exit, BEFORE any DB/orchestrator work (no artifacts written)."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    for bad in (_FORCE_ROUNDS_MAX + 1, -1):
        out = tmp_path / f"bad{bad}"
        assert run_db(db=str(db), run_id="s", out_dir=out, force_rounds=bad) == 2
        assert not (out / "s.proposal.json").exists()               # rejected up front → nothing emitted


# === load-bearing: no flag ⇒ today's run, byte-for-byte ============================================


def test_no_force_rounds_byte_identical_to_explicit_none(monkeypatch, tmp_path):
    """A no-flag run and a run with force_rounds explicitly None produce BYTE-IDENTICAL artifacts — the
    new branch at the default changes nothing (the engine-spine change is gated entirely behind set)."""
    monkeypatch.delenv("CUA_LIVE", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    a, b = tmp_path / "noflag", tmp_path / "explicit_none"
    assert run_db(db=str(db), run_id="s", out_dir=a) == 0
    assert run_db(db=str(db), run_id="s", out_dir=b, force_rounds=None) == 0
    for ext in ("proposal.json", "trace.jsonl", "audit.json", "ingestion.json"):
        assert (a / f"s.{ext}").read_bytes() == (b / f"s.{ext}").read_bytes(), f"{ext} drifted"


def test_cli_main_threads_force_rounds(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    out = tmp_path / "cli"
    rc = main(["--db", str(db), "--run-id", "s", "--out-dir", str(out), "--force-rounds", "2", "--capture-content"])
    assert rc == 0
    c = json.loads((out / "s.content.json").read_text())
    assert len(c["rounds"]) == 3                                     # parsed + applied end-to-end


def test_cli_main_force_rounds_out_of_range_nonzero(monkeypatch, tmp_path):
    monkeypatch.delenv("CUA_LIVE", raising=False)
    db = tmp_path / "m.db"
    _mini_db(str(db))
    rc = main(["--db", str(db), "--run-id", "s", "--out-dir", str(tmp_path / "x"), "--force-rounds", "99"])
    assert rc == 2
