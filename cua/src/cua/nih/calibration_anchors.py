"""calibration_anchors.py — NIH binding: the Internal Critic's calibration anchors (gap 5).

Implements: contracts.md §1.7 (Critic scores), §1.10 (`Audit.calibration`); test_review_contract.md
            part B (Critic calibration — MAE / rank-corr); design §5 ("the Critic's 1-9 calibration
            anchors are a separate, deferred artifact: scored drafts spanning the range").
            Decision: build/decisions/2026-06-02-critic-calibration-anchors.md.
Generic role: eval-only reference data (NOT a pipeline role) — scored drafts spanning the 1-9 range.
NIH binding: NIH-flavoured stand-in drafts; domain nouns are legal here.
Owner: S5 (builder 1, the offline seed set) → S7 (builder 3, blinded-judge targets + the MAE/rank-corr).

Boundaries (load-bearing — test-review contamination rule): anchors are scored drafts, eval-only,
read-only, OUTSIDE the loop — NEVER injected into any agent input, and disjoint from both the writer
few-shot exemplars and the RePORTER reference set. v1 is a deterministic, offline seed: the targets are
hand-assigned modeling choices (a low anchor is, by design, NOT an exemplar). Known limit: the v1
deterministic Critic surrogate COMPRESSES the top of the range (any non-overclaiming draft scores 7), so
v1 MAE against high anchors is poor while rank ordering holds — that gap is the finding S7 quantifies
with the real Opus Critic (decision §C).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..types import (
    Claim,
    Draft,
    DraftFragment,
    EvidenceEntry,
    EvidenceScores,
    Grade,
    Level,
    Source,
    SourceSet,
    permitted,
)
from ..roles._writing import phrase
from .framework import F1, F2

_ORPHAN = "SYNTH-ANCHOR-ABSENT"  # an id deliberately absent from an anchor's source set (fabrication)


@dataclass
class CalibrationAnchor:
    """One calibration anchor (decision §A): a minimal, scrutinizable draft whose `target_scores` are
    the calibration target the Critic is measured against. `build()` returns the pieces the Critic
    consumes — a Draft, the SourceSet it is grounded against, and the EvidenceScores it resolves grades
    from. Spans the 1-9 range by construction (clean → high; overclaim/orphan → low)."""

    id: str
    target_scores: dict
    rationale: str
    _claims: list = field(default_factory=list)
    _sources: list = field(default_factory=list)
    _evidence: dict = field(default_factory=dict)

    def build(self) -> tuple[Draft, SourceSet, EvidenceScores]:
        fragments: list[DraftFragment] = []
        # F1 content sits in one section fragment; each F2 claim is its own aim segment (the fan-out unit).
        f1_claims = [c for c in self._claims if c.serves_dimension == F1]
        if f1_claims:
            fragments.append(
                DraftFragment(stage="anchor", section="significance_innovation",
                              text="", claims=f1_claims, serves_dimension=F1)
            )
        for i, c in enumerate([c for c in self._claims if c.serves_dimension == F2]):
            fragments.append(
                DraftFragment(stage="anchor", section="aims", text="", segment_id=f"aim-{i + 1}",
                              claims=[c], serves_dimension=F2)
            )
        evidence = EvidenceScores(self._evidence)
        return Draft(fragments=fragments), SourceSet(list(self._sources)), evidence


def _calibrated_claim(cid: str, dim: str, grade: Grade, evidence: dict, sources: list) -> Claim:
    """A grounded, calibrated claim: graded `grade`, phrased AT permitted(grade), cited in corpus."""
    sid = f"SYNTH-ANCHOR-{cid}"
    sources.append(Source(id=sid))
    evidence[cid] = EvidenceEntry(grade=grade, evidence_features={}, support_source_ids=[sid])
    return Claim(id=cid, text=phrase("The program", "the outcome", permitted(grade)),
                 evidence_ids=[cid], reference_ids=[sid], serves_dimension=dim,
                 subject="The program", predicate="the outcome")


def _overclaiming_claim(cid: str, dim: str, evidence: dict, sources: list) -> Claim:
    """A grounded but OVERCLAIMING claim: minimal grade (permits L1) phrased at L4 (causal)."""
    sid = f"SYNTH-ANCHOR-{cid}"
    sources.append(Source(id=sid))
    evidence[cid] = EvidenceEntry(grade=Grade.MINIMAL, evidence_features={}, support_source_ids=[sid])
    return Claim(id=cid, text=phrase("The program", "the outcome", Level.L4),
                 evidence_ids=[cid], reference_ids=[sid], serves_dimension=dim,
                 subject="The program", predicate="the outcome")


def _orphan_claim(cid: str, dim: str, evidence: dict) -> Claim:
    """A claim whose only citation is a FABRICATED id (absent from the anchor's source set)."""
    evidence[cid] = EvidenceEntry(grade=Grade.MODERATE, evidence_features={}, support_source_ids=[_ORPHAN])
    return Claim(id=cid, text=phrase("The program", "the outcome", permitted(Grade.MODERATE)),
                 evidence_ids=[cid], reference_ids=[_ORPHAN], serves_dimension=dim,
                 subject="The program", predicate="the outcome")


def _anchor_high() -> CalibrationAnchor:
    ev: dict = {}
    srcs: list = []
    claims = [
        _calibrated_claim("hi-f1-a", F1, Grade.STRONG, ev, srcs),
        _calibrated_claim("hi-f1-b", F1, Grade.MODERATE, ev, srcs),
        _calibrated_claim("hi-f2-a", F2, Grade.MODERATE, ev, srcs),
        _calibrated_claim("hi-f2-b", F2, Grade.WEAK, ev, srcs),
    ]
    return CalibrationAnchor("anchor-high", {F1: 8, F2: 8},
                             "clean, grounded, calibrated on both factors", claims, srcs, ev)


def _anchor_mid() -> CalibrationAnchor:
    ev: dict = {}
    srcs: list = []
    claims = [
        _calibrated_claim("mid-f1-a", F1, Grade.MODERATE, ev, srcs),
        _overclaiming_claim("mid-f1-over", F1, ev, srcs),  # one F1 overclaim drags F1 to mid/low
        _calibrated_claim("mid-f2-a", F2, Grade.MODERATE, ev, srcs),
    ]
    return CalibrationAnchor("anchor-mid", {F1: 5, F2: 7},
                             "F2 sound; a single F1 overclaim", claims, srcs, ev)


def _anchor_low() -> CalibrationAnchor:
    ev: dict = {}
    srcs: list = []
    claims = [
        _overclaiming_claim("lo-f1-a", F1, ev, srcs),
        _overclaiming_claim("lo-f1-b", F1, ev, srcs),  # two F1 overclaims → bottom of the range
        _orphan_claim("lo-f2-orphan", F2, ev),  # a fabricated citation on F2
    ]
    return CalibrationAnchor("anchor-low", {F1: 2, F2: 3},
                             "multiple F1 overclaims + a fabricated F2 citation", claims, srcs, ev)


# The deterministic v1 seed set, spanning the range on each factor (decision §C).
ANCHORS: list = [_anchor_high(), _anchor_mid(), _anchor_low()]


def internal_scores(critic, anchor: CalibrationAnchor) -> dict:
    """Run `critic` over an anchor's grounded draft and return its whole-draft `{dim: score}` (the
    `Audit.calibration.internal_scores` the eval compares to the target). Offline, no network: grounds
    the anchor draft with the code Grounder, then scores with empty obligations (anchors test the SCORE
    signal, not obligation coverage). S7 supplies the blinded-judge `target_scores` + computes MAE /
    rank-corr (test-review B3)."""
    from ..grounding import Grounder  # local import: keep this module import-light for the fixtures path

    draft, source_set, evidence = anchor.build()
    grounded, _report = Grounder().ground(draft, source_set)
    report = critic.critique(grounded, [], evidence, [])
    return {dim: ds.score for dim, ds in report.dimension_scores.items()}


def calibration_table(critic) -> list[dict]:
    """Convenience for the S7 harness / offline inspection: per anchor, the target vs the Critic's
    internal scores. (MAE / rank-corr are S7's to compute against the blinded judge; decision §B.)"""
    rows: list[dict] = []
    for a in ANCHORS:
        rows.append({"id": a.id, "target": a.target_scores, "internal": internal_scores(critic, a),
                     "rationale": a.rationale})
    return rows
