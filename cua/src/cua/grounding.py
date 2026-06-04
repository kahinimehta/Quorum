"""grounding.py — Grounder [code].

Implements: contracts.md §1.5 (Grounder signature), §1.10 (GroundingReport), §3 invariant 1,
            §1.12 (overclaim ladder — permitted() + level() both real).
Generic role: Grounder  ·  NIH binding: Grounding & Citation (design §2/§3).
Owner: S2 (builder 1, Grounder + ladder scaffold) → S4 (builder 1, real level() lexicon, gap 4).
       Closed-world: ground only verifies refs; it never gathers (design principle 6).

Trust-critical (design principle 3): the reference-integrity gate (inv-1) is DETERMINISTIC code — a
model can never emit an out-of-source-set reference because no model owns this decision. Grounding is
also the precondition for calibration (principle 4): the overclaim ladder is chained to the same
draft; level() (S4, hedge-cue lexicon) measures assertiveness and the check flags, never grades.

Leak rule: 'reference' is the generic term used everywhere in the body; the §2 binding noun appears
only in the header binding line above, exactly as the CONVENTIONS rule-1 example sanctions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import (
    GRADE_RANK,
    LEVEL_RANK,
    Claim,
    Draft,
    EvidenceScores,
    Grade,
    GroundedDraft,
    Level,
    SourceSet,
    permitted,
)


# === §1.10 GroundingReport =======================================================================


@dataclass
class GroundingReport:
    """The Grounder's report (contracts.md §1.10). `all_in_source_set` is the HARD gate (inv-1):
    every cited id ∈ SourceSet, i.e. `orphan_ids == []`. `resolve_rate` (online DOI/PMID resolve,
    decision A) is unselected here — S2's gate is offline cited-∈-source-set only (test-data §2)."""

    n_references: int  # distinct in-source-set references (the reference deck; §2.1 'EVERY ref ∈ corpus')
    all_in_source_set: bool  # HARD gate (inv-1)
    orphan_ids: list[str] = field(default_factory=list)  # cited ids NOT in SourceSet (fabrications)
    resolve_rate: float | None = None  # optional; not asserted on fixtures (test-data §2)


# === §1.5 Grounder (code) ========================================================================


class Grounder:
    """[code] (Draft, SourceSet) -> (GroundedDraft, GroundingReport) — contracts.md §1.5.

    Enforces inv-1: collect every reference the draft cites, partition into in-source-set vs orphan,
    and fail the gate the moment an orphan appears. Deterministic; no LLM, no network."""

    def ground(self, draft: Draft, source_set: SourceSet) -> tuple[GroundedDraft, GroundingReport]:
        source_ids = source_set.ids()
        cited = draft.reference_ids()  # distinct, order-preserved
        in_source_set = [r for r in cited if r in source_ids]
        orphan_ids = [r for r in cited if r not in source_ids]
        report = GroundingReport(
            n_references=len(in_source_set),
            all_in_source_set=(len(orphan_ids) == 0),
            orphan_ids=orphan_ids,
            resolve_rate=None,
        )
        return GroundedDraft(draft=draft, grounding_report=report), report


# === §1.12 Overclaim ladder (calibration half — scaffold) ========================================


@dataclass
class OverclaimRow:
    """One row of Audit.overclaim_check (contracts.md §1.10/§1.12). The first five fields are the
    frozen contract shape; `unscored`/`note` are S2 scaffold annotations (additive)."""

    claim: str
    claim_level: str  # level(claim) — PLACEHOLDER until gap 4 (see level())
    evidence_grade: str
    permitted_level: str
    ok: bool
    unscored: bool = False  # claim had no resolvable grade → defaulted to minimal (§1.12, §2.5)
    note: str = ""


