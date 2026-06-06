"""framework.py — NIH binding: the Condition, corpus item, and evidence alias.

Implements: contracts.md §2.1 (NIHReviewFramework(Condition), F1/F2/F3; Paper = Source; corpus =
            SourceSet of Paper; EvidenceAssessment = EvidenceScores).
Generic role: Condition (compiles → obligations + Budget) · Source · EvidenceScores.
NIH binding: NIH Simplified Review Framework; Paper; EvidenceAssessment (skeptic, GRADE-style).
Owner: S2 (builder 1) — type skeletons + a MINIMAL obligation template. The real obligation loader /
       topic specializer is S4 (`nih/obligations.py`, reading the nih_obligations.md set; OPEN.md gap 2).

Domain nouns are legal here (this is the binding). The first-pass RubricObligation set lives in
files/conclusion_update_agent_nih_obligations.md; the rows below mirror it as a stand-in template.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import (
    Budget,
    Condition,
    EvidenceScores,
    Obligation,
    Task,
)


# === §2.1 Paper / corpus / EvidenceAssessment ====================================================


@dataclass
class Paper:
    """A corpus item — `Source` specialized for the NIH binding (contracts.md §2.1). Field shape is
    kept byte-identical to the S1 fixture mirror so determinism digests are preserved across the
    reconciliation (S1-gate ruling). `resolvable_id` is DOI|PMID (decision A, OPEN.md — still open)."""

    id: str
    authors: list[str]
    year: int
    title: str
    venue: str
    resolvable_id: str
    key_finding: str
    real: bool = False


class EvidenceAssessment(EvidenceScores):
    """The skeptic's per-claim GRADE-style assessment (contracts.md §2.1: Grade ↔ GRADE, strong=high
    … minimal=very-low). A map claim_id -> EvidenceEntry. This agent only ENFORCES the ladder over
    it; grade calibration is the skeptic's burden (decision B, OPEN.md)."""


# === §2.1 NIHReviewFramework (Condition) =========================================================

# Dimensions (contracts.md §2.1): F1, F2 scored 1..9; F3 sufficiency.
F1 = "F1"  # Significance + Innovation — 'should it be done?'
F2 = "F2"  # Approach (rigor & feasibility) — 'can it be done?'
F3 = "F3"  # Investigator + Environment — 'by this team, here?' (sufficient/insufficient)

SCORED_DIMENSIONS: tuple[str, str] = (F1, F2)  # the 1..9 axes the stopping rule can gate

# §2.4 model ids (Anthropic API strings) — the per-role v1 model bindings live in this layer (the NIH
# binding), not in the engine's config.py. Imported by the roles (writers, Selection Scorer, Critic,
# Reviser).
OPUS_4_8 = "claude-opus-4-8"
SONNET_4_6 = "claude-sonnet-4-6"
HAIKU_4_5 = "claude-haiku-4-5-20251001"


@dataclass
class NIHReviewFramework(Condition):
    """The NIH Simplified Review Framework as a `Condition` (contracts.md §2.1). `compile` emits the
    full RubricObligation set (topic-specialized, per-aim rows instantiated) + a section/word Budget.
    v1 is near-deterministic (templated), per the Blueprint Planner role note (design §3); the rows +
    specialization + per-aim instantiation live in `obligations.py` (S4, gap 2a)."""

    dimensions: tuple[str, str, str] = (F1, F2, F3)

    def compile(self, task: Task) -> tuple[list[Obligation], Budget]:
        # Lazy import: obligations.py imports F1/F2/F3 from here, so the dependency is one-way.
        from . import obligations

        return obligations.compile_obligations(task), obligations.compile_budget(task)
