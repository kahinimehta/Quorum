"""critic_calibration.py — Critic calibration over the gap-5 anchors [tester, builder 3].

Implements: test_review_contract.md part B3 (compare `Audit.calibration.internal_scores` — the Critic —
            against the blinded judge on a held-out set: per-factor MAE + rank correlation; THIS number
            licenses the Critic as a reward signal); contracts.md §1.10 (`Audit.calibration.{external_
            scores, mae, rank_corr}`, None until the eval fills them); §2.1 (F1/F2 scored). Decisions:
            2026-06-02-eval-methodology.md §D, 2026-06-02-critic-calibration-anchors.md,
            2026-06-02-critic-range-retune.md (dev-5 quantification + the joint retune projection).
Generic role: the calibration computation — internal (Critic) vs external (blinded judge) over the
              scored drafts spanning 1–9 (the anchors). Read-only, outside the loop. Owner: S7 (builder 3).

Offline + deterministic: runs the real (deterministic v1) Internal Critic over each anchor's grounded
draft (no network — `calibration_anchors.internal_scores`), takes the blinded judge's target, and
computes per-factor MAE + Spearman rank-corr. Also derives the **dev-5 retune projection** (a what-if
re-derivation from the anchors' overclaim/orphan counts — NEVER mutates `roles/critic.py`; the eval
stays independent of the role it measures — Boundaries / principle 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from blinded_judge import BlindedJudge


# === metrics (pure, no numpy — deps stay minimal) ===============================================


def mae(internal: list[float], external: list[float]) -> float:
    """Mean absolute error |internal − external| (test-review B3). Equal-length, ≥1 point."""
    assert internal and len(internal) == len(external), "MAE needs equal, non-empty score vectors"
    return sum(abs(i - e) for i, e in zip(internal, external)) / len(internal)


def _ranks(xs: list[float]) -> list[float]:
    """Fractional (average-tie) ranks, 1 = smallest — the basis of Spearman's ρ."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based average rank over the tie block
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(internal: list[float], external: list[float]) -> float:
    """Spearman rank correlation = Pearson on fractional ranks (test-review B3). Returns 0.0 when
    either side has zero rank-variance (a constant vector — no orderable signal), flagged rather than
    NaN so the report stays JSON-clean."""
    assert internal and len(internal) == len(external), "rank-corr needs equal, non-empty vectors"
    ri, re = _ranks(internal), _ranks(external)
    n = len(ri)
    mi, me = sum(ri) / n, sum(re) / n
    cov = sum((a - mi) * (b - me) for a, b in zip(ri, re)) / n
    vi = sum((a - mi) ** 2 for a in ri) / n
    ve = sum((b - me) ** 2 for b in re) / n
    if vi == 0 or ve == 0:
        return 0.0
    return cov / ((vi ** 0.5) * (ve ** 0.5))


# === calibration result ========================================================================


