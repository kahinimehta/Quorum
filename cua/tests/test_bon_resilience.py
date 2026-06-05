"""BON-RESILIENCE — best-of-N TOPS UP a failed candidate to maintain N (bounded; survivors fallback).

`build/live/BON-RESILIENCE_relay.md` (amended → top-up, not drop-only): in best-of-N, one candidate's
retry-exhausted live structured-output failure (`LiveStructuredOutputError`) must NOT abort the run AND
must NOT silently shrink N (that distorts the scaling x-axis). Drop the failed attempt and generate a
REPLACEMENT until there are N successes, bounded at `cap = N + ceil(N/2)`. If the cap is hit with M
(1 ≤ M < N) successes, proceed with the best of those M (log "got M of N"); hard-fail only if ZERO
succeed. `n=1` tops up too (cap 2) — strictly more robust than today, never less.

OFFLINE BYTE-IDENTICAL: the deterministic surrogate never raises `LiveStructuredOutputError`, so the
drop/top-up path is DEAD offline — exercised here with a fake stage that raises directly (no network/key).
Owner: BON-RESILIENCE (builder 1).
"""

from __future__ import annotations

import pytest

from cua import llm
from cua.capture import ContentCapture
from cua.config import RoleConfig
from cua.generation import _attempt_cap, _produce_one
from cua.roles import SelectionScorer
from cua.trace import TraceRecorder
from cua.types import Claim, Draft, DraftFragment


class _FakeStage:
    """A best-of-N stage whose `produce()` raises `LiveStructuredOutputError` on the chosen 1-based ATTEMPT
    numbers (a live candidate omitting a required field across all per-call retries), and otherwise returns
    a distinct, F1-grounded fragment keyed by its SUCCESS ordinal (so the surrogate Selection Scorer ranks
    them and a top-up replacement is a fresh, succeeding sample)."""

    name = "synthesizer"
    map_over = None

    def __init__(self, n: int, fail_attempts=(), *, refs_for=None):
        self.config = RoleConfig(model_id="claude-opus-4-8", effort="high", n_samples=n, reward_source=["F1"])
        self._fail = set(fail_attempts)        # 1-based attempt numbers that raise
        self._refs_for = refs_for or {}        # success ordinal (1-based) -> extra ref (breaks score ties)
        self.attempts = 0
        self._success = 0

    def produce(self, obligations, inputs, draft_so_far, item=None) -> DraftFragment:
        self.attempts += 1
        if self.attempts in self._fail:
            raise llm.LiveStructuredOutputError(
                f"omitted required field 'innovation' (attempt {self.attempts}); stop=end_turn"
            )
        self._success += 1
        k = self._success
        refs = ["100", self._refs_for[k]] if k in self._refs_for else ["100"]
        claim = Claim(id=f"s{k}", text=f"candidate {k}", evidence_ids=["e1"], reference_ids=refs, serves_dimension="F1")
        return DraftFragment(stage="synthesizer", section="F1", text=f"cand{k}", claims=[claim], serves_dimension="F1")


def _run(stage, capture=None):
    rec = TraceRecorder()
    best = _produce_one(stage, [], {}, Draft(), None, SelectionScorer(), rec, 0, "synthesizer", capture)
    return best, rec


def _roles(rec):
    return [ev.role for ev in rec.trace]


# === the cap formula =============================================================================


def test_attempt_cap_is_target_plus_headroom():
    assert [_attempt_cap(t) for t in (1, 3, 5, 10, 20)] == [2, 5, 8, 15, 30]   # target + ceil(target/2)


# === 1 of N fails → a REPLACEMENT is produced → the run keeps N successes =========================


