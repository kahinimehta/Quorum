"""competitiveness.py — AI proposals vs matched funded human grants [tester, builder 3].

Implements: test_review_contract.md part B4 (AI proposals' blinded factor scores vs MATCHED funded
            human proposals; report the gap) + B2 blinding (source identity hidden + order randomized).
            Decision: build/decisions/2026-06-02-eval-methodology.md §A (matching), §C (blinding).
Generic role: the competitiveness comparison — the AI vs the funded-human bar. Read-only, outside the
              loop. Owner: S7 (builder 3) shipped the pooled plumbing; S8 (builder 3) adds the
              matched-STRATUM rigor (per-mechanism means/spread/n + gap), the statistical treatment, and
              the live-judge gate. The go/no-go lives in `tests/review.py` (part C).

Offline + deterministic: runs the agent on the 5 fixtures (the same deterministic surrogate roles as
`cua.nih.run`), maps AI proposals + matched human references to a common source-blinded `JudgeInput`,
shuffles with a FIXED seed (so the run is byte-reproducible), judge-scores, and reports the per-factor
AI−human gap — pooled AND per matched stratum (mechanism). The RePORTER references are abstracted
stand-ins (contamination rule; reporter_reference). The live LLM judge is gated (`use_live_judge`).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from blinded_judge import BlindedJudge, JudgeInput
from reporter_reference import matched_subset

_BLINDING_SEED = 20260602  # fixed → deterministic blinded order (decision §C; no wall-clock/RNG drift)


@dataclass
class CompetitivenessResult:
    """Per-factor AI vs matched-human means + the gap (test-review B4). v1 basic; S8 expands."""

    ai_mean: dict[str, float]
    human_mean: dict[str, float]
    gap: dict[str, float]  # ai_mean − human_mean (≥0 ⇒ AI at/above the funded bar on that factor)
    n_ai: int
    n_human: int

    def as_dict(self) -> dict:
        return {"ai_mean": self.ai_mean, "human_mean": self.human_mean, "gap": self.gap,
                "n_ai": self.n_ai, "n_human": self.n_human}


def _ai_judge_inputs() -> list[JudgeInput]:
    """Run the agent on every fixture (offline, deterministic) and map each Proposal+Audit to a
    source-blinded structural JudgeInput. n_overclaims comes from the final Audit's overclaim_check
    (the resisted proposals carry 0 — the loop hedged/dropped the bait)."""
    from cua.nih.run import _build_orchestrator, RUN_CONFIG
    from cua.nih.task import build_task
    from testdata import all_fixtures, validate

    out: list[JudgeInput] = []
    for fx in all_fixtures():
        validate(fx)
        proposal, _trace, audit = _build_orchestrator().run(build_task(fx), RUN_CONFIG)
        n_overclaims = sum(1 for r in audit.overclaim_check if not r.ok)
        has_innovation = any(s.name == "innovation" and s.text for s in proposal.sections)
        out.append(JudgeInput(
            source="AI",
            title=proposal.project_title,
            has_central_hypothesis=bool(proposal.central_hypothesis),
            has_innovation=has_innovation,
            n_aims=len(proposal.aims),
            n_references=len(proposal.references),
            n_overclaims=n_overclaims,
            mechanism=getattr(fx.grant_call, "mechanism", ""),
        ))
    return out


def _human_judge_inputs() -> list[JudgeInput]:
    """The MATCHED funded-human references (B4): for each AI proposal, its matched subset by mechanism +
    domain (reporter_reference.matched_subset), de-duplicated. Funded human work (abstracted) carries no
    overclaim signal → n_overclaims = 0, has_innovation = True."""
    from testdata import all_fixtures

    seen: dict[str, JudgeInput] = {}
    for fx in all_fixtures():
        gc = fx.grant_call
        for ref in matched_subset(getattr(gc, "mechanism", ""), getattr(gc, "title", "")):
            if ref.app_id in seen:
                continue
            seen[ref.app_id] = JudgeInput(
                source="human",
                title=ref.app_id,
                has_central_hypothesis=ref.has_central_hypothesis,
                has_innovation=True,
                n_aims=ref.n_aims,
                n_references=ref.est_references,
                n_overclaims=0,
                mechanism=ref.activity_code,
            )
    return list(seen.values())


def competitiveness(judge: BlindedJudge | None = None) -> CompetitivenessResult:
    """Score AI proposals vs matched human references under the blinded judge and report the per-factor
    gap (test-review B4). Source identity is hidden from the judge (it ignores `JudgeInput.source`) and
    the pooled order is randomized with a fixed seed (deterministic)."""
    judge = judge if judge is not None else BlindedJudge()
    ai = _ai_judge_inputs()
    human = _human_judge_inputs()

    pooled = ai + human
    random.Random(_BLINDING_SEED).shuffle(pooled)  # order randomized (B2); fixed seed → reproducible

    scores = {id(ji): judge.score(ji) for ji in pooled}  # judge is blind to ji.source

    def _mean(items: list[JudgeInput], factor: str) -> float:
        vals = [getattr(scores[id(ji)], factor) for ji in items]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    ai_mean = {"F1": _mean(ai, "F1"), "F2": _mean(ai, "F2")}
    human_mean = {"F1": _mean(human, "F1"), "F2": _mean(human, "F2")}
    gap = {d: round(ai_mean[d] - human_mean[d], 4) for d in ("F1", "F2")}
    return CompetitivenessResult(ai_mean=ai_mean, human_mean=human_mean, gap=gap,
                                 n_ai=len(ai), n_human=len(human))


# === S8 — matched-stratum rigor + statistical treatment =========================================


def _mean_std(vals: list[float]) -> tuple[float, float]:
    """Mean + SAMPLE std (n−1). std = 0.0 for n < 2 (no spread estimable — flagged, not faked)."""
    if not vals:
        return 0.0, 0.0
    m = sum(vals) / len(vals)
    if len(vals) < 2:
        return round(m, 4), 0.0
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return round(m, 4), round(var ** 0.5, 4)


@dataclass
class StratumResult:
    """One matched stratum (by mechanism; B4 'matched'): per-factor AI vs human mean ± std + the gap,
    with the per-arm n. Descriptive statistics only — small n, so no p-values are claimed."""

    mechanism: str
    ai_mean: dict[str, float]
    human_mean: dict[str, float]
    ai_std: dict[str, float]
    human_std: dict[str, float]
    gap: dict[str, float]
    n_ai: int
    n_human: int

    def as_dict(self) -> dict:
        return {"mechanism": self.mechanism, "ai_mean": self.ai_mean, "human_mean": self.human_mean,
                "ai_std": self.ai_std, "human_std": self.human_std, "gap": self.gap,
                "n_ai": self.n_ai, "n_human": self.n_human}


@dataclass
class StratifiedCompetitiveness:
    """The matched-stratum competitiveness result (B4). `as_dict()` is a SUPERSET of the pooled
    `CompetitivenessResult` shape (top-level ai_mean/human_mean/gap/n_ai/n_human stay, so the S7 plumbing
    + EvalReport readers are unchanged) PLUS per-stratum `strata` + the `method` note."""

    pooled: CompetitivenessResult
    strata: list[StratumResult]
    method: str

    def as_dict(self) -> dict:
        d = self.pooled.as_dict()
        d["strata"] = {s.mechanism: s.as_dict() for s in self.strata}
        d["method"] = self.method
        return d


def competitiveness_stratified(judge: BlindedJudge | None = None, *,
                               use_live_judge: bool = False) -> StratifiedCompetitiveness:
    """AI vs matched funded-human references, reported per MATCHED stratum (mechanism) + pooled
    (test-review B4). Blinded (judge ignores `source`) + order-randomized (fixed seed). `use_live_judge`
    selects the gated live Sonnet judge (NotImplementedError offline — decision §B); v1 uses the
    deterministic surrogate. Statistical treatment is descriptive (mean ± sample std + n per arm);
    small n is flagged in `method`, not papered over with significance claims."""
    if use_live_judge:
        from blinded_judge import live_judge
        judge = live_judge()  # gated — raises offline
    judge = judge if judge is not None else BlindedJudge()

    ai = _ai_judge_inputs()
    human = _human_judge_inputs()
    pooled_items = ai + human
    random.Random(_BLINDING_SEED).shuffle(pooled_items)  # order randomized (B2); deterministic
    scores = {id(ji): judge.score(ji) for ji in pooled_items}  # blind to source

    def _arm_stats(items: list[JudgeInput]) -> tuple[dict, dict]:
        means, stds = {}, {}
        for d in ("F1", "F2"):
            means[d], stds[d] = _mean_std([getattr(scores[id(ji)], d) for ji in items])
        return means, stds

    mechanisms = sorted({ji.mechanism for ji in pooled_items if ji.mechanism})
    strata: list[StratumResult] = []
    for mech in mechanisms:
        ai_m = [ji for ji in ai if ji.mechanism == mech]
        hu_m = [ji for ji in human if ji.mechanism == mech]
        if not ai_m or not hu_m:
            continue  # an unmatched stratum (no human OR no AI item) is not a fair comparison
        ai_mean, ai_std = _arm_stats(ai_m)
        hu_mean, hu_std = _arm_stats(hu_m)
        strata.append(StratumResult(
            mechanism=mech, ai_mean=ai_mean, human_mean=hu_mean, ai_std=ai_std, human_std=hu_std,
            gap={d: round(ai_mean[d] - hu_mean[d], 4) for d in ("F1", "F2")},
            n_ai=len(ai_m), n_human=len(hu_m),
        ))

    pooled = competitiveness(judge)
    method = (
        "blinded (source hidden) + order-randomized (fixed seed); matched by mechanism; descriptive "
        f"stats (mean ± sample std, per-arm n) — small n, no significance claimed; "
        f"judge={'live-sonnet' if use_live_judge else 'v1-surrogate'}"
    )
    return StratifiedCompetitiveness(pooled=pooled, strata=strata, method=method)