@dataclass
class CalibrationResult:
    """Per-factor MAE + rank-corr of the Critic vs the blinded judge over the anchors, with the raw
    per-anchor score vectors (so a reviewer can see the compression, not just the summary)."""

    mae: dict[str, float]
    rank_corr: dict[str, float]
    internal: dict[str, list[int]]  # per factor, per anchor (Critic)
    external: dict[str, list[int]]  # per factor, per anchor (blinded judge)
    anchor_ids: list[str]
    n: int

    def as_dict(self) -> dict:
        return {
            "mae": self.mae, "rank_corr": self.rank_corr,
            "internal": self.internal, "external": self.external,
            "anchor_ids": self.anchor_ids, "n": self.n,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationResult":
        """Rebuild a CalibrationResult from `EvalReport.calibration` — so a consumer of the single entry
        point `build_eval_report()` (e.g. tests/review.py) can `fill_calibration` without re-running."""
        anchor_ids = d.get("anchor_ids", [])
        return cls(mae=d["mae"], rank_corr=d["rank_corr"], internal=d.get("internal", {}),
                   external=d.get("external", {}), anchor_ids=anchor_ids, n=d.get("n", len(anchor_ids)))


def _scored_dims() -> tuple[str, ...]:
    from cua.nih.framework import SCORED_DIMENSIONS
    return SCORED_DIMENSIONS


def _result(internal: dict[str, list[int]], external: dict[str, list[int]],
            anchor_ids: list[str]) -> CalibrationResult:
    dims = _scored_dims()
    return CalibrationResult(
        mae={d: round(mae(internal[d], external[d]), 4) for d in dims},
        rank_corr={d: round(spearman(internal[d], external[d]), 4) for d in dims},
        internal=internal, external=external, anchor_ids=anchor_ids, n=len(anchor_ids),
    )


def calibrate(critic=None, judge: BlindedJudge | None = None) -> CalibrationResult:
    """Run the Internal Critic + the blinded judge over the gap-5 anchors and compute per-factor MAE +
    rank-corr (test-review B3). Offline, deterministic. `critic`/`judge` default to the real classes."""
    from cua.roles import InternalCritic
    from cua.nih.calibration_anchors import ANCHORS, internal_scores as critic_scores

    critic = critic if critic is not None else InternalCritic()
    judge = judge if judge is not None else BlindedJudge()
    dims = _scored_dims()

    internal: dict[str, list[int]] = {d: [] for d in dims}
    external: dict[str, list[int]] = {d: [] for d in dims}
    anchor_ids: list[str] = []
    for anchor in ANCHORS:
        anchor_ids.append(anchor.id)
        cs = critic_scores(critic, anchor)  # the Critic's whole-draft {dim: score}
        js = judge.score_anchor(anchor)  # the blinded judge's target
        ext = {"F1": js.F1, "F2": js.F2}
        for d in dims:
            internal[d].append(cs[d])
            external[d].append(ext[d])
    return _result(internal, external, anchor_ids)


# === dev-5: the joint retune PROJECTION (what-if; never mutates roles/critic.py) ================
# Decision 2026-06-02-critic-range-retune.md. The eval RE-DERIVES the Critic score from each anchor's
# observable (overclaim, orphan) counts under proposed weights — a read-only projection that quantifies
# how the joint base+penalty+bar retune would reduce MAE. Applying it to roles/critic.py + the stopping
# bar is builder 1 / operator's (keeps the eval independent of the role it measures — Boundaries).

RETUNE = {"base": 8, "overclaim_penalty": 3, "orphan_penalty": 5, "unmet_penalty": 1, "bar": 6}
_CURRENT = {"base": 7, "overclaim_penalty": 3, "orphan_penalty": 3, "unmet_penalty": 1, "bar": 5}


def _dimension_counts(anchor) -> dict[str, tuple[int, int]]:
    """Per scored dimension, the (n_overclaim, n_orphan) the Critic would count for this anchor —
    re-derived from the SAME public, enforce-only machinery the Critic uses (`level`/`resolve_grade`/
    `permitted`, and the Grounder's orphan list). Read-only; not a copy of the Critic role."""
    from cua.grounding import Grounder, level, resolve_grade
    from cua.types import LEVEL_RANK, permitted

    draft, source_set, evidence = anchor.build()
    grounded, report = Grounder().ground(draft, source_set)
    orphan_ids = set(report.orphan_ids)
    claims = grounded.draft.claims()
    out: dict[str, tuple[int, int]] = {}
    for dim in _scored_dims():
        dim_claims = [c for c in claims if c.serves_dimension == dim]
        n_over = sum(1 for c in dim_claims
                     if LEVEL_RANK[level(c.text)] > LEVEL_RANK[permitted(resolve_grade(c, evidence)[0])])
        n_orphan = sum(1 for c in dim_claims if any(r in orphan_ids for r in c.reference_ids))
        out[dim] = (n_over, n_orphan)
    return out


def _projected_score(n_over: int, n_orphan: int, params: dict) -> int:
    raw = params["base"] - params["overclaim_penalty"] * n_over - params["orphan_penalty"] * n_orphan
    return max(1, min(9, raw))


def projected_calibration(params: dict = RETUNE) -> CalibrationResult:
    """The calibration the Critic WOULD show under `params` (default = the proposed retune), vs the same
    blinded-judge targets. Quantifies the dev-5 remedy without touching the role."""
    from cua.nih.calibration_anchors import ANCHORS

    judge = BlindedJudge()
    dims = _scored_dims()
    internal: dict[str, list[int]] = {d: [] for d in dims}
    external: dict[str, list[int]] = {d: [] for d in dims}
    anchor_ids: list[str] = []
    for anchor in ANCHORS:
        anchor_ids.append(anchor.id)
        counts = _dimension_counts(anchor)
        js = judge.score_anchor(anchor)
        ext = {"F1": js.F1, "F2": js.F2}
        for d in dims:
            internal[d].append(_projected_score(*counts[d], params))
            external[d].append(ext[d])
    return _result(internal, external, anchor_ids)


def dev5_quantification() -> dict:
    """The dev-5 finding for the EvalReport / handoff: the current Critic's compression (MAE + the
    capped-at-base top) vs the projected joint retune. Read-only analysis."""
    current = calibrate()
    projected = projected_calibration(RETUNE)
    return {
        "current": {"mae": current.mae, "rank_corr": current.rank_corr,
                    "internal": current.internal, "external": current.external},
        "projected_retune": {"params": RETUNE, "mae": projected.mae, "rank_corr": projected.rank_corr,
                             "internal": projected.internal},
        "finding": (
            "v1 Critic surrogate caps clean dims at base=7, so it cannot reach the high anchors' 8 "
            "(top-of-range compression); rank ordering already holds. The joint base 7→8 / orphan "
            "−3→−5 / bar 5→6 retune reduces per-factor MAE while preserving the 5-fixture revise/pass "
            "behavior. Application is builder 1 (critic.py) + operator (stopping bar) — relayed, not "
            "applied here (eval independence)."
        ),
    }


# === fill Audit.calibration.{external_scores, mae, rank_corr} (B3; §1.10) =======================


def fill_calibration(calibration, result: CalibrationResult, external_scores: dict | None = None):
    """Return a NEW `Calibration` with the eval-computed `mae`/`rank_corr` (and optional per-proposal
    `external_scores`) filled in — the §1.10 fields the agent leaves None until the eval (S7) fills
    them. Read-only / outside-the-loop: produces a copy via `dataclasses.replace`, never mutates a live
    run (test-review Boundaries). `calibration` is a `cua.trace.Calibration`."""
    return replace(
        calibration,
        external_scores=external_scores if external_scores is not None else calibration.external_scores,
        mae=dict(result.mae),
        rank_corr=dict(result.rank_corr),
    )


# === offline run aid (mirrors invariants.py::main; not the pytest suite — that is test_eval.py) =


def main() -> int:
    """`python tests/eval/critic_calibration.py` — print the calibration table + the dev-5 retune
    projection. Offline, no deps, deterministic."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    cur = calibrate()
    proj = projected_calibration(RETUNE)
    print("S7 Critic calibration — internal (Critic) vs external (blinded judge), over the gap-5 anchors")
    print("-" * 82)
    for d in _scored_dims():
        print(f"  {d}: internal={cur.internal[d]} external={cur.external[d]} "
              f"MAE={cur.mae[d]} rank_corr={cur.rank_corr[d]}")
    print(f"  anchors={cur.anchor_ids} (n={cur.n})")
    print("-" * 82)
    print(f"dev-5 retune projection {RETUNE}:")
    for d in _scored_dims():
        print(f"  {d}: internal'={proj.internal[d]} → MAE {cur.mae[d]} → {proj.mae[d]} "
              f"(rank_corr {cur.rank_corr[d]} → {proj.rank_corr[d]})")
    print("-" * 82)
    print("OK — calibration computed (offline; see build/decisions/2026-06-02-critic-range-retune.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
