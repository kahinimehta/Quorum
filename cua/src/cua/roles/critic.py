"""critic.py — Internal Critic [LLM, heavy] — the reward engine.

Implements: contracts.md §1.5 (Critic signature — receives ObligationPublic, NOT self_score), §1.7
            (CritiqueReport: dimension_scores per factor [drives the §1.11 stopping rule], segment_scores
            per aim, decision, flagged_obligations), §1.12 (overclaim ladder — measured, never graded),
            §2.4 (RoleConfig: Opus 4.8 effort high). Decision: 2026-06-02-critic-scoring-rubric.
Generic role: Critic — scores the grounded draft against the obligations on each dimension and emits a
              pass/revise signal.  NIH binding: Internal Critic (design §2/§3) — the validated judge
              that MEASURES (vs the Selection Scorer that PICKS); calibrated to the eval (S7).
Owner: S5 (builder 1).

Independence (principle 2, load-bearing): the Critic is a SEPARATE lineage from the writers and the
Selection Scorer (never fused into a writer — design §6); it receives ObligationPublic only and ASSERTS
in code that no obligation it is handed exposes self_score/notes; it never sees the writer's trace. It
also ENFORCES, never grades (§1.12): it measures level(), maps grade→permitted, and flags — it never
produces or revises a Grade. v1 is a deterministic, offline surrogate of the Opus judge (no network).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ..config import RoleConfig
from ..grounding import level, resolve_grade
from ..types import (
    LEVEL_RANK,
    Claim,
    CritiqueReport,
    DimensionScore,
    EvidenceScores,
    GroundedDraft,
    ObligationPublic,
    SegmentScore,
    permitted,
)
from ..nih.framework import F1, F2, F3, OPUS_4_8, SCORED_DIMENSIONS
from ._repair import drop_directive, hedge_directive

# Scoring rubric weights (decision 2026-06-02-critic-scoring-rubric §A). Base is a competent,
# fundable-range score; penalties are calibrated to the v1 stopping bar (dimension_thresholds F1/F2 = 5,
# gap 8) so a single overclaim/orphan drops a gated dimension below it (7−3 = 4 < 5) and a clean
# dimension clears it (7 ≥ 5). Retuned alongside gap 8 at S6.
_BASE = 7
_OVERCLAIM_PENALTY = 3  # the dominant calibration failure
_ORPHAN_PENALTY = 3  # a fabricated (out-of-source-set) citation
_UNMET_ROW_PENALTY = 1  # a `critic` obligation row whose satisfied_by target is absent from the draft
_SCORE_MIN, _SCORE_MAX = 1, 9


def _clamp(score: int) -> int:
    return max(_SCORE_MIN, min(_SCORE_MAX, score))


def _overclaims(claim: Claim, evidence: EvidenceScores) -> bool:
    """True iff the claim asserts above the rung its evidence grade permits (§1.12). ENFORCE-only:
    level() measures the text, resolve_grade resolves the grade (unscored→minimal, composite→lowest),
    permitted() maps grade→rung. The Critic never grades."""
    grade, _unscored = resolve_grade(claim, evidence)
    return LEVEL_RANK[level(claim.text)] > LEVEL_RANK[permitted(grade)]


def _permitted_label(claim: Claim, evidence: EvidenceScores) -> str:
    grade, _unscored = resolve_grade(claim, evidence)
    return permitted(grade).value


# === live path (the reward engine) — forced-tool-use schema + prompt =============================
# `decisions/2026-06-02-live-bodies-wave-decisions.md` + LIVE-2/3 pattern: when is_live() and a recorder
# is reachable, real Opus SCORES the rubric on the BLIND grounded draft. The LLM emits the JUDGMENT
# (per-factor 1-9 + justifications, per-aim scores, pass/revise, flagged ids); the CODE owns the
# grade-aware repair directives (drop-orphan/hedge) it derives from the GroundingReport + overclaim
# ladder, and ENFORCES the calibration penalties on the LLM's base so an un-repaired overclaim/orphan
# can't pass (principle 2 / decision 2026-06-02-critic-scoring-rubric §B). Same-shaped CritiqueReport.


class _DimensionJudgment(BaseModel):
    """One factor's quality judgment: a 1-9 BASE score + a justification. Tolerant of the model
    flattening this to a bare number/string (live-structured-output-robustness) — coerced to {score}."""

    score: int = Field(description="1-9 quality score for this factor (the base; code applies grade penalties)")
    justification: str = Field(default="", description="brief, specific justification")

    @model_validator(mode="before")
    @classmethod
    def _tolerate_flattened(cls, data):
        if isinstance(data, bool):  # guard: bool is an int subclass — never a score
            return data
        if isinstance(data, (int, float)):
            return {"score": int(data)}
        if isinstance(data, str) and data.strip().lstrip("-").isdigit():
            return {"score": int(data.strip())}
        return data


class _SegmentJudgment(BaseModel):
    """One aim's quality judgment (audit-only; not gated). `aim_id` lets the code bind it to the aim."""

    aim_id: str = Field(default="", description="the aim id this score is for, e.g. 'aim-1'")
    score: int = Field(default=7, description="1-9 quality score for this aim")
    justification: str = Field(default="")


