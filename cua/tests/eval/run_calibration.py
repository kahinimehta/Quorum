"""run_calibration.py — Critic calibration over the REAL drafts via the live blinded judge [builder 3].

CALIB-LIVE (build/live/CALIB-LIVE_relay.md): our grading is uncalibrated on every real run
(`Audit.calibration.external_scores/mae/rank_corr = None`). This runner closes that: for each run-id it
loads `<run>.proposal.json`, scores it with the BLINDED judge (live Sonnet when `CUA_LIVE`+key, else the
deterministic surrogate), reads the Critic's `internal_scores` from `<run>.audit.json`, and computes
per-factor MAE + Spearman — emitting `outputs/calibration.json` with the per-run {internal, external},
the aggregate calibration, and the external F1/F2/F3 keyed by (n, rounds) for the scaling/compute curves.
The agent does NOT re-run — the judge scores the EXISTING drafts.

INDEPENDENCE (load-bearing): the judge is handed ONLY the proposal text (`score_proposal` →
`_render_proposal`), NEVER the Audit / `internal_scores` / writer trace; the Critic is never tuned to
agree. This runner reads `internal_scores` purely to compute the comparison metric — it is never passed
to the judge. Read-only, outside the loop; no agent/spine change. Reuses `critic_calibration.{mae,spearman}`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_OUTPUTS = Path(__file__).resolve().parents[2] / "outputs"

# Default run set (CALIB-LIVE): full3 + the 8 sweep runs (the n-axis at r=3 and the rounds-axis at n=3).
DEFAULT_RUN_IDS = [
    "full3",
    "sw_n1_r3", "sw_n3_r3", "sw_n5_r3", "sw_n10_r3", "sw_n20_r3",  # n-axis (rounds=3)
    "sw_n3_r6", "sw_n3_r12", "sw_n3_r24",                          # rounds-axis (n=3)
]

_SWEEP_RE = re.compile(r"^sw_n(\d+)_r(\d+)$")


def _parse_n_rounds(run_id: str) -> tuple[int | None, int | None]:
    """(n, rounds) from a sweep id `sw_n<N>_r<R>`; (None, None) for a non-sweep id (e.g. full3)."""
    m = _SWEEP_RE.match(run_id)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def calibrate_runs(run_ids: list[str] | None = None, outputs_dir: Path | None = None, judge=None) -> dict:
    """Score each run's proposal with the blinded judge and compute the Critic's calibration vs it.

    For each run-id: load `<run>.proposal.json` + `<run>.audit.json`; read the Critic's
    `internal_scores`; count overclaims from the Audit's `overclaim_check` (the deterministic ladder, NOT
    the Critic's score) and pass that to the surrogate only; score the proposal with the BLIND judge
    (proposal text only). Aggregate per-factor MAE + Spearman over F1/F2 (F3 is sufficiency, reported but
    not numerically correlated). Returns the `calibration.json` payload (deterministic offline)."""
    from blinded_judge import BlindedJudge
    from critic_calibration import mae, spearman
    from cua import llm

    run_ids = list(run_ids) if run_ids is not None else list(DEFAULT_RUN_IDS)
    outputs_dir = Path(outputs_dir) if outputs_dir is not None else _OUTPUTS
    judge = judge if judge is not None else BlindedJudge()

    runs: dict[str, dict] = {}
    internal_vec: dict[str, list[int]] = {"F1": [], "F2": []}
    external_vec: dict[str, list[int]] = {"F1": [], "F2": []}

    for rid in run_ids:
        prop_path = outputs_dir / f"{rid}.proposal.json"
        audit_path = outputs_dir / f"{rid}.audit.json"
        if not (prop_path.exists() and audit_path.exists()):
            runs[rid] = {"error": "missing proposal/audit"}
            continue
        proposal = json.loads(prop_path.read_text(encoding="utf-8"))
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        internal = audit.get("calibration", {}).get("internal_scores", {}) or {}
        n_over = sum(1 for r in audit.get("overclaim_check", []) if not r.get("ok", True))
        n, rounds = _parse_n_rounds(rid)
        try:
            # BLIND: the judge receives ONLY `proposal` (+ n_over for the surrogate rubric); never `audit`/internal.
            js = judge.score_proposal(proposal, n_overclaims=n_over)
        except Exception as e:  # e.g. LiveStructuredOutputError — record + keep the batch going (legible)
            runs[rid] = {"n": n, "rounds": rounds, "internal": _internal3(internal),
                         "error": f"{type(e).__name__}: {e}"}
            continue
        runs[rid] = {
            "n": n, "rounds": rounds,
            "internal": _internal3(internal),
            "external": {"F1": js.F1, "F2": js.F2, "F3": js.F3},
            "external_justification": js.justification,
            "n_overclaims": n_over,
        }
        for d in ("F1", "F2"):
            if isinstance(internal.get(d), (int, float)):
                internal_vec[d].append(int(internal[d]))
                external_vec[d].append(getattr(js, d))

    aggregate = {"mae": {}, "rank_corr": {}, "n": len(internal_vec["F1"])}
    for d in ("F1", "F2"):
        if internal_vec[d]:
            aggregate["mae"][d] = round(mae(internal_vec[d], external_vec[d]), 4)
            aggregate["rank_corr"][d] = round(spearman(internal_vec[d], external_vec[d]), 4)

    return {
        "judge": "live-sonnet" if llm.is_live() else "v1-surrogate",
        "model": BlindedJudge.config.model_id,
        "independence": (
            "blind: the judge received ONLY each proposal's text (score_proposal → _render_proposal); "
            "never internal_scores / CritiqueReport / trace. F3 is sufficiency (not in MAE/rank-corr)."
        ),
        "runs": runs,
        "aggregate": aggregate,
        "by_axis": _by_axis(runs),
    }


def _internal3(internal: dict) -> dict:
    return {"F1": internal.get("F1"), "F2": internal.get("F2"), "F3": internal.get("F3")}


def _by_axis(runs: dict[str, dict]) -> dict:
    """The compute-curve view: the external (+ internal) F1/F2/F3 along the two sweep axes — the n-axis
    at rounds=3 and the rounds-axis at n=3 — so a viewer can plot external-quality-vs-compute beside the
    Critic's (mirrors render_sweep's NAX/RAX). Only scored (non-error) sweep runs are included."""
    def _row(rid: str) -> dict | None:
        r = runs.get(rid)
        if not r or "external" not in r:
            return None
        return {"run_id": rid, "n": r["n"], "rounds": r["rounds"],
                "internal": r["internal"], "external": r["external"]}

    n_axis = [row for n in (1, 3, 5, 10, 20) if (row := _row(f"sw_n{n}_r3"))]
    rounds_axis = [row for r in (3, 6, 12, 24) if (row := _row(f"sw_n3_r{r}"))]
    return {"n_axis": n_axis, "rounds_axis": rounds_axis}


def main(argv: list[str] | None = None) -> int:
    """`python tests/eval/run_calibration.py [run_id ...]` — score the drafts + emit outputs/calibration.json.
    Offline (default) uses the deterministic surrogate judge; `CUA_LIVE`+key uses the live Sonnet judge."""
    # sys.path bootstrap (mirrors critic_calibration.main) so the script resolves `cua` + the sibling modules.
    root = Path(__file__).resolve().parents[2]
    for p in (root / "src", root, Path(__file__).resolve().parent):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    argv = sys.argv[1:] if argv is None else argv
    run_ids = argv or None
    report = calibrate_runs(run_ids)

    out_path = _OUTPUTS / "calibration.json"
    _OUTPUTS.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"CALIB-LIVE — judge={report['judge']} ({report['model']}) over {len(report['runs'])} run(s)")
    print("-" * 78)
    for rid, r in report["runs"].items():
        if "external" not in r:
            print(f"  {rid:12s}  {r.get('error', 'skipped')}")
            continue
        i, e = r["internal"], r["external"]
        print(f"  {rid:12s}  internal F1={i['F1']} F2={i['F2']} F3={i['F3']}  |  "
              f"external F1={e['F1']} F2={e['F2']} F3={e['F3']}")
    print("-" * 78)
    agg = report["aggregate"]
    print(f"aggregate (n={agg['n']}): MAE={agg['mae']}  rank_corr={agg['rank_corr']}")
    print(f"OK — wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