def resolve_grade(claim: Claim, evidence_scores: EvidenceScores) -> tuple[Grade, bool]:
    """Resolve the grade a claim's assertiveness is measured against (contracts.md §1.12).

    - Unlinked (no evidence_ids) OR every referenced id unscored → `minimal`, flagged (§1.12 grounding
      clause; §2.5 unscored-claim default).
    - Composite (binds >1 graded id) → the LOWEST constituent grade (binding fallback, NOT grading).
    Returns (grade, unscored_flag). The agent only ENFORCES — it never produces or revises a grade."""

    grades = [evidence_scores[eid].grade for eid in claim.evidence_ids if eid in evidence_scores]
    if not grades:
        return Grade.MINIMAL, True
    return min(grades, key=lambda g: GRADE_RANK[g]), False


# Hedge-cue lexicon (contracts.md §1.12 'MEASURED independently: hedge-cue lexicon + Haiku@0';
# build/decisions/2026-06-02-overclaim-level-classifier.md). Ordered L4 → L1; the FIRST non-empty tier
# wins (an overclaim is about the strongest assertion the text makes). Generic English cues only — this
# is engine-layer, so it names no domain noun (CONVENTIONS rule 1).
_LEVEL_CUES: list[tuple[Level, tuple[str, ...]]] = [
    (Level.L4, (  # causal / definitive
        "causes", "reverses", "restores", "eliminates", "cures", "prevents", "abolishes",
        "demonstrates that", "establishes that", "proves", "confirms that", "drives",
        "is responsible for",
    )),
    (Level.L3, (  # associative
        "is associated with", "associated with", "correlates with", "predicts", "is linked to",
        "linked to", "contributes to", "underlies", "is a determinant of",
    )),
    (Level.L2, (  # suggestive
        "may", "might", "suggests", "could", "appears to", "is consistent with",
        "supports the hypothesis", "points to", "preliminary",
    )),
    (Level.L1, (  # exploratory
        "we will investigate", "we will explore", "we hypothesize", "to determine whether",
        "examine whether", "assess whether",
    )),
]


def level(claim_text: str) -> Level:
    """Measure a claim's assertiveness rung from its text (contracts.md §1.12).

    Real v1 classifier: a deterministic hedge-cue lexicon. Scans the lowercased text and returns the
    HIGHEST rung any cue triggers; un-cued text defaults to L1 (the most conservative rung), so a
    sentence with no assertiveness marker never false-flags. The optional `+ Haiku@0` disambiguator
    (§1.12) — which may only RAISE a default-L1 — is deferred (offline/closed-world; design principle
    3/6). Ownership is ENFORCE-only: this maps text → rung; build_overclaim_check maps rung → permitted
    and flags. It never grades (§1.12)."""

    text = claim_text.lower()
    for lvl, cues in _LEVEL_CUES:
        if any(cue in text for cue in cues):
            return lvl
    return Level.L1


def build_overclaim_check(claims: list[Claim], evidence_scores: EvidenceScores) -> list[OverclaimRow]:
    """Build Audit.overclaim_check over a draft's claims (contracts.md §1.10/§1.12). All three pieces
    are real: level() measures assertiveness (hedge-cue lexicon, S4/gap 4), permitted() maps the
    resolved grade to its rung, and grade resolution (unscored→minimal, composite→lowest) runs here.
    `ok = level <= permitted`; a False row is a flagged overclaim (flag, not gate — §1.12)."""

    rows: list[OverclaimRow] = []
    for claim in claims:
        grade, unscored = resolve_grade(claim, evidence_scores)
        permitted_level = permitted(grade)
        claim_level = level(claim.text)
        overclaims = LEVEL_RANK[claim_level] > LEVEL_RANK[permitted_level]
        rows.append(
            OverclaimRow(
                claim=claim.id,
                claim_level=claim_level.value,
                evidence_grade=grade.value,
                permitted_level=permitted_level.value,
                ok=not overclaims,
                unscored=unscored,
                note=(
                    f"level({claim_level.value}) > permitted({permitted_level.value}) for "
                    f"{'unscored→minimal' if unscored else grade.value} evidence"
                    if overclaims else ""
                ),
            )
        )
    return rows