class _CritiqueOut(BaseModel):
    """The live Internal Critic's forced-tool output — the JUDGMENT only (§1.7). The drop-orphan/hedge
    repair directives are NOT here: the code derives them from the GroundingReport + overclaim ladder so
    the Reviser's targets stay non-fabricable. F3 is scored (1-9) but not gated by §1.11 (SCORED_DIMENSIONS
    = F1/F2); it surfaces in the report + informs the LLM's decision."""

    f1: _DimensionJudgment = Field(description="Significance + Innovation — should it be done?")
    f2: _DimensionJudgment = Field(description="Approach: rigor & feasibility — can it be done?")
    f3: _DimensionJudgment = Field(description="Investigator + Environment — by this team, here?")
    segment_scores: list[_SegmentJudgment] = Field(default_factory=list, description="one score per aim")
    decision: str = Field(default="revise", description="'pass' or 'revise'")
    flagged_obligation_ids: list[str] = Field(default_factory=list, description="ids of obligations judged unmet")


def _live_critique_prompt(
    grounded: GroundedDraft,
    obligations_public: list[ObligationPublic],
    evidence_scores: EvidenceScores,
    external_critiques: list,
) -> str:
    """Serialize the BLIND inputs (principle 2): the finished grounded draft (section/aim text + each
    claim with its CODE-resolved grade + permitted rung), the PUBLIC obligations (requirements only — no
    self_score/notes), the evidence grades, the external critiques, and the grounding result. The writer's
    self-assessment/reasoning never appears here."""
    draft = grounded.draft
    report = grounded.grounding_report

    lines: list[str] = []
    for f in draft.fragments:
        head = f.section + (f" [{f.segment_id}]" if f.segment_id else "")
        lines.append(f"## {head} (serves {f.serves_dimension or '-'})")
        if f.text:
            lines.append(f.text)
        for c in f.claims:
            grade, unscored = resolve_grade(c, evidence_scores)
            refs = ", ".join(c.reference_ids) or "(none)"
            lines.append(
                f"  - claim[{c.id}] (serves {c.serves_dimension or '-'}; evidence "
                f"grade={grade.value}{'/unscored' if unscored else ''}; permitted<={permitted(grade).value}; "
                f"cites {refs}): {c.text}"
            )
    draft_block = "\n".join(lines) or "(empty draft)"

    obs = "\n".join(
        f"- {o.id} [{o.dimension}] {o.requirement}"
        + (f"  (satisfied_by: {', '.join(o.satisfied_by)})" if o.satisfied_by else "")
        for o in obligations_public
    ) or "(none)"
    grades = "\n".join(
        f"- {k}: {evidence_scores[k].grade.value}" for k in evidence_scores
    ) or "(no graded evidence — corpus-only)"
    ext = external_critiques or []
    ext_block = "\n".join(
        f"- targets {getattr(c, 'target_ref', '?')}: {getattr(c, 'text', '')}" for c in ext
    ) or "(none)"

    return (
        "Score this FINISHED, GROUNDED draft against the obligations on each NIH review factor. You see "
        "the draft + the obligation requirements + the evidence grades — NOT the writer's self-assessment "
        "or reasoning. Reward grounded, calibrated claims that meet each factor's requirements; penalize "
        "overclaim (asserting above the evidence grade) and any fabricated citation. You MEASURE and "
        "ENFORCE — you never re-grade the evidence.\n\n"
        f"DRAFT:\n{draft_block}\n\n"
        f"OBLIGATIONS (public — requirements only):\n{obs}\n\n"
        f"EVIDENCE GRADES:\n{grades}\n\n"
        f"EXTERNAL CRITIQUES:\n{ext_block}\n\n"
        f"GROUNDING: all_in_source_set={report.all_in_source_set}; orphans={list(report.orphan_ids)}\n\n"
        "Return, for each factor, a 1-9 score + justification:\n"
        "- f1: Significance + Innovation.\n"
        "- f2: Approach — rigor & feasibility.\n"
        "- f3: Investigator + Environment.\n"
        "- segment_scores: one 1-9 score per aim (use the aim id, e.g. 'aim-1').\n"
        "- decision: 'pass' iff every factor meets its bar AND the draft is fully grounded and calibrated, "
        "else 'revise'.\n"
        "- flagged_obligation_ids: the ids of any obligations the draft does not yet satisfy.\n"
    )


