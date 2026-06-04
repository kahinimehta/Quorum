"""synthesizer.py — Generator stage 1: Argument Synthesizer [LLM, heavy] — primary tuning target.

Implements: contracts.md §1.6 (GenerationStage, map_over=None), §2.2 (ArgumentSynthesizer ->
            ArgumentSkeleton), §2.4 (RoleConfig; reward F1, best-of-N, log_pairs); §1.12 phrasing.
Generic role: Generator stage 1.  NIH binding: Argument Synthesizer (design §2/§3) — where the
              conclusion forms: gap -> central hypothesis -> aim stubs + Significance/Innovation.
Owner: S4 (builder 1).  Decisions: 2026-06-02-overclaim-level-classifier (writer assertiveness),
       2026-06-02-obligation-specialization (the rubric plans the aim count), 2026-06-02-fewshot-*.

Every claim is tagged `serves_dimension` + `evidence_ids` (§2.2). Claims are phrased at the rung their
evidence permits (calibrated), EXCEPT minimal/unscored empirical claims, which the writer over-reaches
to causal — the face-value bait the overclaim check then flags (level() measures it independently).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ._cites import coerce_cited
from ._corpus import findings_block, id_list_block
from ..config import RoleConfig
from ..grounding import resolve_grade
from ..nih.framework import F1, OPUS_4_8
from ..nih.obligations import planned_aim_ids
from ..nih.proposal import ArgumentSkeleton
from ..types import GRADE_RANK, Claim, Draft, DraftFragment, EvidenceScores, GenerationStage, Obligation
from ._writing import phrase, target_level

# Writer output budget (INGEST-1 v2, lowered from the LIVE-2 interim 32768). The Ingestion Layer now hands
# the writer a diversified, deduplicated top-K view instead of ~400 raw findings, so the prompt is far
# smaller and the structured argument fits in a budget BELOW the non-streaming streaming ceiling (32768
# tripped `dem3`'s 10-min non-streaming wall). 16384 = the engine's generic default, which the smaller
# roles already use without tripping the wall; streaming stays the documented fallback if a future top_k
# bump or larger writer output reintroduces truncation. Live-path only (offline surrogates never call
# complete()); operator verifies no truncation on the `full2` re-run.
_WRITER_MAX_TOKENS = 16384


def _first_match(keys: list[str], subs: tuple[str, ...]) -> str | None:
    """First claim_id whose lowercased text contains one of `subs` (the writer's role-key heuristic)."""
    for k in keys:
        kl = k.lower()
        if any(s in kl for s in subs):
            return k
    return None


def _highest(keys: list[str], evidence: EvidenceScores) -> str | None:
    """The highest-graded key among `keys` (ordinal GRADE_RANK); None if none is graded."""
    best, best_rank = None, -1
    for k in keys:
        entry = evidence.get(k)
        if entry is None:
            continue
        rank = GRADE_RANK[entry.grade]
        if rank > best_rank:
            best, best_rank = k, rank
    return best


def _supports(ev_ids: list[str], evidence: EvidenceScores) -> list[str]:
    """The corpus ids backing these evidence keys (the claim's reference_ids; inv-1 checks them)."""
    out: list[str] = []
    for k in ev_ids:
        entry = evidence.get(k)
        if entry is not None:
            out.extend(entry.support_source_ids)
    return list(dict.fromkeys(out))


# === live path (corpus-driven) — forced-tool-use schema + prompt =================================
# `decisions/2026-06-02-demo-v1-corpus-only-scope.md`: the EvidenceAssessment is empty, so the live
# writer is CORPUS-driven (the surrogate iterates evidence keys; there are none here). The schema is
# the F1 skeleton the model is forced to return; we assign the fixed role-claim ids + serves_dimension.


class _CitedClaim(BaseModel):
    """One F1 claim the live writer emits: prose + the corpus ids it cites (ONLY ids from the provided
    corpus). Non-empty text so the assembled §2.1 envelope's non-empty section text holds.

    Tolerant of the model flattening this to a bare STRING (non-deterministic; live-structured-output-
    robustness): the `mode="before"` validator coerces a string into `{text, cited_corpus_ids}`, recovering
    inline `[type:id]` cites so the citation survives → the Grounder still checks it (inv-1)."""

    text: str = Field(min_length=1, description="the claim, phrased at the EXPLORATORY rung (evidence is unscored)")
    cited_corpus_ids: list[str] = Field(default_factory=list, description="ids from the CORPUS list this claim cites; [] if none")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_flattened(cls, data):
        return coerce_cited(data, "text")


class _AimStub(BaseModel):
    """One planned aim: a title + the corpus ids it should be grounded in (the AimArchitect expands it).
    Tolerant of a bare-string flattening, like _CitedClaim (cites recovered into cited_corpus_ids)."""

    title: str = Field(min_length=1)
    cited_corpus_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _tolerate_flattened(cls, data):
        return coerce_cited(data, "title")


class _F1Argument(BaseModel):
    """The live ArgumentSynthesizer's forced-tool output (§2.2): gap → central hypothesis →
    Significance / Innovation (each citing only corpus ids) + the planned aim stubs."""

    gap: str = Field(min_length=1)
    significance: _CitedClaim
    central_hypothesis: _CitedClaim
    innovation: _CitedClaim
    aims: list[_AimStub] = Field(default_factory=list)


def _live_prompt(topic: str, corpus, obligations: list[Obligation], n_aims: int) -> str:
    """Serialize corpus (id/title/key_finding) + F1 obligations + topic into the user message, with the
    cite-only-corpus + hedge-to-exploratory rules (§3.1/§1.12; demo-v1-corpus-only-scope).

    Significance is the easiest section to over-reach: explaining "why it matters" invites suggestive,
    relational prose ("could reorient …", "linking X to Y") that the code-owned hedge-cue lexicon
    (grounding.level) reads as L2 > the permitted L1 for unscored evidence (LIVE-INT_B finding). So the
    significance instruction + the hedge RULES below frame it as the open QUESTION + the unmet need, and
    the avoid-list bans the suggestive (L2) hedges + relational framings, not just causal/associative verbs."""
    # Bounded prompt view (INGEST-1 v2): the Ingestion Layer's diversified top-K representatives (+ a
    # corroboration count where a finding is corroborated), NOT all ~400 raw findings (which overloads the
    # model → omissions/truncation), PLUS the full citable id-list (inv-1: cite only real ids).
    findings = findings_block(corpus)
    citable = id_list_block(corpus)
    f1 = "\n".join(f"- {o.id}: {o.requirement}" for o in obligations if o.dimension == F1) or "(none)"
    return (
        f"TOPIC: {topic}\n\n"
        f"CORPUS FINDINGS (diversified top-K shown — cite ONLY ids from the FULL CITABLE IDS list below):\n{findings}\n\n"
        f"FULL CITABLE IDS (every corpus id — cite ONLY from here; never invent or guess an id):\n{citable}\n\n"
        f"F1 OBLIGATIONS to satisfy:\n{f1}\n\n"
        "TASK:\n"
        "- Name the specific gap/barrier to progress.\n"
        "- Significance: frame WHY THE QUESTION IS WORTH INVESTIGATING — the unmet clinical/scientific need "
        "and the opportunity a study creates — WITHOUT asserting that any mechanism or relationship already "
        "holds, co-occurs, or is suggested. Describe the gap and the potential of investigating it, not an "
        "established or likely relationship. Keep it specific and grounded; cite >=1 corpus id.\n"
        "- State ONE central hypothesis that follows from the gap, citing the corpus id(s) it rests on.\n"
        "- Innovation: the specific departure from current concepts/methods/practice (not a generic 'novel').\n"
        f"- Sketch exactly {n_aims} aim stub(s), each a title + the corpus ids it should be grounded in.\n\n"
        "RULES:\n"
        "- Cite ONLY ids from the FULL CITABLE IDS list above. Any id not in that list is a fabrication and is rejected.\n"
        "- The evidence is UNSCORED (no grades). Phrase EVERY empirical claim — SIGNIFICANCE INCLUDED — at the "
        "EXPLORATORY rung ('we will investigate / examine whether …', 'to determine whether …'): state the open "
        "QUESTION and the unmet need, never an established or merely suggested relationship. Avoid "
        "(a) causal/associative verbs ('causes', 'reverses', 'restores', 'is associated with', 'correlates "
        "with', 'is linked to', 'predicts', 'underlies', 'contributes to'); (b) suggestive hedges that still "
        "assert a relationship ('may', 'might', 'could', 'suggests', 'appears to', 'is consistent with'); "
        "(c) relational framings ('intersect with', 'linking X to Y', 'co-occur', 'could reorient/redefine', "
        "'indexed by'). Assert no more than unscored evidence permits.\n"
    )


class ArgumentSynthesizer(GenerationStage):
    """Argument Synthesizer (§1.6/§2.2; reward F1; best-of-N engaged). Emits the F1 skeleton + the
    significance/central-hypothesis/innovation claims, and plans the aim_stubs (with the evidence each
    aim is to be grounded in) over the rubric's planned aim slots."""

    name = "synthesizer"
    map_over = None
    config = RoleConfig(
        model_id=OPUS_4_8,
        effort="xhigh",  # Opus rejects temperature → effort (the hardest reasoning step)
        n_samples=3,
        reward_source=[F1],
        log_pairs=True,
        few_shot_exemplars=["(structural exemplar: funded Significance/Innovation skeleton)"],
        system_prompt_template=(
            "Synthesize the upstream evidence into a defensible, novel-but-grounded argument: name the "
            "gap, state one central hypothesis that follows from it, sketch the aim stubs, and write "
            "Significance + Innovation. Tag every claim with the factor it serves and its evidence ids; "
            "assert no more than the evidence grade permits."
        ),
    )

    def _claim(self, cid: str, subject: str, predicate: str, ev_ids: list[str],
               evidence: EvidenceScores, *, framing: bool) -> Claim:
        claim = Claim(
            id=cid, text="", evidence_ids=list(ev_ids),
            reference_ids=_supports(ev_ids, evidence), serves_dimension=F1,
            subject=subject, predicate=predicate,  # handle for the Reviser's re-phrase (round-trip reverse)
        )
        grade, _unscored = resolve_grade(claim, evidence)
        claim.text = phrase(subject, predicate, target_level(grade, framing=framing))
        return claim

    def produce(self, obligations: list[Obligation], inputs: dict, draft_so_far: Draft, item=None) -> DraftFragment:
        """§1.6 produce. LIVE branch (corpus-driven Opus) when `cua.llm.is_live()` AND the driver
        supplied a recorder (via `inputs['_recorder']`); otherwise the deterministic SURROGATE (the
        default — offline, byte-identical). Falls back to the surrogate on `LiveUnavailable`. Decisions:
        live-bodies-wave / demo-v1-corpus-only-scope / trace-recording-ownership."""
        recorder = inputs.get("_recorder")
        if recorder is not None and llm.is_live():
            try:
                return self._produce_live(obligations, inputs, recorder, inputs.get("_round", 0))
            except llm.LiveUnavailable:
                pass  # toggle off / no key → the surrogate (default path)
        return self._produce_surrogate(obligations, inputs, draft_so_far, item)

    def _produce_live(self, obligations: list[Obligation], inputs: dict, recorder, round: int) -> DraftFragment:
        """Read the corpus + obligations and call `cua.llm.complete()` to produce the F1 argument as
        real Opus prose (forced tool-use → `_F1Argument`). complete() records the one TraceEvent."""
        grant = inputs.get("grant_call")
        topic = getattr(grant, "title", "the proposed work")
        aim_ids = planned_aim_ids(obligations) or ["aim-1", "aim-2"]
        out: _F1Argument = llm.complete(
            self.config,
            system=self.config.system_prompt_template,
            user=_live_prompt(topic, inputs.get("corpus"), obligations, len(aim_ids)),
            schema=_F1Argument,
            trace_role=self.name,
            recorder=recorder,
            round=round,
            input_refs=("corpus", "obligations"),
            max_tokens=_WRITER_MAX_TOKENS,  # scale-robustness: Opus xhigh + full argument needs headroom
            # output_ref defaults to "synthesizer:live" (the live-event convention,
            # decisions/2026-06-02-trace-recording-ownership.md).
        )
        return self._fragment_from(out, topic, aim_ids)

    def _fragment_from(self, out: _F1Argument, topic: str, aim_ids: list[str]) -> DraftFragment:
        """Assemble the DraftFragment from the live output — SAME shape as the surrogate. Each F1 role
        claim carries the fixed id the ledger binds (significance / central-hypothesis / innovation) and
        `evidence_ids = reference_ids = cited corpus ids` (corpus-only: unscored → minimal → must hedge
        to L1; inv-2 binds F1 rows to these). Fabricated ids flow through → the Grounder flags them (inv-1)."""

        def role_claim(cid: str, cc: _CitedClaim) -> Claim:
            ids = list(dict.fromkeys(cc.cited_corpus_ids))
            return Claim(id=cid, text=cc.text, evidence_ids=ids, reference_ids=ids, serves_dimension=F1)

        sig = role_claim("significance", out.significance)
        central = role_claim("central-hypothesis", out.central_hypothesis)
        innov = role_claim("innovation", out.innovation)
        claims = [sig, central, innov]

        anchor = next((r for c in (sig, central, innov) for r in c.reference_ids), None)
        aim_stubs: list[dict] = []
        for i, aid in enumerate(aim_ids):
            a = out.aims[i] if i < len(out.aims) else None
            title = a.title if (a and a.title) else f"Aim {i + 1}: {topic}"
            ev_keys = list(dict.fromkeys(a.cited_corpus_ids)) if a else []
            if not ev_keys and anchor:  # keep the aim groundable (mirror the surrogate's anchor)
                ev_keys = [anchor]
            aim_stubs.append({"id": aid, "title": title, "evidence_keys": ev_keys})

        skeleton = ArgumentSkeleton(
            gap=out.gap,
            central_hypothesis=central.text,
            aim_stubs=aim_stubs,
            significance=sig.text,
            innovation=innov.text,
        )
        return DraftFragment(
            stage=self.name,
            section="significance_innovation",
            text=sig.text + " " + innov.text,
            claims=claims,
            serves_dimension=F1,
            provides={"skeleton": [skeleton], "aim_stubs": aim_stubs},
        )

    def _produce_surrogate(self, obligations: list[Obligation], inputs: dict, draft_so_far: Draft, item=None) -> DraftFragment:
        evidence: EvidenceScores = inputs.get("evidence_scores", EvidenceScores())
        grant = inputs.get("grant_call")
        topic = getattr(grant, "title", "the proposed work")
        keys = list(evidence.keys())  # insertion order = deterministic

        # Role keys for the three F1 claims; the rest seed the aims.
        sig_key = _first_match(keys, ("sig", "burden"))
        central_key = _first_match(keys, ("central", "hyp"))
        innov_key = _first_match(keys, ("innov",))
        role_keys = {k for k in (sig_key, central_key, innov_key) if k}
        aim_pool = [k for k in keys if k not in role_keys]
        anchor = central_key or _highest(aim_pool, evidence) or _highest(keys, evidence)

        # F1 claims. The significance claim is unscored when the skeptic graded no significance/impact
        # key (e.g. unscored_claim) → the writer over-reaches → the overclaim the check flags.
        sig_claim = self._claim("significance", "The proposed program",
                                f"the disease burden in {topic}", [sig_key] if sig_key else [], evidence, framing=False)
        central_ids = [central_key] if central_key else ([anchor] if anchor else [])
        central_claim = self._claim("central-hypothesis", "The central hypothesis",
                                    f"the clinical outcome in {topic}", central_ids, evidence, framing=False)
        innov_claim = self._claim("innovation", "The proposed innovation",
                                  "current methods and practice", [innov_key] if innov_key else [], evidence, framing=True)
        claims = [sig_claim, central_claim, innov_claim]

        # Plan the aims from the compiled rubric (principle 1: the rubric is a generation constraint).
        aim_ids = planned_aim_ids(obligations) or ["aim-1", "aim-2"]
        n = len(aim_ids)
        assigned: dict[str, list[str]] = {a: [] for a in aim_ids}
        for j, k in enumerate(aim_pool):
            assigned[aim_ids[j % n]].append(k)
        for a in aim_ids:  # anchor any aim the pool didn't reach so it stays groundable (inv-2)
            if not assigned[a] and anchor:
                assigned[a] = [anchor]

        aim_stubs = [
            {"id": a, "title": f"Aim {a.split('-')[1]}: {topic}", "evidence_keys": assigned[a]}
            for a in aim_ids
        ]

        skeleton = ArgumentSkeleton(
            gap=f"A specific barrier to progress in {topic} remains unresolved.",
            central_hypothesis=central_claim.text,
            aim_stubs=aim_stubs,
            significance=f"Significance — resolving the barrier in {topic} matters to the field. {sig_claim.text}",
            innovation=f"Innovation — a specific departure from current practice in {topic}. {innov_claim.text}",
        )
        return DraftFragment(
            stage=self.name,
            section="significance_innovation",
            text=skeleton.significance + " " + skeleton.innovation,
            claims=claims,
            serves_dimension=F1,
            provides={"skeleton": [skeleton], "aim_stubs": aim_stubs},
        )