def test_one_failure_tops_up_to_maintain_n():
    # n=3: attempt 2 fails; the loop tops up (attempt 4) → 3 successes. success 2 carries an extra ref → wins.
    stage = _FakeStage(3, fail_attempts={2}, refs_for={2: "101"})
    cap = ContentCapture()
    best, rec = _run(stage, cap)

    assert stage.attempts == 4 and stage._success == 3        # one drop, topped up to N=3
    assert best.claims[0].id == "s2"                          # best of the THREE successes

    roles = _roles(rec)
    assert "synthesizer:dropped" in roles
    res = next(ev for ev in rec.trace if ev.role == "synthesizer:resilience")
    assert "requested 3, attempts 4, succeeded 3, dropped 1" in res.decision
    assert "got" not in res.decision                          # full N reached → no shortfall note

    bon = cap.best_of_n[0]
    assert (bon["requested"], bon["attempts"], bon["succeeded"], bon["dropped"], bon["n"]) == (3, 4, 3, 1, 3)
    assert len(bon["candidates"]) == 3 and sum(c["chosen"] for c in bon["candidates"]) == 1
    assert [d["attempt"] for d in bon["dropped_attempts"]] == [2]
    assert "innovation" in bon["dropped_attempts"][0]["error"]
    assert "topped-up to 3/3" in bon["rationale"]


def test_maintain_n_with_two_interspersed_failures():
    stage = _FakeStage(5, fail_attempts={2, 4})
    cap = ContentCapture()
    best, rec = _run(stage, cap)
    assert stage.attempts == 7 and stage._success == 5        # 2 drops, topped up to N=5
    bon = cap.best_of_n[0]
    assert (bon["requested"], bon["succeeded"], bon["dropped"], bon["n"]) == (5, 5, 2, 5)
    assert [d["attempt"] for d in bon["dropped_attempts"]] == [2, 4]


# === failures EXCEED the cap → proceed with the survivors' best (≥1) + log M-of-N ================


def test_cap_exceeded_degrades_to_best_of_m():
    # n=3 → cap 5. attempts 2..5 all fail → only success 1 (attempt 1) within budget.
    stage = _FakeStage(3, fail_attempts={2, 3, 4, 5})
    cap = ContentCapture()
    best, rec = _run(stage, cap)
    assert stage.attempts == 5 and stage._success == 1        # cap reached, 1 survivor
    assert best.claims[0].id == "s1"                          # best of M=1
    res = next(ev for ev in rec.trace if ev.role == "synthesizer:resilience")
    assert "requested 3, attempts 5, succeeded 1, dropped 4" in res.decision
    assert "got 1 of 3 requested (cap 5 reached)" in res.decision
    bon = cap.best_of_n[0]
    assert (bon["requested"], bon["succeeded"], bon["dropped"], bon["n"]) == (3, 1, 4, 1)


# === ALL fail → re-raise (hard-fail) — including n=1 =============================================


def test_all_fail_reraises():
    stage = _FakeStage(3, fail_attempts={1, 2, 3, 4, 5})       # every attempt up to the cap fails
    with pytest.raises(llm.LiveStructuredOutputError):
        _run(stage)
    assert stage.attempts == _attempt_cap(3)                   # exhausted the bounded budget


def test_n1_tops_up_then_succeeds():
    # n=1 takes the single-shot path but now TOPS UP: attempt 1 fails, attempt 2 succeeds → returns it.
    stage = _FakeStage(1, fail_attempts={1})
    best, rec = _run(stage)
    assert stage.attempts == 2 and best.claims[0].id == "s1"   # one top-up, then success
    roles = _roles(rec)
    assert "synthesizer:dropped" in roles
    res = next(ev for ev in rec.trace if ev.role == "synthesizer:resilience")
    assert "requested 1, attempts 2, succeeded 1, dropped 1" in res.decision


def test_n1_all_fail_hard_fails():
    stage = _FakeStage(1, fail_attempts={1, 2})                # both attempts (cap=2) fail
    with pytest.raises(llm.LiveStructuredOutputError):
        _run(stage)
    assert stage.attempts == 2                                 # cap reached, no survivor


# === no failures → the drop/top-up path is DEAD (byte-identical rationale) =======================


def test_no_failures_no_topup_events():
    stage = _FakeStage(3, fail_attempts=set())
    cap = ContentCapture()
    best, rec = _run(stage, cap)
    assert stage.attempts == 3 and best.claims[0].id in {"s1", "s2", "s3"}
    roles = _roles(rec)
    assert "synthesizer:dropped" not in roles and "synthesizer:resilience" not in roles
    bon = cap.best_of_n[0]
    assert (bon["requested"], bon["attempts"], bon["succeeded"], bon["dropped"], bon["n"]) == (3, 3, 3, 0, 3)
    assert bon["dropped_attempts"] == []
    assert all(set(c) == {"index", "score", "rationale", "chosen", "fragment"} for c in bon["candidates"])
