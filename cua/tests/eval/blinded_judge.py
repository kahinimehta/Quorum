"""blinded_judge.py — the blinded LLM-as-judge [tester, builder 3].

Implements: test_review_contract.md part B2 (LLM-as-judge scoring F1/F2 1–9 + F3 sufficiency, source
            identity hidden + order randomized, DIFFERENT model/prompt from the Internal Critic,
            deterministic) + Boundaries (blinded judge ≠ Internal Critic). Decision:
            build/decisions/2026-06-02-eval-methodology.md §C; contracts.md §2.1 (F1/F2 1–9, F3
            sufficiency), §1.10 (the calibration target).
Generic role: the independent external eval judge — the ground truth the Critic is calibrated against
              (the single coupling point that licenses the Critic as a reward signal, design §6).
NIH binding: NIH study-section reviewer scoring the Simplified Review Framework. Owner: S7 (builder 3).

Independence (LOAD-BEARING — Boundaries; design principle 2/4): the judge is a DIFFERENT model + prompt
from the Critic and is BLIND to the Critic's output — `score`/`score_anchor` receive only the
draft/proposal, NEVER the `CritiqueReport` / `internal_scores` / writer trace. If the eval author also
tuned the Critic to agree with the judge, the calibration would be circular (which is why the dev-5
retune is RELAYED, not applied here — see 2026-06-02-critic-range-retune.md). v1 is a deterministic
OFFLINE surrogate (no LLM, no network — same posture as the agent's S4/S5 surrogates); the real Sonnet
judge (config below) replaces the surrogate bodies with an API call, harness unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from cua.config import RoleConfig
from cua.nih.framework import SONNET_4_6


_F_MIN, _F_MAX = 1, 9


def _clamp(score: int) -> int:
    return max(_F_MIN, min(_F_MAX, score))


@dataclass(frozen=True)
class JudgeScore:
    """The blinded judge's per-proposal score (test-review B2; contracts.md §2.1). F1/F2 on the 1–9
    scale NORMALIZED to higher = better (so MAE/rank-corr against the Critic's higher-is-better 1–9 are
    directly comparable — the native NIH 1 = best is converted at the harness boundary, decision §C).
    F3 is sufficiency, not 1–9."""

    F1: int
    F2: int
    F3: str  # "sufficient" | "insufficient"
    justification: str = ""


@dataclass(frozen=True)
class JudgeInput:
    """The common, source-blinded structural view of ONE proposal (AI or human) the judge scores for
    competitiveness (decision §C blinding). `source` is carried for post-hoc bookkeeping ONLY — the
    judge's `score` MUST NOT read it (blinding; verified in test_eval.py by score-invariance to source).
    Fields are the structural features BOTH an AI proposal (from Proposal+Audit) and a funded human
    reference (abstracted) expose, so the comparison is apples-to-apples. `mechanism` is the matched-
    stratum key (R01|R21; B4) — NOT a blinded identity, so the judge may see it."""

    source: str  # "AI" | "human" — bookkeeping; the judge is blind to it
    title: str
    has_central_hypothesis: bool
    has_innovation: bool
    n_aims: int
    n_references: int
    n_overclaims: int  # funded human work (abstracted) → 0; AI → Audit.overclaim_check non-ok count
    mechanism: str = ""  # R01 | R21 — the matched-stratum key (B4); default keeps positional ctors valid


# === The judge ==================================================================================


_JUDGE_PROMPT = (
    "You are an independent NIH study-section reviewer. Given one proposal (Significance/Innovation + "
    "Specific Aims with citations), score F1 (Significance+Innovation) and F2 (Approach: rigor & "
    "feasibility) on the 1–9 scale reported so HIGHER = BETTER, and F3 (Investigator+Environment) as "
    "sufficient|insufficient. Reward a grounded, novel-but-defensible argument, calibrated claims, "
    "rigorous feasible aims, explicit pitfalls/alternatives; penalize over-reach and weak support. You "
    "do NOT see how the draft was produced, any internal score, or whether it is human- or "
    "machine-authored. Output JSON {F1,F2,F3,justification}. Be deterministic."
)


class BlindedJudge:
    """The blinded LLM-as-judge (test-review B2). DIFFERENT model + prompt from the Internal Critic
    (`claude-sonnet-4-6` @ temperature 0.0 — Sonnet supports temperature, so deterministic — vs the
    Critic's `claude-opus-4-8` effort high), and blind to the Critic's output. v1 deterministic offline
    surrogate; the real Sonnet judge replaces the surrogate bodies with an API call."""

    config = RoleConfig(
        model_id=SONNET_4_6,
        temperature=0.0,  # Sonnet accepts temperature → deterministic scores (B2)
        system_prompt_template=_JUDGE_PROMPT,
    )

    # --- calibration target (B3) over the gap-5 anchors -----------------------------------------

    def score_anchor(self, anchor) -> JudgeScore:
        """The blinded judge's target score for a calibration anchor (test-review B3). v1 OFFLINE seed:
        emit the anchor's hand-assigned `target_scores` as the external target — explicitly sanctioned
        for the offline seed by [[2026-06-02-critic-calibration-anchors]] §B.2 (the seed targets ARE
        'what a good judge says'). The real Sonnet judge replaces this body by scoring
        `anchor.build()`'s draft via the prompt above; the harness/MAE/rank-corr code is unchanged.
        The judge never sees the Critic's score for the anchor (blinding)."""
        t = anchor.target_scores
        return JudgeScore(F1=_clamp(int(t["F1"])), F2=_clamp(int(t["F2"])), F3="sufficient",
                          justification="v1 offline blinded-judge seed target (decision §B.2)")

    # --- competitiveness (B4) — the independent positive-merit rubric ---------------------------

    def score(self, ji: JudgeInput) -> JudgeScore:
        """Score one source-blinded proposal (test-review B4). INDEPENDENT basis from the Critic: a
        POSITIVE evidence/structure-merit rubric (build UP from a floor), not the Critic's penalty-from-
        baseline — so the judge can disagree with the Critic. Deterministic; reads only structural
        features (NEVER `ji.source` — the blinding) and never the Critic's output. v1 surrogate of the
        Sonnet judge."""
        ref_bonus = 1 if ji.n_references >= 30 else 0
        f1 = 5
        f1 += 1 if ji.has_central_hypothesis else -1
        f1 += 1 if ji.has_innovation else 0
        f1 += ref_bonus
        f1 -= 3 * ji.n_overclaims
        f2 = 5
        f2 += 1 if ji.n_aims >= 3 else 0
        f2 += ref_bonus
        f2 -= 3 * ji.n_overclaims
        f3 = "sufficient" if (ji.has_central_hypothesis and ji.n_aims >= 2) else "insufficient"
        return JudgeScore(
            F1=_clamp(f1), F2=_clamp(f2), F3=f3,
            justification=f"merit: hyp={ji.has_central_hypothesis} innov={ji.has_innovation} "
                          f"aims={ji.n_aims} refs={ji.n_references} overclaims={ji.n_overclaims}",
        )


def live_judge():  # pragma: no cover — production path, not exercised in the offline v1 suite
    """The production blinded judge backed by the live Sonnet API (decision §B/§C). Network + LLM
    gated and NOT wired in v1 — the offline suite uses the deterministic `BlindedJudge` surrogate. When
    wired, this returns a judge whose `score`/`score_anchor` call `claude-sonnet-4-6` @ temp 0 with the
    §C prompt; the calibration/competitiveness harness is unchanged (same `score`/`score_anchor` API)."""
    raise NotImplementedError(
        "the live Sonnet blinded judge is network-gated and not wired in v1 (decision §B); "
        "the offline suite uses the deterministic BlindedJudge surrogate"
    )
