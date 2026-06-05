"""selfcheck.py — fixture self-check (operator gate aid) [test-data].

Implements: a runnable verification of the S1 done-criteria that are builder-2's own deliverable —
            `validate()` behavior (test-data §6) and determinism (same seed ⇒ byte-identical
            Fixture, test-data §6). Brief: build/briefs/S1_fixtures.md done-criteria.
Owner: S1 (builder 2).

Scope note: this is NOT the agent's hard-invariant suite (inv-1/2/3, contract §3) — those, and the
assertion of each fixture's `Expectations`, are S3 (builder 3, test-review part A). This module only
exercises the test-data layer it ships, so the operator can confirm the S1 gate with one command:

    python -m testdata.selfcheck     # from the repo root

Exit code 0 ⇒ all S1 self-checks pass; non-zero ⇒ a checked criterion failed.
"""

from __future__ import annotations

import sys

from .scenarios import DEFAULT_SEEDS, SCENARIO_BUILDERS, intentionally_broken
from .types import digest
from .validate import FixtureValidationError, validate, validation_errors


def run() -> list[str]:
    """Return a list of failure messages (empty ⇒ everything passed)."""
    failures: list[str] = []

    # 1. validate() PASSES on all five named scenarios (done-criterion).
    for name, build in SCENARIO_BUILDERS.items():
        fx = build()
        if fx.name != name:
            failures.append(f"[name] builder '{name}' produced fixture named '{fx.name}'")
        try:
            validate(fx)
            print(f"[validate] PASS  {name}")
        except FixtureValidationError as e:
            failures.append(f"[validate] '{name}' should pass but failed:\n{e}")

    # 2. validate() REJECTS the intentionally-broken fixture (proves the gate has teeth).
    broken = intentionally_broken()
    errs = validation_errors(broken)
    if errs:
        print(f"[teeth]    PASS  intentionally_broken rejected ({len(errs)} problem(s); first: {errs[0]})")
    else:
        failures.append("[teeth] intentionally_broken was accepted by validate() — gate has no teeth")

    # 3. Determinism: same seed ⇒ byte-identical Fixture (done-criterion). Also confirm a DIFFERENT
    #    seed changes the fingerprint (seed is load-bearing via the minted resolvable_ids).
    for name, build in SCENARIO_BUILDERS.items():
        seed = DEFAULT_SEEDS[name]
        d1, d2 = digest(build(seed)), digest(build(seed))
        if d1 != d2:
            failures.append(f"[determinism] '{name}' not reproducible at seed {seed}: {d1} != {d2}")
            continue
        d_other = digest(build(seed + 1))
        tag = "seed load-bearing" if d_other != d1 else "WARN seed inert"
        print(f"[determ.]  PASS  {name}  seed={seed} digest={d1[:12]}…  ({tag})")

    return failures


def main() -> int:
    print("S1 fixtures self-check (validate + determinism)\n" + "-" * 46)
    failures = run()
    print("-" * 46)
    if failures:
        print(f"FAIL — {len(failures)} problem(s):")
        for f in failures:
            print(f"  * {f}")
        return 1
    print("OK — all S1 self-checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
