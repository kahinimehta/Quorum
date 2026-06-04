"""proposal.py — NIH binding: the Artifact and its parts.

Implements: contracts.md §2.1 (Proposal(Artifact), ProposalSection, ExpandedAim, RubricObligation,
            + the Structured-output envelope), §2.2 (ArgumentSkeleton — the ArgumentSynthesizer's
            output shape).
Generic role: Artifact (the finished deliverable) and the writer's intermediate skeleton.
NIH binding: Proposal / Specific Aims / Significance / Innovation / citation deck.
Owner: S2 (builder 1, type skeletons) → S4 (the writers fill them) → S2-A (the structural envelope).

Domain nouns are legal here. RubricObligation IS Obligation with dimension ∈ {F1, F2, F3} (§2.1).

Structured-output envelope (§2.1, ratified 2026-06-02 — `build/decisions/2026-06-02-proposal-
structured-output-amendment.md`): the assembled `Proposal` is validated against a strict STRUCTURAL
schema (`ProposalEnvelope`) at assembly via `validate_proposal()`, so a malformed Proposal cannot
leave assembly / reach the citation gate. Scope = STRUCTURE ONLY (required fields present + well-typed
+ the PHS 398 Research Plan shape). LOCAL validation (Pydantic) — deterministic, offline; NOT a
live/model structured-output API call. No semantic check lives here: cited-∈-corpus (inv-1), overclaim
(inv-3/§1.12), and obligation coverage (inv-2) own all meaning (§3); the envelope adds/removes none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..types import Artifact, Obligation
from .framework import Paper

# RubricObligation = Obligation with dimension ∈ {F1, F2, F3} (contracts.md §2.1).
RubricObligation = Obligation


@dataclass
class ProposalSection:
    """A section of the Proposal (contracts.md §2.1): name, the factor it serves, backing evidence
    ids, and the text."""

    name: str
    serves_dimension: str
    evidence_ids: list[str]
    text: str


@dataclass
class ExpandedAim:
    """One fully expanded Specific Aim (contracts.md §2.1) — the AimArchitect's output."""

    id: str
    hypothesis: str
    rationale: str
    approach: str
    expected_outcomes: str
    pitfalls_alternatives: str
    citation_ids: list[str] = field(default_factory=list)


@dataclass
class ArgumentSkeleton:
    """The ArgumentSynthesizer's output (contracts.md §2.2): gap → central hypothesis → aim stubs +
    Significance/Innovation. Every claim it carries is tagged serves_dimension + evidence_ids."""

    gap: str
    central_hypothesis: str
    aim_stubs: list
    significance: str
    innovation: str


@dataclass
class Proposal(Artifact):
    """The finished, grounded deliverable (contracts.md §2.1). `references` is the citation deck —
    EVERY ref ∈ corpus (enforced by the Grounder, inv-1). `obligations` is the embedded ledger.

    The runtime `Proposal` stays a plain dataclass (asdict-serialized to outputs, byte-deterministic).
    Its STRUCTURE is gated separately at assembly by `validate_proposal()` against `ProposalEnvelope`
    below — the envelope mirrors this shape; it never mutates or replaces the object."""

    project_title: str
    central_hypothesis: str
    sections: list[ProposalSection]
    aims: list[ExpandedAim]
    references: list[Paper]
    obligations: list[Obligation]
    revision_round: int


# === §2.1 Structured-output envelope (STRUCTURE ONLY — local, offline, deterministic) =============
#
# A strict Pydantic mirror of the Proposal shape. It is a *validator*, not the runtime carrier: the
# emitted Proposal remains the dataclass above (so byte-output + determinism are untouched), and we
# validate the assembled instance against this envelope at the end of assembly (`validate_proposal`).
# This is a typed SHAPE check only — required fields present, well-typed, in the PHS 398 Research Plan
# shape. It encodes NO semantics: membership-in-corpus (inv-1), overclaim (inv-3/§1.12), and
# obligation coverage (inv-2) remain the §3 gates' exclusive business. `from_attributes` reads the
# dataclass fields (and ignores any extra attribute, e.g. a fixture Paper's `real` marker); `strict`
# forbids silent type coercion so a wrong-typed field is a real structural failure, not a quiet cast.

