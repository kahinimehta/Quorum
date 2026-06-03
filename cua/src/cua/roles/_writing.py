"""_writing.py — writer assertiveness/prose helpers [role-internal, generic].

Implements: contracts.md §1.12 (the writer phrases each claim at a target rung; grounding.level()
            recovers it) + build/decisions/2026-06-02-overclaim-level-classifier.md (§2 writer model).
Generic role: shared helper for the two writer stages (ArgumentSynthesizer, AimArchitect). Names no
              domain noun — callers pass the subject/predicate prose; this only sets assertiveness.
Owner: S4 (builder 1).

The writer emits text whose hedge-cue round-trips through grounding.level() to the SAME rung it
targeted, so the overclaim check measures the emitted text INDEPENDENTLY of the writer (principle 4).
The templates here and the lexicon in grounding.level() are co-designed for that round-trip.
"""

from __future__ import annotations

from ..types import Grade, Level, permitted


def target_level(grade: Grade, *, framing: bool) -> Level:
    """The rung the writer phrases a claim at (decision §2).

    - framing claims (e.g. innovation) are non-empirical → permitted(grade); they never over-reach.
    - empirical claims on MINIMAL/unscored evidence → L4 (causal): the narrative over-reach that
      DEFINES the bait — the check then flags it (low_grade_bait, unscored_claim).
    - otherwise (grade >= weak) → permitted(grade): a calibrated writer."""

    if framing:
        return permitted(grade)
    if grade is Grade.MINIMAL:
        return Level.L4
    return permitted(grade)


# Level -> phrasing template. Each embeds exactly ONE hedge-cue that grounding.level() recovers to the
# same rung (round-trip). Subject/predicate are neutral prose supplied by the caller; keep them
# cue-free (a stray cue would shift the measured level — verified by running the overclaim check).
_TEMPLATES: dict[Level, str] = {
    Level.L4: "{subject} reverses {predicate}.",
    Level.L3: "{subject} is associated with improvement in {predicate}.",
    Level.L2: "{subject} may improve {predicate}.",
    Level.L1: "We will investigate whether {subject} affects {predicate}.",
}


def phrase(subject: str, predicate: str, lvl: Level) -> str:
    """Render claim text at `lvl` (round-trips through grounding.level())."""

    return _TEMPLATES[lvl].format(subject=subject, predicate=predicate)
