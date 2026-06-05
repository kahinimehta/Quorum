"""task.py — NIH binding: NIHGrantTask + Artifact assembly.

Implements: contracts.md §2.3 (NIHGrantTask(Task): artifact_type=Proposal, condition=
            NIHReviewFramework, generator=[ArgumentSynthesizer, AimArchitect], input_contract),
            §2.5 (intake refusal), §1.4 (assemble the finished Artifact from the grounded draft).
Generic role: a concrete `Task` — the engine drives it without knowing it is a grant.
NIH binding: GrantCall intake, the Proposal assembly, the generic coverage-risk → F1-risk mapping.
Owner: S2 (builder 1).

`build_task(fixture)` adapts an S1 Fixture (stand-in upstream inputs) into the Task the Orchestrator
runs — fixtures ARE the NIH corpus/evidence, so no conversion is needed (shared types post-reconcile).
"""

from __future__ import annotations

from ..roles import AimArchitect, ArgumentSynthesizer
from ..types import (
    Draft,
    GroundedDraft,
    Obligation,
    SectionSpec,
    SourceSet,
    Task,
)
from .framework import F1, NIHReviewFramework, Paper
from .obligations import mark_ledger
from .proposal import ArgumentSkeleton, ExpandedAim, Proposal, ProposalSection, validate_proposal


def _default_sections() -> list[SectionSpec]:
    """The v1 section plan (contracts.md §2.3 sections = [significance, innovation, aims...])."""
    return [
        SectionSpec(name="significance", serves_dimension=F1, target_words=600),
        SectionSpec(name="innovation", serves_dimension=F1, target_words=300),
        SectionSpec(name="aims", serves_dimension="F2", target_words=2400),
    ]


class NIHGrantTask(Task):
    """The NIH-grant `Task` (contracts.md §2.3). Carries the staged Generator (Synthesizer +
    AimArchitect stubs in S2), the NIH Condition, and the two binding hooks the engine calls."""

    artifact_type = Proposal

    def __init__(
        self,
        grant_call,
        corpus: SourceSet,
        evidence,
        subgroups=None,
        treatments=None,
        commercial=None,
        external_critiques=None,
    ) -> None:
        self.grant_call = grant_call
        self.source_set = corpus
        self.evidence = evidence
        self.subgroups = subgroups
        self.treatments = treatments
        self.commercial = commercial
        self.external_critiques = external_critiques or []

        self.condition = NIHReviewFramework()
        self.sections = _default_sections()
        self.generator = [ArgumentSynthesizer(), AimArchitect()]
        self.steering_sources = []
        self.input_contract = {
            "required": ["grant_call", "corpus", "evidence"],
            "optional": ["subgroups", "treatments", "commercial"],
        }

    # --- engine-facing hooks -------------------------------------------------------------------

    def inputs(self) -> dict:
        """The slots the Generator/Critic consume (generic keys the engine reads)."""
        return {
            "grant_call": self.grant_call,
            "corpus": self.source_set,
            "evidence_scores": self.evidence,
            "subgroups": self.subgroups,
            "treatments": self.treatments,
            "commercial": self.commercial,
            "external_critiques": self.external_critiques,
        }

    def intake_refusal(self) -> str | None:
        """Refuse to start unless the GrantCall mechanism + limits are KNOWN (contracts.md §2.5)."""
        gc = self.grant_call
        if gc is None or not getattr(gc, "mechanism", ""):
            return "grant mechanism unknown (§2.5)"
        if not getattr(gc, "specific_aims_page_limit", 0) or not getattr(gc, "research_strategy_page_limit", 0):
            return "grant page limits unknown (§2.5)"
        return None

    def assemble_artifact(
        self,
        grounded: GroundedDraft,
        obligations: list[Obligation],
        revision_round: int,
        degraded: bool,
    ) -> Proposal:
        """Build the Proposal from the final grounded draft (contracts.md §1.4/§2.1). Deterministic.
        `degraded` (generic coverage-risk from the intake gate) is rendered as an F1 risk note here —
        the engine never names F1."""
        draft = grounded.draft
        skeleton: ArgumentSkeleton = _first_provided(draft, "skeleton")
        aims: list[ExpandedAim] = _all_provided(draft, "aims")

        corpus_by_id = {p.id: p for p in self.source_set.sources}
        references: list[Paper] = [corpus_by_id[rid] for rid in draft.reference_ids() if rid in corpus_by_id]

        significance_text = skeleton.significance if skeleton else "(no skeleton)"
        if degraded:
            significance_text += (
                " [F1 risk: corpus coverage is thin; significance claims are narrowed pending more evidence.]"
            )
        # Section evidence_ids come from the writer's F1 role claims (their backing evidence keys).
        by_id = {c.id: c for c in draft.claims()}
        sig_claim = by_id.get("significance")
        innov_claim = by_id.get("innovation")
        sections = [
            ProposalSection(
                name="significance", serves_dimension=F1,
                evidence_ids=list(sig_claim.evidence_ids) if sig_claim else [], text=significance_text,
            ),
            ProposalSection(
                name="innovation", serves_dimension=F1,
                evidence_ids=list(innov_claim.evidence_ids) if innov_claim else [],
                text=(skeleton.innovation if skeleton else ""),
            ),
        ]

        # Mark the ledger from the written draft — every `satisfied` obligation carries >=1 evidence_id
        # (inv-2; the S2-gate finding). See nih/obligations.mark_ledger + the 2026-06-02 decision.
        mark_ledger(obligations, draft, grounded.grounding_report, self.evidence)

        proposal = Proposal(
            project_title=getattr(self.grant_call, "title", ""),
            central_hypothesis=(skeleton.central_hypothesis if skeleton else ""),
            sections=sections,
            aims=aims,
            references=references,
            obligations=obligations,
            revision_round=revision_round,
        )
        # §2.1 structured-output envelope: gate the STRUCTURE before the Proposal leaves assembly —
        # a malformed Proposal raises here and never reaches the Orchestrator / citation gate. Local,
        # offline, deterministic; structure-only (the §3 semantic gates are unchanged). Returns the
        # same object unchanged, so byte-output stays identical.
        return validate_proposal(proposal)


# --- draft helpers -------------------------------------------------------------------------------


def _first_provided(draft: Draft, ref: str):
    for f in draft.fragments:
        if ref in f.provides and f.provides[ref]:
            return f.provides[ref][0]
    return None


def _all_provided(draft: Draft, ref: str) -> list:
    out: list = []
    for f in draft.fragments:
        out.extend(f.provides.get(ref, []))
    return out


# --- fixture adapter -----------------------------------------------------------------------------


def build_task(fixture) -> NIHGrantTask:
    """Adapt an S1 Fixture into an NIHGrantTask (contracts.md §2.3 input_contract). The fixture's
    corpus/evidence are already the bound types post-reconciliation, so this is a direct mapping."""
    return NIHGrantTask(
        grant_call=fixture.grant_call,
        corpus=fixture.corpus,
        evidence=fixture.evidence,
        subgroups=fixture.subgroups,
        treatments=fixture.treatments,
        commercial=fixture.commercial,
        external_critiques=fixture.external_critiques,
    )
