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

from pydantic import BaseModel, Field, model_validator

from cua import llm
from cua.config import RoleConfig
from cua.nih.framework import SONNET_4_6
from cua.trace import TraceRecorder


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


# === live path (real Sonnet judge over a real proposal) — forced-tool-use schema + render ========
# CALIB-LIVE (build/live/CALIB-LIVE_relay.md): the live blinded judge replaces the surrogate body with a
# real `claude-sonnet-4-6` @ temp 0 call (gated by `CUA_LIVE` + `ANTHROPIC_API_KEY`, lazy `anthropic`),
# scoring the proposal's TEXT. INDEPENDENCE (load-bearing): the judge receives ONLY the proposal — never
# the Audit / Critic `internal_scores` / writer trace — and is a different model+prompt from the Critic
# (Opus, effort high). The surrogate stays the DEFAULT offline → the eval suite is byte-identical.


class _JudgeOut(BaseModel):
    """The live judge's forced-tool output (decision §C): F1/F2 1–9 (higher=better) + F3 sufficiency +
    a justification. Tolerant of the model flattening a factor to a bare number / casing F3 freely
    (live-structured-output-robustness); F1/F2 are clamped and F3 normalized at the JudgeScore boundary."""

    F1: int = Field(description="Significance + Innovation, 1-9 (higher = better)")
    F2: int = Field(description="Approach — rigor & feasibility, 1-9 (higher = better)")
    F3: str = Field(default="sufficient", description="Investigator + Environment: 'sufficient' or 'insufficient'")
    justification: str = Field(default="")

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, dict):
            for k in ("F1", "F2"):  # a factor returned as a bare numeric string → int
                v = data.get(k)
                if isinstance(v, str) and v.strip().lstrip("-").isdigit():
                    data = {**data, k: int(v.strip())}
        return data


def _render_proposal(proposal: dict) -> str:
    """Serialize a `<run>.proposal.json` into the judge's user prompt — the draft TEXT ONLY (title +
    central hypothesis + Significance/Innovation + each Specific Aim with its citations + the reference
    list). BLIND by construction: reads only `proposal` fields, NEVER the Audit / `internal_scores` /
    trace (independence — CALIB-LIVE / decision §C)."""
    sections = {s.get("name"): s.get("text", "") for s in proposal.get("sections", [])}
    lines = [
        f"TITLE: {proposal.get('project_title', '')}",
        f"CENTRAL HYPOTHESIS: {proposal.get('central_hypothesis', '')}",
        f"SIGNIFICANCE:\n{sections.get('significance', '(none)')}",
        f"INNOVATION:\n{sections.get('innovation', '(none)')}",
        "SPECIFIC AIMS:",
    ]
    for aim in proposal.get("aims", []):
        cites = ", ".join(aim.get("citation_ids", [])) or "(none)"
        lines.append(
            f"  {aim.get('id', 'aim')}: {aim.get('hypothesis', '')}\n"
            f"    Rationale: {aim.get('rationale', '')}\n"
            f"    Approach: {aim.get('approach', '')}\n"
            f"    Expected outcomes: {aim.get('expected_outcomes', '')}\n"
            f"    Pitfalls/alternatives: {aim.get('pitfalls_alternatives', '')}\n"
            f"    Citations: {cites}"
        )
    refs = proposal.get("references", [])
    ref_list = "; ".join(f"[{r.get('id', '')}] {r.get('title', '')}" for r in refs[:40])
    lines.append(f"REFERENCES ({len(refs)}): {ref_list or '(none)'}")
    return "\n".join(lines)


def _judge_input_from_proposal(proposal: dict, n_overclaims: int = 0) -> "JudgeInput":
    """Map a `<run>.proposal.json` (+ the deterministic overclaim count the runner reads from the Audit's
    `overclaim_check` ladder — NOT the Critic's `internal_scores`) to the structural `JudgeInput` the
    OFFLINE surrogate scores. Mirrors `competitiveness._ai_judge_inputs` so the surrogate basis is the
    same positive-merit rubric (independence preserved; the Critic is never read)."""
    sections = proposal.get("sections", [])
    has_innovation = any(s.get("name") == "innovation" and s.get("text") for s in sections)
    return JudgeInput(
        source="AI",
        title=proposal.get("project_title", ""),
        has_central_hypothesis=bool(proposal.get("central_hypothesis")),
        has_innovation=has_innovation,
        n_aims=len(proposal.get("aims", [])),
        n_references=len(proposal.get("references", [])),
        n_overclaims=n_overclaims,
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

    # --- calibration over the REAL drafts (CALIB-LIVE) — live Sonnet | surrogate -----------------

    def score_proposal(self, proposal: dict, n_overclaims: int = 0, *, recorder=None) -> JudgeScore:
        """Score a REAL proposal loaded from `<run>.proposal.json` (CALIB-LIVE). LIVE (`is_live()`): real
        Sonnet reads the proposal TEXT ONLY and returns F1/F2 1–9 + F3 sufficiency — BLIND to the Audit /
        Critic `internal_scores` / trace (independence, load-bearing). SURROGATE (the DEFAULT, offline):
        the same positive-merit rubric over the proposal's structure (+ `n_overclaims`, the deterministic
        ladder count the runner passes from the Audit's `overclaim_check` — never the Critic's score), so
        the offline calibration is deterministic + byte-identical. Falls back to the surrogate on
        `LiveUnavailable` (mirrors the agent roles)."""
        if llm.is_live():
            try:
                return self._score_proposal_live(proposal, recorder if recorder is not None else TraceRecorder())
            except llm.LiveUnavailable:
                pass
        return self.score(_judge_input_from_proposal(proposal, n_overclaims))

    def _score_proposal_live(self, proposal: dict, recorder) -> JudgeScore:
        """Real Sonnet (temp 0) scores the proposal's rendered TEXT via forced tool-use → `_JudgeOut`;
        `complete()` records the one TraceEvent (discarded — the eval is not part of the agent trace).
        The prompt carries ONLY `_render_proposal(proposal)` — the Audit / Critic scores never appear."""
        out: _JudgeOut = llm.complete(
            self.config,
            system=self.config.system_prompt_template,
            user=_render_proposal(proposal),
            schema=_JudgeOut,
            trace_role="blinded_judge",
            recorder=recorder,
            input_refs=("proposal",),
        )
        f3 = "sufficient" if str(out.F3).strip().lower().startswith("suff") else "insufficient"
        return JudgeScore(F1=_clamp(int(out.F1)), F2=_clamp(int(out.F2)), F3=f3, justification=out.justification or "")


def live_judge():  # pragma: no cover — production path, not exercised in the offline v1 suite
    """The production blinded judge backed by the live Sonnet API (decision §B/§C). Network + LLM
    gated and NOT wired in v1 — the offline suite uses the deterministic `BlindedJudge` surrogate. When
    wired, this returns a judge whose `score`/`score_anchor` call `claude-sonnet-4-6` @ temp 0 with the
    §C prompt; the calibration/competitiveness harness is unchanged (same `score`/`score_anchor` API)."""
    raise NotImplementedError(
        "the live Sonnet blinded judge is network-gated and not wired in v1 (decision §B); "
        "the offline suite uses the deterministic BlindedJudge surrogate"
    )
