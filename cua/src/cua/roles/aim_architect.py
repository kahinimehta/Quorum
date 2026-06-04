"""aim_architect.py — Generator stage 2: Aim Architect [LLM, heavy].

Implements: contracts.md §1.6 (GenerationStage, map_over=aim_stubs), §2.2 (AimArchitect ->
            ExpandedAim), §2.4 (RoleConfig; reward F2); §1.12 phrasing.
Generic role: Generator stage 2.  NIH binding: Aim Architect (design §2/§3) — expands one aim stub
              into rationale / approach / expected outcomes / pitfalls, with citations.
Owner: S4 (builder 1).  Decision: 2026-06-02-overclaim-level-classifier (writer assertiveness).

One DraftFragment per aim (segment_id = aim id) so the ledger marking can bind each per-aim obligation
to its aim's evidence (inv-2). Each aim claim is grounded in the evidence keys the Synthesizer assigned
to that aim and phrased at the rung that evidence permits (minimal → causal over-reach, the bait).
Knob idle in v1 (single-shot); reward F2 wired for best-of-N when engaged.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ._cites import coerce_expansion
from ._corpus import findings_block, id_list_block
from ..config import RoleConfig
from ..grounding import resolve_grade
from ..nih.framework import F2, OPUS_4_8
from ..nih.proposal import ExpandedAim
from ..types import Claim, Draft, DraftFragment, EvidenceScores, GenerationStage, Obligation
from ._writing import phrase, target_level

# Writer output budget (INGEST-1 v2, lowered from the LIVE-2 interim 32768): see synthesizer — the Ingestion
# Layer's bounded top-K view shrinks the prompt enough that the structured aim expansion fits below the
# non-streaming streaming ceiling (32768 tripped `dem3`'s 10-min wall). 16384 = the engine generic default;
# streaming stays the documented fallback. Live-path only (offline surrogates never call complete()).
_WRITER_MAX_TOKENS = 16384


def _supports(ev_ids: list[str], evidence: EvidenceScores) -> list[str]:
    out: list[str] = []
    for k in ev_ids:
        entry = evidence.get(k)
        if entry is not None:
            out.extend(entry.support_source_ids)
    return list(dict.fromkeys(out))


# === live path (corpus-driven) — forced-tool-use schema + prompt =================================
# Mirrors LIVE-2 (synthesizer.py): the EvidenceAssessment is empty (demo-v1-corpus-only-scope), so the
# live AimArchitect expands one aim stub from the corpus key_findings it cites. The schema's five aim
# parts are each non-empty (§2.1 _AimEnvelope); `citation_ids` are the corpus ids the aim cites.


_PROSE_FIELDS = ("hypothesis", "rationale", "approach", "expected_outcomes", "pitfalls_alternatives")


class _AimExpansion(BaseModel):
    """One ExpandedAim the live AimArchitect emits (§2.2). All five PHS 398 parts non-empty so the
    assembled §2.1 _AimEnvelope holds; `citation_ids` are corpus ids only (inv-1).

    Tolerant of the model flattening (live-structured-output-robustness): the `mode="before"` validator
    recovers `[type:id]` cites inlined into any prose part into `citation_ids` (the common case), and — if
    the whole aim is handed back as a bare STRING — spreads the cleaned string across the parts so the
    object validates rather than hard-failing after the paid call. The citation survives either way."""

    hypothesis: str = Field(min_length=1, description="one explicit, testable hypothesis at the EXPLORATORY rung (unscored evidence)")
    rationale: str = Field(min_length=1)
    approach: str = Field(min_length=1, description="key methods/design at enough specificity to judge rigor (not goals alone)")
    expected_outcomes: str = Field(min_length=1)
    pitfalls_alternatives: str = Field(min_length=1)
    citation_ids: list[str] = Field(default_factory=list, description="corpus ids this aim cites; only ids from the provided corpus")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_flattened(cls, data):
        return coerce_expansion(data, _PROSE_FIELDS)


def _aim_prompt(topic: str, title: str, ev_keys: list[str], corpus, obligations: list[Obligation]) -> str:
    """Serialize the aim's pre-assigned evidence (its `evidence_keys` → those Papers' key_findings) + the
    full corpus + the F2 obligations + topic, with the cite-only-corpus + hedge-to-exploratory rules."""
    by_id = {p.id: p for p in getattr(corpus, "sources", [])}
    assigned = "\n".join(
        f"[{cid}] {getattr(by_id[cid], 'title', '') or ''} — {getattr(by_id[cid], 'key_finding', '') or ''}"
        for cid in ev_keys if cid in by_id
    ) or "(none pre-assigned)"
    # Bounded prompt view (INGEST-1 v2): the aim's pre-assigned evidence in FULL (small, specific) + the
    # Ingestion Layer's diversified top-K corpus findings (NOT all ~400) + the full citable id-list (inv-1).
    findings = findings_block(corpus)
    citable = id_list_block(corpus)
    f2 = "\n".join(f"- {o.id}: {o.requirement}" for o in obligations if o.dimension == F2) or "(none)"
    return (
        f"TOPIC: {topic}\n"
        f"AIM TO EXPAND: {title}\n\n"
        f"EVIDENCE PRE-ASSIGNED TO THIS AIM:\n{assigned}\n\n"
        f"CORPUS FINDINGS (diversified top-K shown — cite ONLY ids from the FULL CITABLE IDS list below):\n{findings}\n\n"
        f"FULL CITABLE IDS (every corpus id — cite ONLY from here):\n{citable}\n\n"
        f"F2 OBLIGATIONS (rigor / feasibility) to satisfy:\n{f2}\n\n"
        "TASK — expand this aim into:\n"
        "- hypothesis: one explicit, testable hypothesis/objective.\n"
        "- rationale: why it follows from the cited evidence.\n"
        "- approach: the key methods/design at enough specificity to judge rigor (not goals alone).\n"
        "- expected_outcomes: outcomes tied to the hypothesis.\n"
        "- pitfalls_alternatives: explicit pitfalls + alternative strategies.\n"
        "- citation_ids: the corpus ids this aim cites (>=1, only from the lists above).\n\n"
        "RULES:\n"
        "- Cite ONLY ids from the FULL CITABLE IDS list above. Any id not in that list is a fabrication and is rejected.\n"
        "- Evidence is UNSCORED. Phrase the hypothesis at the EXPLORATORY rung ('we will investigate / "
        "examine whether …', 'to determine whether …'); do NOT assert causation or association (avoid "
        "'causes', 'reverses', 'restores', 'is associated with', 'correlates with'). Assert no more than "
        "unscored evidence permits.\n"
    )


class AimArchitect(GenerationStage):
    """Aim Architect (§1.6/§2.2; reward F2; map_over=aim_stubs). Conservative, standard methods — rigor
    rewards precision over flourish, so less reasoning depth than the Synthesizer (design §3)."""

    name = "aim_architect"
    map_over = "aim_stubs"
    config = RoleConfig(
        model_id=OPUS_4_8,
        effort="high",
        n_samples=1,  # single-shot in v1; F2 reward wired for best-of-N when engaged
        reward_source=[F2],
        few_shot_exemplars=["(structural exemplar: funded Specific Aim skeleton)"],
        system_prompt_template=(
            "Expand one aim stub into a testable hypothesis, a specific methods/design approach, "
            "expected outcomes tied to the hypothesis, and an explicit pitfalls/alternative-strategies "
            "paragraph, citing only corpus ids. Surface the expertise/resources the approach assumes "
            "(F3). Assert no more than the evidence grade permits."
        ),
    )

    def produce(self, obligations: list[Obligation], inputs: dict, draft_so_far: Draft, item=None) -> DraftFragment:
        """§1.6 produce (map_over=aim_stubs). LIVE branch (corpus-driven Opus) when `cua.llm.is_live()`
        AND the driver supplied a recorder (`inputs['_recorder']`); else the deterministic SURROGATE (the
        default — offline, byte-identical). Falls back to the surrogate on `LiveUnavailable`. Mirrors
        LIVE-2 (synthesizer); the spine trace-guard already covers the map_over loop."""
        recorder = inputs.get("_recorder")
        if recorder is not None and llm.is_live():
            try:
                return self._produce_live(obligations, inputs, item, recorder, inputs.get("_round", 0))
            except llm.LiveUnavailable:
                pass  # toggle off / no key → the surrogate (default path)
        return self._produce_surrogate(obligations, inputs, draft_so_far, item)

    def _produce_live(self, obligations: list[Obligation], inputs: dict, item, recorder, round: int) -> DraftFragment:
        """Expand one aim stub into a real Opus `ExpandedAim` (forced tool-use → `_AimExpansion`).
        complete() records the one TraceEvent (the LIVE-2 trace-guard covers each map_over position)."""
        topic = getattr(inputs.get("grant_call"), "title", "the proposed work")
        aim_id = item["id"] if item else "aim-x"
        title = item["title"] if item else f"Aim: {topic}"
        ev_keys = list(item.get("evidence_keys", [])) if item else []
        out: _AimExpansion = llm.complete(
            self.config,
            system=self.config.system_prompt_template,
            user=_aim_prompt(topic, title, ev_keys, inputs.get("corpus"), obligations),
            schema=_AimExpansion,
            trace_role=self.name,
            recorder=recorder,
            round=round,
            input_refs=("aim_stub", "corpus", "obligations"),
            max_tokens=_WRITER_MAX_TOKENS,  # scale-robustness: full structured aim expansion needs headroom
            # output_ref defaults to "aim_architect:live" (the live-event convention).
        )
        return self._fragment_from(out, aim_id, title)

    def _fragment_from(self, out: _AimExpansion, aim_id: str, title: str) -> DraftFragment:
        """Assemble the DraftFragment from the live output — SAME shape as the surrogate (section="aims",
        segment_id=aim_id, one ExpandedAim provided). The aim's testable hypothesis is the bound claim,
        carrying `evidence_ids = reference_ids = cited corpus ids` (corpus-only: unscored → minimal → must
        hedge to L1; binds the per-aim F2 ledger rows via segment_id, inv-2). A fabricated citation id
        flows through reference_ids + the aim's citation_ids → the Grounder flags it (inv-1) and the
        Reviser scrubs it from both."""
        cites = list(dict.fromkeys(out.citation_ids))
        claim = Claim(
            id=f"{aim_id}::hypothesis",
            text=out.hypothesis,
            evidence_ids=cites,
            reference_ids=cites,
            serves_dimension=F2,
        )
        aim = ExpandedAim(
            id=aim_id,
            hypothesis=out.hypothesis,
            rationale=out.rationale,
            approach=out.approach,
            expected_outcomes=out.expected_outcomes,
            pitfalls_alternatives=out.pitfalls_alternatives,
            citation_ids=cites,
        )
        return DraftFragment(
            stage=self.name,
            section="aims",
            text=out.approach,
            segment_id=aim_id,
            claims=[claim],
            serves_dimension=F2,
            provides={"aims": [aim]},
        )

    def _produce_surrogate(self, obligations: list[Obligation], inputs: dict, draft_so_far: Draft, item=None) -> DraftFragment:
        evidence: EvidenceScores = inputs.get("evidence_scores", EvidenceScores())
        topic = getattr(inputs.get("grant_call"), "title", "the proposed work")
        aim_id = item["id"] if item else "aim-x"
        title = item["title"] if item else f"Aim: {topic}"
        ev_keys: list[str] = list(item.get("evidence_keys", [])) if item else []

        claims: list[Claim] = []
        cite_ids: list[str] = []
        for k in ev_keys:
            claim = Claim(
                id=f"{aim_id}::{k}", text="", evidence_ids=[k],
                reference_ids=_supports([k], evidence), serves_dimension=F2,
                subject=title, predicate="the targeted mechanism",  # re-phrase handle (round-trip reverse)
            )
            grade, _unscored = resolve_grade(claim, evidence)
            claim.text = phrase(title, "the targeted mechanism", target_level(grade, framing=False))
            claims.append(claim)
            cite_ids.extend(claim.reference_ids)

        aim = ExpandedAim(
            id=aim_id,
            hypothesis=f"Testable hypothesis for {title}.",
            rationale=f"Rationale grounded in the corpus for {title}.",
            approach=f"Methods and design for {title}; expertise and resources surfaced (F3).",
            expected_outcomes=f"Expected outcomes tied to the hypothesis for {title}.",
            pitfalls_alternatives=f"Pitfalls and alternative strategies for {title}.",
            citation_ids=list(dict.fromkeys(cite_ids)),
        )
        return DraftFragment(
            stage=self.name,
            section="aims",
            text=aim.approach,
            segment_id=aim_id,
            claims=claims,
            serves_dimension=F2,
            provides={"aims": [aim]},
        )