_ENVELOPE = ConfigDict(from_attributes=True, strict=True)


class _SectionEnvelope(BaseModel):
    """Structural shape of one ProposalSection (§2.1): a named, dimension-tagged, non-empty body with
    a (possibly empty) evidence-id list. Whether those ids are in-corpus is inv-1's call, not ours."""

    model_config = _ENVELOPE

    name: str = Field(min_length=1)
    serves_dimension: str = Field(min_length=1)
    evidence_ids: list[str]
    text: str = Field(min_length=1)


class _AimEnvelope(BaseModel):
    """Structural shape of one ExpandedAim (§2.1): an identified aim CARRYING each PHS 398 part —
    hypothesis / rationale / approach / expected_outcomes / pitfalls_alternatives — as non-empty
    prose, plus a `citation_ids` list (which may be empty; whether an aim MUST cite is semantics)."""

    model_config = _ENVELOPE

    id: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    approach: str = Field(min_length=1)
    expected_outcomes: str = Field(min_length=1)
    pitfalls_alternatives: str = Field(min_length=1)
    citation_ids: list[str]


class _PaperEnvelope(BaseModel):
    """Structural shape of one citation-deck Paper (§2.1 Paper = Source). Type-checks the §2.1 fields;
    the deck's membership-in-corpus is the Grounder's inv-1 gate, never asserted here."""

    model_config = _ENVELOPE

    id: str = Field(min_length=1)
    authors: list[str]
    year: int
    title: str
    venue: str
    resolvable_id: str
    key_finding: str


class _ObligationEnvelope(BaseModel):
    """Structural shape of one embedded ledger RubricObligation (§2.1). Only the identifying shape is
    checked; coverage (satisfied ⇒ has evidence) is inv-2's business (§3.2), not the envelope's."""

    model_config = _ENVELOPE

    id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    requirement: str


class ProposalEnvelope(BaseModel):
    """The strict structural schema for an assembled Proposal (§2.1 PHS 398 Research Plan shape):
    a titled, hypothesis-bearing plan with ≥1 ProposalSection, ≥1 ExpandedAim (each carrying its
    parts), a references deck, and the embedded obligations ledger. STRUCTURE ONLY."""

    model_config = _ENVELOPE

    project_title: str = Field(min_length=1)
    central_hypothesis: str = Field(min_length=1)
    sections: list[_SectionEnvelope] = Field(min_length=1)
    aims: list[_AimEnvelope] = Field(min_length=1)
    references: list[_PaperEnvelope]
    obligations: list[_ObligationEnvelope]
    revision_round: int = Field(ge=0)


class ProposalStructureError(ValueError):
    """Raised by `validate_proposal` when an assembled Proposal fails the §2.1 structural envelope.
    A structural (shape/type) failure — NOT a semantic verdict (those are the §3 gates)."""


def validate_proposal(proposal: Proposal) -> Proposal:
    """Validate an assembled Proposal against the strict structural envelope (§2.1) and return it
    UNCHANGED on success — STRUCTURE ONLY, local + offline + deterministic (no model/API call, no
    mutation, so byte-output is untouched). Raises `ProposalStructureError` on a malformed Proposal,
    at assembly, before it can leave for the Orchestrator / citation gate. Semantics are out of scope:
    this never inspects corpus membership, grades, or coverage (the §3 invariants own those)."""

    try:
        ProposalEnvelope.model_validate(proposal, from_attributes=True)
    except ValidationError as exc:
        raise ProposalStructureError(
            f"malformed Proposal — fails §2.1 structural envelope "
            f"({exc.error_count()} structural error(s)):\n{exc}"
        ) from exc
    return proposal
