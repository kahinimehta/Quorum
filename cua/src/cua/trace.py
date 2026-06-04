"""trace.py — Trace & Audit assembly [code].

Implements: contracts.md §1.10 (TraceEvent/Trace as JSONL — one event per role call; Audit
            assembled deterministically, never by a model — design §1 observability).
Generic role: the two never-collapsed observability artifacts (internal Trace, judge-facing Audit).
NIH binding: assembled once per run for the bound Task (design §2); no domain logic lives here.
Owner: S2 (builder 1).

Determinism (design §1: 'assembled by a codified module, not by a model'): `ts` is a LOGICAL
monotonic tick, not wall-clock — so two identical runs emit byte-identical traces. The recorder is
the single sink every role call writes one event to.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .grounding import GroundingReport, OverclaimRow
from .types import CritiqueReport, Obligation


# === §1.10 Trace =================================================================================


@dataclass
class TraceEvent:
    """One event per role call (contracts.md §1.10). `model`/`sampling` echo the role's RoleConfig
    so the Trace shows which model + sampling produced each step; code roles log model=None."""

    round: int
    role: str
    model: str | None
    sampling: str | None
    input_refs: list[str]
    output_ref: str | None
    tokens: int | None
    ts: int  # LOGICAL monotonic tick (deterministic; NOT wall-clock)
    decision: str | None = None


class Trace(list):
    """`list[TraceEvent]` (contracts.md §1.10) with a JSONL serializer."""

    def to_jsonl(self) -> str:
        return "\n".join(json.dumps(asdict(ev), ensure_ascii=False) for ev in self)


class TraceRecorder:
    """The single sink every role call writes to. Owns the logical clock so `ts` is reproducible."""

    def __init__(self) -> None:
        self._events: Trace = Trace()
        self._tick: int = 0

    def record(
        self,
        round: int,
        role: str,
        *,
        model: str | None = None,
        sampling: str | None = None,
        input_refs: tuple[str, ...] | list[str] = (),
        output_ref: str | None = None,
        tokens: int | None = None,
        decision: str | None = None,
    ) -> TraceEvent:
        self._tick += 1
        ev = TraceEvent(
            round=round,
            role=role,
            model=model,
            sampling=sampling,
            input_refs=list(input_refs),
            output_ref=output_ref,
            tokens=tokens,
            ts=self._tick,
            decision=decision,
        )
        self._events.append(ev)
        return ev

    @property
    def trace(self) -> Trace:
        return self._events


# === §1.10 Audit =================================================================================


@dataclass
class Calibration:
    """Audit.calibration (contracts.md §1.10). `internal_scores` are the Critic's whole-draft
    dimension scores; `external_scores`/`mae`/`rank_corr` are filled by the eval (S7), None here.
    `segment_scores` is ADDITIVE (mirrors the S2 precedent of additive Audit annotations): the §1.7
    CritiqueReport per-segment scores (per fan-out item quality) surfaced into the Audit for the
    operator and the per-stage reward (design §5). The §3 invariants do not read it, so it is shape-safe."""

    internal_scores: dict[str, int] = field(default_factory=dict)
    external_scores: dict[str, int] | None = None
    mae: dict[str, float] | None = None
    rank_corr: dict[str, float] | None = None
    segment_scores: dict | None = None


@dataclass
class UnitTestRow:
    """One row of Audit.unit_tests (contracts.md §1.10): a code-level self-check carried in the
    Audit. S2 records the reference-integrity gate result here; the full offline suite is S3."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class Audit:
    """The judge-facing Audit (contracts.md §1.10) — assembled deterministically by `assemble_audit`,
    never by a model. `obligation_ledger` is the FULL obligations (with self_score, status)."""

    grounding_report: GroundingReport
    obligation_ledger: list[Obligation]
    calibration: Calibration
    overclaim_check: list[OverclaimRow]
    unit_tests: list[UnitTestRow]


def assemble_audit(
    grounding_report: GroundingReport,
    obligation_ledger: list[Obligation],
    critique: CritiqueReport,
    overclaim_check: list[OverclaimRow],
    unit_tests: list[UnitTestRow],
) -> Audit:
    """Deterministically assemble the Audit from the run's already-computed pieces (contracts.md
    §1.10). No model, no nondeterminism — pure projection of inputs."""

    calibration = Calibration(
        internal_scores={dim: ds.score for dim, ds in critique.dimension_scores.items()},
        external_scores=None,
        mae=None,
        rank_corr=None,
        segment_scores={
            ref: {"dimension": ss.dimension, "score": ss.score, "justification": ss.justification}
            for ref, ss in critique.segment_scores.items()
        }
        or None,
    )
    return Audit(
        grounding_report=grounding_report,
        obligation_ledger=obligation_ledger,
        calibration=calibration,
        overclaim_check=overclaim_check,
        unit_tests=unit_tests,
    )
