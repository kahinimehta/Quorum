"""_repair.py — the Critic→Reviser repair-directive protocol [role-internal, generic].

Implements: contracts.md §1.7 (the directives ride in `CritiqueReport.dimension_scores[D].spans`, a
            free-form `list[str]`), §1.5 (the Reviser's frozen signature gives it neither EvidenceScores
            nor the GroundingReport — so the grade-aware repair signal must travel from the Critic, which
            has both, through the CritiqueReport); build/decisions/2026-06-02-critic-scoring-rubric.md §B.
Generic role: the one documented place the Critic↔Reviser repair vocabulary lives, so the two cannot
              drift. Names no domain noun — claim ids / source ids / rung labels are generic.
Owner: S5 (builder 1).

The Critic ENCODES directives (it knows grades + orphans); the Reviser PARSES + applies them (it knows
how to write). This keeps the Critic the grade-aware judge and the Reviser a dumb surgical editor
(design §3) while using only frozen CritiqueReport fields.
"""

from __future__ import annotations

from typing import Iterable

HEDGE = "hedge"  # hedge:<claim_id>:<Lk>      — re-phrase claim_id down to rung Lk (= permitted(grade))
DROP = "drop-orphan"  # drop-orphan:<source_id>    — drop a fabricated (out-of-source-set) reference id


def hedge_directive(claim_id: str, level: str) -> str:
    """Encode a 'hedge this claim to rung `level`' directive (level e.g. 'L1'; the Critic computes it
    as permitted(grade) — it owns the grades)."""
    return f"{HEDGE}:{claim_id}:{level}"


def drop_directive(source_id: str) -> str:
    """Encode a 'drop this orphan reference id' directive (source_id ∈ grounding_report.orphan_ids)."""
    return f"{DROP}:{source_id}"


def parse_directives(spans: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    """Decode the directives carried in a flattened set of `spans` (recognised prefixes only — any
    other span string is human-readable prose and is ignored). Returns:
        hedges : { claim_id -> target rung label }   (last write wins; claim ids are unique anyway)
        drops  : [ orphan source_id ]                 (de-duplicated, order-preserved)
    """
    hedges: dict[str, str] = {}
    drops: list[str] = []
    for span in spans:
        if not isinstance(span, str):
            continue
        if span.startswith(HEDGE + ":"):
            # claim ids may themselves contain ':' (e.g. an aim claim 'aim-2::clm-...'), so split the
            # rung label off the RIGHT — the body is everything between the prefix and the last ':'.
            body = span[len(HEDGE) + 1:]
            claim_id, sep, level = body.rpartition(":")
            if sep and claim_id and level:
                hedges[claim_id] = level
        elif span.startswith(DROP + ":"):
            source_id = span[len(DROP) + 1:]  # source ids never carry a rung label — take the remainder
            if source_id and source_id not in drops:
                drops.append(source_id)
    return hedges, drops
