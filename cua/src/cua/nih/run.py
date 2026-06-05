"""run.py — NIH binding: drive the spine on the S1 fixtures, emit the three artifacts.

Implements the run done-criterion: run the Orchestrator on all five fixtures with the real roles and
emit **Proposal · Trace · Audit** to `outputs/` (design §1 observability — three artifacts, never
collapsed). Offline, deterministic, no LLM, no network — every role is a deterministic surrogate (S4
writers + Selection Scorer; S5 Internal Critic + Reviser), so the closed revise loop runs end-to-end.

    python -m cua.nih.run            # from repo root (needs `cua` importable: pip install -e . OR PYTHONPATH=src)

The runner is the only nih module that imports the fixtures (testdata) — the binding types/roles stay
fixture-free. Exit 0 ⇒ all five ran and emitted; non-zero ⇒ a fixture refused or errored.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path

from ..orchestrator import IntakeRefused, Orchestrator
from ..roles import BlueprintPlanner, InternalCritic, Reviser, SelectionScorer
from ..types import RunConfig, Status
from .task import build_task

# Repo root = src/cua/nih/run.py -> parents[3]. Outputs land in <repo>/outputs/.
OUTPUTS_DIR = Path(__file__).resolve().parents[3] / "outputs"

# v1 stopping bar (gap 8). The operator sets the real dimension_thresholds at S6; these exercise the
# score-gate without being the blocker (the reference-integrity gate is what makes a negative revise).
RUN_CONFIG = RunConfig(max_rounds=3, dimension_thresholds={"F1": 5, "F2": 5})


def _json_default(obj):
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"not JSON-serializable: {type(obj).__name__}")


def _dump(obj) -> str:
    data = asdict(obj) if is_dataclass(obj) else obj
    return json.dumps(data, default=_json_default, indent=2, ensure_ascii=False)


def _build_orchestrator() -> Orchestrator:
    """Wire the roles into the engine spine (§1.5 collaborators). All roles are real deterministic
    surrogates now: writers + Selection Scorer (S4), Internal Critic + Reviser (S5) — the revise loop
    is closed."""
    return Orchestrator(
        conditioner=BlueprintPlanner(),
        critic=InternalCritic(),
        reviser=Reviser(),
        selection_scorer=SelectionScorer(),
    )


def run(out_dir: Path = OUTPUTS_DIR) -> int:
    # Imported here so the binding stays import-light for the fixtures (which import framework).
    from testdata import all_fixtures, validate

    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    print("CUA agent — run on S1 fixtures (Proposal · Trace · Audit); closed revise loop (S5)")
    print("-" * 70)
    for fixture in all_fixtures():
        name = fixture.name
        try:
            validate(fixture)  # the test-data gate runs before the agent sees the fixture (test-data §6)
            task = build_task(fixture)
            artifact, trace, audit = _build_orchestrator().run(task, RUN_CONFIG)
        except IntakeRefused as e:
            failures.append(f"{name}: intake refused: {e}")
            print(f"[refuse]  {name}: {e}")
            continue
        except Exception as e:  # surface any wiring error per-fixture, keep going
            failures.append(f"{name}: {type(e).__name__}: {e}")
            print(f"[ERROR]   {name}: {type(e).__name__}: {e}")
            continue

        (out_dir / f"{name}.proposal.json").write_text(_dump(artifact), encoding="utf-8")
        (out_dir / f"{name}.trace.jsonl").write_text(trace.to_jsonl() + "\n", encoding="utf-8")
        (out_dir / f"{name}.audit.json").write_text(_dump(audit), encoding="utf-8")

        gr = audit.grounding_report
        ledger = audit.obligation_ledger
        satisfied = [o for o in ledger if o.status == Status.SATISFIED]
        overclaims = [r.claim for r in audit.overclaim_check if not r.ok]
        inv1 = "PASS" if gr.all_in_source_set else f"FAIL orphans={gr.orphan_ids}"
        inv2 = "PASS" if all(o.evidence_ids for o in satisfied) else "FAIL"
        inv3 = "PASS" if not overclaims else f"flags={overclaims}"
        print(
            f"[ok] {name:16s} r={artifact.revision_round} refs={gr.n_references} aims={len(artifact.aims)} "
            f"sat={len(satisfied)} | inv-1={inv1} inv-2={inv2} inv-3={inv3}"
        )

    print("-" * 70)
    if failures:
        print(f"FAIL — {len(failures)} fixture(s) did not emit:")
        for f in failures:
            print(f"  * {f}")
        return 1
    print(f"OK — emitted Proposal/Trace/Audit for all fixtures to {out_dir}")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