class InternalCritic:
    """Internal Critic (§1.5/§1.7/§2.4): `(GroundedDraft, [ObligationPublic], EvidenceScores,
    external_critiques) -> CritiqueReport`. Opus 4.8, effort `high` (Opus rejects temperature). Blind to
    self_score; calibrated to the eval (S7). v1 deterministic surrogate of the Opus judge."""

    config = RoleConfig(
        model_id=OPUS_4_8,
        effort="high",
        system_prompt_template=(
            "Score the finished, grounded draft against the obligations on each scored dimension "
            "(1-9). You see the obligation requirements + evidence ids and the evidence grades — NOT "
            "the writer's self_score or reasoning. Reward grounded, calibrated claims that meet the "
            "dimension's requirements; penalize overclaim (assertiveness above the evidence grade) and "
            "fabricated citations. Emit per-aim scores, flag the unmet obligations, and decide "
            "pass/revise. You measure and enforce; you never re-grade evidence."
        ),
    )

    def critique(
        self,
        grounded: GroundedDraft,
        obligations_public: list[ObligationPublic],
        evidence_scores: EvidenceScores,
        external_critiques: list,
        *,
        recorder=None,
        round: int = 0,
    ) -> CritiqueReport:
        # Independence (§1.5, principle 2): the Critic must be blind to the writer's self_score/notes.
        # Enforced in code on BOTH paths, before any branch — not just by the orchestrator constructing
        # ObligationPublic. A raw Obligation (which carries self_score/notes) trips this on the live path too.
        for ob in obligations_public:
            assert not hasattr(ob, "self_score") and not hasattr(ob, "notes"), (
                "Critic must receive ObligationPublic (no self_score/notes) — scoring independence (§1.5)"
            )

        # LIVE branch (real Opus reward engine) when is_live() AND the Orchestrator threaded a recorder
        # (the §1.5 critique() domain signature is unchanged — recorder/round are engine transport, like
        # inputs['_recorder'] for the writers). Else the deterministic surrogate (the default, byte-
        # identical offline). Falls back to the surrogate on LiveUnavailable (mirrors LIVE-2/3).
        if recorder is not None and llm.is_live():
            try:
                return self._critique_live(
                    grounded, obligations_public, evidence_scores, external_critiques, recorder, round
                )
            except llm.LiveUnavailable:
                pass
        return self._critique_surrogate(grounded, obligations_public, evidence_scores, external_critiques)

    # --- code-owned analysis (shared by both paths — the repair targets can't drift, principle 2) ---

    def _repair_spans(
        self, claims: list[Claim], orphan_ids: set[str], evidence_scores: EvidenceScores
    ) -> tuple[dict[str, list[str]], list[str]]:
        """The per-dimension repair-directive buckets (decision §B), CODE-owned + grade-aware. One
        drop-orphan per fabricated id, one hedge per overclaiming claim (to its permitted rung). Each
        lands in the spans of the dimension the offending claim serves (fallback: the first scored
        dimension); the Reviser unions spans across dimensions. Returns (spans, overclaim_ids). Identical
        on the surrogate and live paths — the LLM never invents a directive."""
        spans: dict[str, list[str]] = {d: [] for d in SCORED_DIMENSIONS}

        def _attach(dim: str | None, directive: str) -> None:
            target = dim if dim in spans else next(iter(spans))
            if directive not in spans[target]:
                spans[target].append(directive)

        for orphan in sorted(orphan_ids):
            citing = next((c.serves_dimension for c in claims if orphan in c.reference_ids), None)
            _attach(citing, drop_directive(orphan))

        overclaim_ids: list[str] = []
        for c in claims:
            if _overclaims(c, evidence_scores):
                overclaim_ids.append(c.id)
                _attach(c.serves_dimension, hedge_directive(c.id, _permitted_label(c, evidence_scores)))
        return spans, overclaim_ids

    def _dim_penalty(
        self,
        dim: str,
        claims: list[Claim],
        orphan_ids: set[str],
        obligations_public: list[ObligationPublic],
        draft,
        evidence_scores: EvidenceScores,
    ) -> tuple[int, int, int, int]:
        """The grade-aware calibration deduction for one dimension (§A): overclaim + orphan + unmet-row
        penalties. Returns (penalty, n_over, n_orphan, n_unmet). The surrogate subtracts it from the fixed
        base; the live path subtracts the SAME deduction from the LLM's quality base — so a code-detected
        overclaim/orphan still drops the dimension below the bar (the loop revises until repaired)."""
        dim_claims = [c for c in claims if c.serves_dimension == dim]
        n_over = sum(1 for c in dim_claims if _overclaims(c, evidence_scores))
        n_orphan = sum(1 for c in dim_claims if any(r in orphan_ids for r in c.reference_ids))
        n_unmet = self._unmet_critic_rows(dim, obligations_public, draft)
        penalty = _OVERCLAIM_PENALTY * n_over + _ORPHAN_PENALTY * n_orphan + _UNMET_ROW_PENALTY * n_unmet
        return penalty, n_over, n_orphan, n_unmet

    # --- surrogate (default — deterministic offline) -------------------------------------------

    def _critique_surrogate(
        self,
        grounded: GroundedDraft,
        obligations_public: list[ObligationPublic],
        evidence_scores: EvidenceScores,
        external_critiques: list,
    ) -> CritiqueReport:
        draft = grounded.draft
        claims = draft.claims()
        orphan_ids = set(grounded.grounding_report.orphan_ids)
        ext = external_critiques or []

        spans, overclaim_ids = self._repair_spans(claims, orphan_ids, evidence_scores)

        # Score each scored dimension (§A): a fixed competent base minus the grade-aware deductions.
        dimension_scores: dict[str, DimensionScore] = {}
        for dim in SCORED_DIMENSIONS:
            penalty, n_over, n_orphan, n_unmet = self._dim_penalty(
                dim, claims, orphan_ids, obligations_public, draft, evidence_scores
            )
            dimension_scores[dim] = DimensionScore(
                score=_clamp(_BASE - penalty),
                justification=self._justify(dim, n_over, n_orphan, n_unmet, ext),
                spans=spans[dim],
            )

        # Per-aim segment_scores on F2 (§1.7; design §5) — validated per-aim quality for the Audit.
        segment_scores = self._segment_scores(draft, evidence_scores, orphan_ids)

        flagged = self._flagged_obligations(obligations_public, bool(overclaim_ids), bool(orphan_ids))
        # The Critic's own pass/revise judgment (the Orchestrator's §1.11 decide is authoritative): a
        # clean, calibrated, fully-grounded draft passes; an orphan or any overclaim revises.
        decision = "revise" if (orphan_ids or overclaim_ids) else "pass"
        return CritiqueReport(
            dimension_scores=dimension_scores,
            segment_scores=segment_scores,
            decision=decision,
            flagged_obligations=flagged,
        )

    # --- live (real Opus reward engine — LLM scores, code enforces) ----------------------------

    def _critique_live(
        self,
        grounded: GroundedDraft,
        obligations_public: list[ObligationPublic],
        evidence_scores: EvidenceScores,
        external_critiques: list,
        recorder,
        round: int,
    ) -> CritiqueReport:
        """Real Opus scores the rubric on the BLIND grounded draft (forced tool-use → `_CritiqueOut`);
        complete() records the one TraceEvent. The CODE owns the repair directives + the calibration
        deductions, so the LLM provides the QUALITY base while the grade-aware overclaim/orphan/unmet
        penalties (non-fabricable) still drive the §1.11 loop and the Reviser's targets. Same-shaped
        CritiqueReport."""
        draft = grounded.draft
        claims = draft.claims()
        orphan_ids = set(grounded.grounding_report.orphan_ids)

        # CODE-owned (grade-aware), identical to the surrogate — derived from the GroundingReport + the
        # overclaim ladder, never from the LLM (so the Reviser's drop-orphan/hedge targets are trustworthy).
        spans, overclaim_ids = self._repair_spans(claims, orphan_ids, evidence_scores)

        out: _CritiqueOut = llm.complete(
            self.config,
            system=self.config.system_prompt_template,
            user=_live_critique_prompt(grounded, obligations_public, evidence_scores, external_critiques),
            schema=_CritiqueOut,
            trace_role="critic",
            recorder=recorder,
            round=round,
            input_refs=("grounded", "obligations"),
            # output_ref defaults to "critic:live" (the live-event convention).
        )

        llm_base = {F1: out.f1.score, F2: out.f2.score}
        llm_just = {F1: out.f1.justification, F2: out.f2.justification}

        dimension_scores: dict[str, DimensionScore] = {}
        for dim in SCORED_DIMENSIONS:  # F1, F2 — the gated 1-9 axes (§1.11)
            penalty, n_over, n_orphan, n_unmet = self._dim_penalty(
                dim, claims, orphan_ids, obligations_public, draft, evidence_scores
            )
            # A FLAGGED dimension (overclaim/orphan/unmet) takes the surrogate-calibrated, DETERMINISTIC
            # score (`_BASE − penalty`) — a code-detected integrity issue is a hard, sub-bar revise signal
            # the LLM cannot inflate away (an Opus base of 8 would leave 8−3=5 ≥ bar and let an overclaim
            # pass). This is what makes inv-3 resistance a GUARANTEE (LIVE-6 then hedges it), exactly as the
            # surrogate. A CLEAN dimension takes the LLM's quality judgment (the reward engine).
            score = _clamp(_BASE - penalty) if penalty else _clamp(llm_base.get(dim, _BASE))
            dimension_scores[dim] = DimensionScore(
                score=score,
                justification=self._live_justify(dim, llm_just.get(dim, ""), n_over, n_orphan, n_unmet),
                spans=spans[dim],  # code-owned repair directives
            )
        # F3 (Investigator + Environment): scored 1-9 by the LLM, surfaced, but NOT gated (§1.11 reads only
        # SCORED_DIMENSIONS) and carries no repair directive — there is no orphan/overclaim notion for it.
        dimension_scores[F3] = DimensionScore(score=_clamp(out.f3.score), justification=out.f3.justification, spans=[])

        # Per-aim segment_scores: the LLM's per-aim base, minus the same code deductions (bases default to
        # _BASE for any aim the LLM didn't score).
        seg_base = {s.aim_id: s.score for s in out.segment_scores if s.aim_id}
        segment_scores = self._segment_scores(draft, evidence_scores, orphan_ids, bases=seg_base)

        # Flagged obligations: code-owned integrity rows (X-1/X-2) ∪ the LLM's flagged ids (valid ones).
        flagged = self._flagged_obligations(obligations_public, bool(overclaim_ids), bool(orphan_ids))
        valid_ids = {ob.id for ob in obligations_public}
        for fid in out.flagged_obligation_ids:
            if fid in valid_ids and fid not in flagged:
                flagged.append(fid)

        # Decision: the code FORCES revise on any integrity issue (orphan/overclaim) — so the repair
        # directives get applied; otherwise the LLM's pass/revise judgment (which weighs F1/F2/F3) shows
        # through. (The Orchestrator's §1.11 decide is authoritative and reads the dimension scores.)
        if orphan_ids or overclaim_ids:
            decision = "revise"
        else:
            decision = "pass" if str(out.decision).strip().lower() == "pass" else "revise"

        return CritiqueReport(
            dimension_scores=dimension_scores,
            segment_scores=segment_scores,
            decision=decision,
            flagged_obligations=flagged,
        )

    @staticmethod
    def _live_justify(dim: str, llm_just: str, n_over: int, n_orphan: int, n_unmet: int) -> str:
        """The LLM's per-factor justification, annotated with the code-enforced deductions (so the score
        the loop sees is explained)."""
        base = (llm_just or "").strip() or f"{dim}: scored"
        notes: list[str] = []
        if n_over:
            notes.append(f"-{_OVERCLAIM_PENALTY * n_over} overclaim")
        if n_orphan:
            notes.append(f"-{_ORPHAN_PENALTY * n_orphan} fabricated-citation")
        if n_unmet:
            notes.append(f"-{_UNMET_ROW_PENALTY * n_unmet} unmet-row")
        return base + (f" [code penalties: {', '.join(notes)}]" if notes else "")

    # --- rubric helpers ------------------------------------------------------------------------

    @staticmethod
    def _draft_refs(draft) -> set[str]:
        """The ids a `critic` obligation's satisfied_by may point at: claim ids ∪ segment (aim) ids."""
        refs: set[str] = set()
        for f in draft.fragments:
            if f.segment_id:
                refs.add(f.segment_id)
            for c in f.claims:
                refs.add(c.id)
        return refs

    def _unmet_critic_rows(self, dim: str, obligations_public: list[ObligationPublic], draft) -> int:
        """# of `critic` obligation rows in `dim` whose satisfied_by target is absent from the draft.
        `notes` is stripped on ObligationPublic, so 'is a critic row' is read structurally: a row that
        names a satisfied_by target (the qualitative rows do) — a missing target is an unmet row."""
        refs = self._draft_refs(draft)
        unmet = 0
        for ob in obligations_public:
            if ob.dimension != dim or not ob.satisfied_by:
                continue
            if not all(t in refs for t in ob.satisfied_by):
                unmet += 1
        return unmet

    def _segment_scores(
        self, draft, evidence_scores: EvidenceScores, orphan_ids: set[str], bases: dict[str, int] | None = None
    ) -> dict:
        """One SegmentScore per aim segment on F2 (the fan-out unit; §1.7). Same penalties as the
        whole-draft rule, restricted to the aim's claims. `bases` (live path) supplies the LLM's per-aim
        quality base; absent (surrogate path) every aim uses the fixed `_BASE` → byte-identical offline."""
        out: dict[str, SegmentScore] = {}
        for f in draft.fragments:
            if not f.segment_id:
                continue
            n_over = sum(1 for c in f.claims if _overclaims(c, evidence_scores))
            n_orphan = sum(1 for c in f.claims if any(r in orphan_ids for r in c.reference_ids))
            base = _clamp((bases or {}).get(f.segment_id, _BASE))
            score = _clamp(base - _OVERCLAIM_PENALTY * n_over - _ORPHAN_PENALTY * n_orphan)
            out[f.segment_id] = SegmentScore(
                dimension="F2",
                score=score,
                justification=(
                    f"aim {f.segment_id}: {n_over} overclaim(s), {n_orphan} fabricated citation(s)"
                    if (n_over or n_orphan) else f"aim {f.segment_id}: grounded and calibrated"
                ),
            )
        return out

    @staticmethod
    def _justify(dim: str, n_over: int, n_orphan: int, n_unmet: int, ext: list) -> str:
        parts: list[str] = []
        if n_over:
            parts.append(f"{n_over} claim(s) assert above the evidence grade")
        if n_orphan:
            parts.append(f"{n_orphan} claim(s) cite a fabricated reference")
        if n_unmet:
            parts.append(f"{n_unmet} obligation row(s) unmet")
        flagged_ext = [c.target_ref for c in ext if getattr(c, "target_ref", None)]
        if flagged_ext:
            parts.append("external critiques target: " + ", ".join(sorted(set(flagged_ext))))
        return f"{dim}: " + ("; ".join(parts) if parts else "requirements met; claims grounded and calibrated")

    @staticmethod
    def _flagged_obligations(obligations_public: list[ObligationPublic], overclaim: bool, orphan: bool) -> list[str]:
        """Obligation ids the Critic judges unmet: X-1 (citation integrity) on any orphan, X-2 (no
        overclaim) on any overclaim — the cross-cutting rows that name the failures, by id when present."""
        ids = {ob.id for ob in obligations_public}
        flagged: list[str] = []
        if orphan and "X-1" in ids:
            flagged.append("X-1")
        if overclaim and "X-2" in ids:
            flagged.append("X-2")
        return flagged
