"""review.py — the human-readable ReviewReport + go/no-go [tester, builder 3].

Implements: test_review_contract.md part C (given (Proposal, Trace, Audit, InvariantReport,
            EvalReport?) emit a ReviewReport: which obligations failed and why, the overclaim list,
            citation issues, the calibration summary, and a go/no-go — REVIEW ONLY, never edits the
            proposal); main contract §3 (the three hard invariants are the gate), §1.10 (Audit /
            `calibration`), §1.12 (overclaim). Decisions: 2026-06-02-eval-methodology.md (the eval it
            consumes), 2026-06-02-critic-range-retune.md (dev-5: reports against the LIVE Critic state).
Generic role: the Reviewer — the final, judge-facing verdict on a finished artifact. Read-only, OUTSIDE
              the agent loop (test-review Boundaries). Owner: S8 (builder 3, terminal).

Single eval entry point: `build_eval_report()` (test-review part B) supplies the calibration + matched
competitiveness; the agent run supplies (Proposal, Trace, Audit); `invariants.run_invariants` supplies
the InvariantReport. The go/no-go gates on the three HARD invariants (§3). Offline + deterministic;
reports against the LIVE Critic state (v1 base-7 / bar-5 — the dev-5 retune is ratified-as-analysis,
application deferred to the live-judge pass).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # annotations only — kept out of runtime so the standalone aid needs no path hack
    from critic_calibration import CalibrationResult

# The Critic state the eval/agent is reporting against (decision 2026-06-02-critic-range-retune.md:
# dev-5 RATIFIED as analysis, APPLICATION DEFERRED → the live agent is still base-7 / bar-5).
LIVE_CRITIC_STATE = "v1 surrogate: base-7 / orphan-penalty-3 / bar-5 (dev-5 retune ratified-as-analysis, deferred)"


@dataclass
class ObligationFinding:
    """One unmet obligation (status ≠ satisfied) for the ReviewReport's 'which obligations failed and
    why' (part C). `at_risk` = degraded (e.g. F3 sufficiency the fixtures can't grade), NOT a hard-gate
    failure; `unsatisfied` = unmet. Neither breaks inv-2 (which only gates SATISFIED-without-evidence)."""

    id: str
    dimension: str
    status: str  # at_risk | unsatisfied
    requirement: str
    reason: str


@dataclass
class ReviewReport:
    """The judge-facing review (test-review part C). Carries the failed/unmet obligations, the overclaim
    list, the citation issues, the calibration summary (filled from `Audit.calibration` via the eval),
    the matched competitiveness, and a go/no-go. REVIEW ONLY — assembled from reads; never edits the
    proposal."""

    proposal_title: str
    revision_round: int
    invariants: dict  # { inv-1, inv-2, inv-3, all_passed } (bool)
    unmet_obligations: list[ObligationFinding]
    overclaims: list[dict]  # { claim, claim_level, permitted_level, evidence_grade }
    citation_issues: dict  # { all_in_source_set, orphan_ids, n_references }
    calibration_summary: dict  # { mae, rank_corr, rank_ordering_sound, critic_state, note }
    competitiveness_summary: dict  # { mechanism, stratum_gap, pooled_gap, note }
    decision: str  # "go" | "no-go"
    rationale: str
    caveats: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """A human-readable rendering (the ReviewReport IS human-readable, part C)."""
        inv = self.invariants
        lines = [
            f"REVIEW — {self.proposal_title}  (revision_round={self.revision_round})",
            f"  decision: {self.decision.upper()}",
            f"  rationale: {self.rationale}",
            f"  invariants: inv-1={inv['inv-1']} inv-2={inv['inv-2']} inv-3={inv['inv-3']} "
            f"(all_passed={inv['all_passed']})",
            f"  citation: all_in_source_set={self.citation_issues['all_in_source_set']} "
            f"orphans={self.citation_issues['orphan_ids']} refs={self.citation_issues['n_references']}",
            f"  overclaims: {[o['claim'] for o in self.overclaims] or 'none'}",
            f"  unmet obligations ({len(self.unmet_obligations)}): "
            f"{[f'{o.id}({o.status})' for o in self.unmet_obligations] or 'none'}",
            f"  calibration: mae={self.calibration_summary['mae']} "
            f"rank_corr={self.calibration_summary['rank_corr']} "
            f"(rank_ordering_sound={self.calibration_summary['rank_ordering_sound']}; "
            f"{self.calibration_summary['critic_state']})",
            f"  competitiveness[{self.competitiveness_summary['mechanism']}]: "
            f"stratum_gap={self.competitiveness_summary['stratum_gap']} "
            f"pooled_gap={self.competitiveness_summary['pooled_gap']}",
        ]
        for c in self.caveats:
            lines.append(f"  caveat: {c}")
        return "\n".join(lines)


# === assembly (read-only) =======================================================================

_RANK_ORDERING_BAR = 0.8  # rank-corr at/above this ⇒ the Critic's ordering tracks the judge (soft)


def _unmet_obligations(audit) -> list[ObligationFinding]:
    out: list[ObligationFinding] = []
    for ob in audit.obligation_ledger:
        status = ob.status.value if hasattr(ob.status, "value") else str(ob.status)
        if status == "satisfied":
            continue
        reason = (ob.notes or "").strip() or (
            "degraded — requirement not fully evidenced" if status == "at_risk" else "requirement unmet"
        )
        out.append(ObligationFinding(id=ob.id, dimension=ob.dimension, status=status,
                                     requirement=ob.requirement, reason=reason))
    return out


def _overclaims(audit) -> list[dict]:
    return [
        {"claim": r.claim, "claim_level": r.claim_level, "permitted_level": r.permitted_level,
         "evidence_grade": r.evidence_grade}
        for r in audit.overclaim_check if not r.ok
    ]


def _calibration_summary(audit, calibration_result: "CalibrationResult") -> dict:
    """The calibration summary, filled from `Audit.calibration.{mae,rank_corr}` via `fill_calibration`
    (the agent leaves them None; the eval — part B — fills them). Read-only: fill returns a copy."""
    from critic_calibration import fill_calibration

    filled = fill_calibration(audit.calibration, calibration_result)
    rank_vals = list((filled.rank_corr or {}).values())
    rank_ordering_sound = bool(rank_vals) and min(rank_vals) >= _RANK_ORDERING_BAR
    return {
        "mae": filled.mae,
        "rank_corr": filled.rank_corr,
        "rank_ordering_sound": rank_ordering_sound,
        "critic_state": LIVE_CRITIC_STATE,
        "note": (
            "rank ordering tracks the blinded judge; the v1 surrogate compresses the top of the 1–9 "
            "range (MAE > 0 at the top) — dev-5, retune ratified-as-analysis + deferred to the "
            "live-judge pass" if not rank_ordering_sound or any(v > 0 for v in (filled.mae or {}).values())
            else "Critic agrees with the blinded judge on level and ordering"
        ),
    }


def _competitiveness_summary(competitiveness: dict, mechanism: str) -> dict:
    """The matched competitiveness for this proposal: its mechanism stratum gap + the pooled gap."""
    strata = competitiveness.get("strata", {})
    stratum = strata.get(mechanism)
    return {
        "mechanism": mechanism,
        "stratum_gap": (stratum or {}).get("gap"),
        "pooled_gap": competitiveness.get("gap"),
        "note": competitiveness.get("method", ""),
    }


def review(proposal, trace, audit, invariant_report, *, calibration_result: "CalibrationResult",
           competitiveness: dict, mechanism: str = "") -> ReviewReport:
    """Assemble the ReviewReport for one (Proposal, Trace, Audit, InvariantReport) + the shared
    EvalReport pieces (part C). REVIEW ONLY — reads the inputs, mutates nothing. go/no-go gates on the
    three HARD invariants (§3); a negative competitiveness gap is surfaced as a CAVEAT, not a NO-GO."""
    inv = {
        "inv-1": invariant_report.by_id("inv-1").passed,
        "inv-2": invariant_report.by_id("inv-2").passed,
        "inv-3": invariant_report.by_id("inv-3").passed,
        "all_passed": invariant_report.all_passed,
    }
    gr = audit.grounding_report
    citation_issues = {
        "all_in_source_set": gr.all_in_source_set,
        "orphan_ids": list(gr.orphan_ids),
        "n_references": gr.n_references,
    }
    unmet = _unmet_obligations(audit)
    overclaims = _overclaims(audit)
    cal = _calibration_summary(audit, calibration_result)
    comp = _competitiveness_summary(competitiveness, mechanism)

    # go/no-go: the three hard invariants are the gate (contract §3 / test-review part C).
    decision = "go" if inv["all_passed"] else "no-go"
    if decision == "go":
        rationale = "all three hard invariants pass (citation integrity, obligation coverage, no overclaim)"
    else:
        failed = [k for k in ("inv-1", "inv-2", "inv-3") if not inv[k]]
        rationale = f"hard invariant(s) failed: {failed}"

    caveats: list[str] = []
    sg = comp["stratum_gap"] or {}
    below = [d for d in ("F1", "F2") if isinstance(sg.get(d), (int, float)) and sg[d] < 0]
    if below:
        caveats.append(
            f"competitiveness: below the matched funded-human bar on {below} (caveat, not a gate; "
            "v1 structural surrogate — see EvalReport.method)"
        )
    if unmet:
        at_risk = [o.id for o in unmet if o.status == "at_risk"]
        if at_risk:
            caveats.append(f"degraded (at_risk, not failing) obligations: {at_risk}")
    if not cal["rank_ordering_sound"] or any(v > 0 for v in (cal["mae"] or {}).values()):
        caveats.append("Critic calibration: v1 surrogate compresses the top of the range (dev-5, deferred)")

    return ReviewReport(
        proposal_title=getattr(proposal, "project_title", "") or "(untitled)",
        revision_round=getattr(proposal, "revision_round", -1),
        invariants=inv,
        unmet_obligations=unmet,
        overclaims=overclaims,
        citation_issues=citation_issues,
        calibration_summary=cal,
        competitiveness_summary=comp,
        decision=decision,
        rationale=rationale,
        caveats=caveats,
    )


def review_all() -> tuple[list[ReviewReport], dict]:
    """Review every fixture's proposal end-to-end (part C) + a build-level go/no-go. Single eval entry
    point: `build_eval_report()` (part B) for the shared calibration + matched competitiveness; the
    agent run for each (Proposal, Trace, Audit); `run_invariants` for the InvariantReport. Offline,
    deterministic, review-only."""
    from cua.nih.run import _build_orchestrator, RUN_CONFIG
    from cua.nih.task import build_task
    from testdata import all_fixtures
    from invariants import run_invariants
    from eval_report import build_eval_report
    from critic_calibration import CalibrationResult

    eval_report = build_eval_report()  # the single Part-B entry point
    cal_result = CalibrationResult.from_dict(eval_report.calibration)
    competitiveness = eval_report.competitiveness

    reports: list[ReviewReport] = []
    for fx in all_fixtures():
        proposal, trace, audit = _build_orchestrator().run(build_task(fx), RUN_CONFIG)
        inv = run_invariants(audit)
        reports.append(review(
            proposal, trace, audit, inv,
            calibration_result=cal_result, competitiveness=competitiveness,
            mechanism=getattr(fx.grant_call, "mechanism", ""),
        ))

    build_decision = "go" if all(r.decision == "go" for r in reports) else "no-go"
    summary = {
        "build_decision": build_decision,
        "n_proposals": len(reports),
        "go": [r.proposal_title for r in reports if r.decision == "go"],
        "no_go": [r.proposal_title for r in reports if r.decision == "no-go"],
        "calibration": eval_report.calibration["mae"] | {"rank_corr": eval_report.calibration["rank_corr"]},
        "competitiveness_pooled_gap": competitiveness.get("gap"),
        "contamination_honored": eval_report.contamination["honored"],
        "critic_state": LIVE_CRITIC_STATE,
    }
    return reports, summary


def main() -> int:
    """`python tests/review.py` — print every proposal's ReviewReport + the build-level go/no-go.
    Offline, deterministic."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for p in (root / "src", root, root / "tests", root / "tests" / "eval"):
        sys.path.insert(0, str(p))

    reports, summary = review_all()
    print("S8 review — ReviewReport per proposal (test-review part C)\n" + "=" * 70)
    for r in reports:
        print(r.to_text())
        print("-" * 70)
    print(f"BUILD DECISION: {summary['build_decision'].upper()}  "
          f"(go={len(summary['go'])}/{summary['n_proposals']})")
    print(f"  calibration: {summary['calibration']}")
    print(f"  competitiveness pooled gap: {summary['competitiveness_pooled_gap']}")
    print(f"  contamination honored: {summary['contamination_honored']}")
    print(f"  critic state: {summary['critic_state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
