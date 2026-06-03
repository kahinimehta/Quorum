"""eval_report.py — the EvalReport assembly [tester, builder 3].

Implements: test_review_contract.md part B (EvalReport: { calibration:{mae, rank_corr},
            competitiveness:{…}, n }); contracts.md §1.10 (`Audit.calibration`). Decision:
            build/decisions/2026-06-02-eval-methodology.md §D.
Generic role: the eval's single emitted artifact — the calibration number (what licenses the Critic as
              reward), the competitiveness gap, and the load-bearing contamination + dev-5 findings.
              Read-only, outside the loop. Owner: S7 (builder 3).

Offline + deterministic: composes `critic_calibration.calibrate` (B3), `competitiveness` (B4),
`reporter_reference.contamination_report` (the HARD rule), and `critic_calibration.dev5_quantification`
(dev-5). No network, no LLM — every input is a deterministic v1 surrogate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from competitiveness import competitiveness_stratified
from critic_calibration import calibrate, dev5_quantification
from reporter_reference import contamination_report


@dataclass
class EvalReport:
    """`{ calibration:{mae, rank_corr}, competitiveness:{…}, n }` (test-review part B). Extended with
    the per-anchor score vectors (so the compression is visible), the HARD `contamination` finding, and
    the `dev5` retune projection — all read-only analysis the S8 ReviewReport consumes."""

    calibration: dict  # { mae:{F1,F2}, rank_corr:{F1,F2}, internal, external, anchor_ids }
    competitiveness: dict  # pooled { ai_mean, human_mean, gap, n_ai, n_human } + { strata, method } (S8)
    contamination: dict  # { honored: bool, exemplar_overlap, input_leaks, n_reference_items }
    dev5: dict  # { current, projected_retune, finding } — the dev-5 quantification + joint-retune projection
    n: int  # held-out calibration set size (the gap-5 anchors)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def build_eval_report() -> EvalReport:
    """Run the full eval (B1–B4 + contamination + dev-5) and assemble the EvalReport. Offline,
    deterministic — the single entry point the S7 test + the S8 review call."""
    cal = calibrate()
    comp = competitiveness_stratified()  # matched strata + pooled (S8); as_dict() is a pooled superset
    contam = contamination_report()
    dev5 = dev5_quantification()
    return EvalReport(
        calibration={
            "mae": cal.mae, "rank_corr": cal.rank_corr,
            "internal": cal.internal, "external": cal.external, "anchor_ids": cal.anchor_ids,
        },
        competitiveness=comp.as_dict(),
        contamination=contam,
        dev5=dev5,
        n=cal.n,
    )


def main() -> int:
    """`python tests/eval/eval_report.py` — emit the EvalReport as JSON. Offline, deterministic."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for p in (root / "src", root, Path(__file__).resolve().parent):
        sys.path.insert(0, str(p))
    print(build_eval_report().to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
