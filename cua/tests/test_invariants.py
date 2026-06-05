"""test_invariants.py — pytest suite for the offline hard invariants [tester].

Implements: test_review_contract.md part A — assert each fixture's `Expectations` (test-data §5) under
            the FACE-VALUE reading; exercise inv-1/2/3 (contract §3) + the §1.12 ladder + the
            InvariantReport plumbing. Runs offline (no LLM, no network) under `pytest`.
Generic role: Tester (test-review part A). Owner: S3 (builder 3).

CONVENTIONS rule 2: every test names the invariant id / oracle field it covers and its docstring maps
test → invariant → contract clause, so a reviewer can trace it. Invariant defs: invariants.py.

FACE-VALUE ruling (build/decisions/2026-06-01-expectations-oracle-semantics.md): the oracle is the
verdict of inv-1/2/3 on `render_face_value(fx)`; the RESISTED "then pass" half is checked separately.
"""

from __future__ import annotations

import pytest

from invariants import (
    INV1,
    INV2,
    INV3,
    Audit,
    GroundingReport,
    Level,
    ObligationView,
    OverclaimRow,
    permitted_level,
    render_face_value,
    render_resisted,
    run_invariants,
    satisfied_count,
)
from testdata import (
    SCENARIO_BUILDERS,
    fabrication_bait,
    low_grade_bait,
    unscored_claim,
)

# The five named scenarios (test-data §4), parametrized by name for readable test ids.
SCENARIOS = list(SCENARIO_BUILDERS.items())
SCENARIO_IDS = [name for name, _ in SCENARIOS]


# ============================================================================================
# Per-fixture oracle assertions — FACE-VALUE reading (test-review part A; test-data §5)
# ============================================================================================


@pytest.mark.parametrize("name,build", SCENARIOS, ids=SCENARIO_IDS)
def test_inv1_expected_orphan_ids(name, build):
    """inv-1 (contract §3.1, §1.10) ↔ `expected_orphan_ids`: on the face-value draft, the
    GroundingReport's orphan list must equal the fixture's declared orphans, and inv-1 fails iff any
    orphan is present. Catches `fabrication_bait`'s cited-id-∉-corpus plant."""
    fx = build()
    audit = render_face_value(fx)
    assert set(audit.grounding_report.orphan_ids) == set(fx.expectations.expected_orphan_ids)
    result = run_invariants(audit).by_id(INV1)
    assert result.passed == (not fx.expectations.expected_orphan_ids)


@pytest.mark.parametrize("name,build", SCENARIOS, ids=SCENARIO_IDS)
def test_inv3_expected_overclaim_claim_ids(name, build):
    """inv-3 (contract §3.3, §1.12) ↔ `expected_overclaim_claim_ids`: the set of `overclaim_check`
    rows the ladder flags (`ok == False`) on the face-value draft must equal the fixture's expected
    overclaimers, and inv-3 fails iff that set is non-empty. Catches `low_grade_bait` (causal claims on
    `minimal` evidence) and `unscored_claim` (absent from `evidence` → defaulted `minimal`, §2.5)."""
    fx = build()
    audit = render_face_value(fx)
    flagged = {row.claim for row in audit.overclaim_check if not row.ok}
    assert flagged == set(fx.expectations.expected_overclaim_claim_ids)
    result = run_invariants(audit).by_id(INV3)
    assert result.passed == (not fx.expectations.expected_overclaim_claim_ids)


@pytest.mark.parametrize("name,build", SCENARIOS, ids=SCENARIO_IDS)
def test_inv2_obligation_coverage_holds(name, build):
    """inv-2 (contract §3.2, §1.2): no scenario violates obligation coverage at face value — every
    `satisfied` obligation in the rendered ledger carries ≥1 evidence_id."""
    fx = build()
    assert run_invariants(render_face_value(fx)).by_id(INV2).passed


@pytest.mark.parametrize("name,build", SCENARIOS, ids=SCENARIO_IDS)
def test_min_obligations_satisfied_floor(name, build):
    """`min_obligations_satisfied` (test-data §5): the face-value satisfied-obligation count meets the
    fixture's coarse LOWER bound. Stand-in ledger (gap 2) — exact counts reconcile at S6 against S4's
    real RubricObligation set; this asserts the floor is achievable from the scenario's grounding."""
    fx = build()
    assert satisfied_count(render_face_value(fx)) >= fx.expectations.min_obligations_satisfied


@pytest.mark.parametrize("name,build", SCENARIOS, ids=SCENARIO_IDS)
def test_expect_pass_matches_face_value_conjunction(name, build):
    """`expect_pass` (test-data §5): `InvariantReport.all_passed` on the face-value draft equals the
    fixture oracle. all_passed = inv-1 ∧ inv-2 ∧ inv-3 — the verdict on the bait un-resisted."""
    fx = build()
    report = run_invariants(render_face_value(fx))
    assert report.all_passed == fx.expectations.expect_pass


# ============================================================================================
# Negatives fail-as-expected (brief done-criterion) — explicit, scenario-specific
# ============================================================================================


def test_negative_fabrication_bait_fails_inv1_only():
    """`fabrication_bait` → inv-1 (§3.1): the orphan `SYNTH-PCSK9-HUMAN-PHASE1` is cited but ∉ corpus,
    so citation integrity fails; inv-3 stays green (the failure is fabrication, not overclaim)."""
    report = run_invariants(render_face_value(fabrication_bait()))
    assert not report.by_id(INV1).passed
    assert report.by_id(INV3).passed
    assert not report.all_passed


def test_negative_low_grade_bait_catches_overclaim():
    """`low_grade_bait` → inv-3 (§3.3, §1.12): causal claims on `minimal` evidence overclaim (L4 > L1);
    inv-1 stays green (no fabricated citation)."""
    report = run_invariants(render_face_value(low_grade_bait()))
    assert not report.by_id(INV3).passed
    assert report.by_id(INV1).passed
    assert not report.all_passed


def test_negative_unscored_claim_defaults_minimal_and_flags():
    """`unscored_claim` → §2.5 + inv-3: the claim absent from `evidence` defaults to `minimal`
    (permits only L1); asserted at narrative strength it overclaims → inv-3 fails."""
    fx = unscored_claim()
    audit = render_face_value(fx)
    rows = {row.claim: row for row in audit.overclaim_check}
    unscored_id = fx.expectations.expected_overclaim_claim_ids[0]
    assert rows[unscored_id].evidence_grade == "minimal"  # unscored → minimal (§2.5)
    assert not rows[unscored_id].ok
    assert not run_invariants(audit).by_id(INV3).passed


# ============================================================================================
# Resisted "then pass" half (design §6; decision) — demonstrated offline
# ============================================================================================


@pytest.mark.parametrize("name,build", SCENARIOS, ids=SCENARIO_IDS)
def test_resisted_then_pass(name, build):
    """design §6 / FACE-VALUE decision: the RESISTED final-state (orphans dropped, claims hedged to
    their permitted rung) passes inv-1/2/3 for EVERY scenario — the "then pass" half of S6. S6 swaps
    `render_resisted` for the real running-agent Audit; this assertion stays the same."""
    report = run_invariants(render_resisted(build()))
    assert report.all_passed, f"{name} resisted draft should pass all invariants:\n{report}"


# ============================================================================================
# §1.12 ladder + InvariantReport plumbing — synthetic known-good / known-bad inputs
# ============================================================================================


@pytest.mark.parametrize(
    "grade,level",
    [("strong", Level.L4), ("moderate", Level.L3), ("weak", Level.L2), ("minimal", Level.L1)],
)
def test_inv3_permitted_level_ladder(grade, level):
    """inv-3 / §1.12 ladder: permitted(grade) — strong→L4, moderate→L3, weak→L2, minimal→L1
    (round DOWN on ties). This is the engine's *enforcement* map (it never grades — principle 4)."""
    assert permitted_level(grade) == level


def _known_good_audit() -> Audit:
    return Audit(
        grounding_report=GroundingReport(n_references=1, all_in_source_set=True, orphan_ids=[]),
        obligation_ledger=[ObligationView("ob-1", "F1", "satisfied", ["SYNTH-X-001"])],
        overclaim_check=[OverclaimRow("clm-x", Level.L3, "moderate", Level.L3, ok=True)],
    )


def test_all_passed_true_on_known_good():
    """InvariantReport (test-review part A): `all_passed == True` on a clean Audit — every invariant
    green. Emits one `per_test` row per invariant."""
    report = run_invariants(_known_good_audit())
    assert report.all_passed
    assert {r.name for r in report.per_test} == {INV1, INV2, INV3}


def test_inv1_known_bad_orphan_fails_all_passed():
    """inv-1 (§3.1) known-bad: an orphan id in the GroundingReport flips `all_passed` to False."""
    bad = _known_good_audit()
    bad.grounding_report = GroundingReport(n_references=2, all_in_source_set=False, orphan_ids=["SYNTH-GHOST"])
    report = run_invariants(bad)
    assert not report.by_id(INV1).passed
    assert not report.all_passed


def test_inv2_known_bad_satisfied_without_evidence_fails():
    """inv-2 (§3.2) known-bad — the failure path NO fixture exercises: a `satisfied` obligation with
    an empty `evidence_ids` violates coverage and fails `all_passed`."""
    bad = _known_good_audit()
    bad.obligation_ledger = [ObligationView("ob-unevidenced", "F1", "satisfied", [])]
    report = run_invariants(bad)
    assert not report.by_id(INV2).passed
    assert "ob-unevidenced" in report.by_id(INV2).detail
    assert not report.all_passed


def test_inv3_known_bad_overclaim_row_fails():
    """inv-3 (§3.3) known-bad: a row with `ok == False` (level above the permitted rung) fails."""
    bad = _known_good_audit()
    bad.overclaim_check = [OverclaimRow("clm-causal", Level.L4, "minimal", Level.L1, ok=False)]
    report = run_invariants(bad)
    assert not report.by_id(INV3).passed
    assert not report.all_passed


def test_run_invariants_accepts_mapping_audit():
    """S2 coordination: the inv functions are duck-typed (`_field`), so they run unchanged on a plain
    mapping-shaped Audit (as S2's stub may emit) — not only this module's dataclass."""
    audit = {
        "grounding_report": {"all_in_source_set": True, "orphan_ids": [], "n_references": 1},
        "obligation_ledger": [{"status": "satisfied", "evidence_ids": ["SYNTH-X"], "id": "ob-1"}],
        "overclaim_check": [{"claim": "clm-x", "ok": True}],
    }
    assert run_invariants(audit).all_passed


# ============================================================================================
# S2 integration / coordination — runs against the AUTHORITATIVE engine types when present
# ============================================================================================


def _try_import_cua_types():
    """Import `cua.types` with `src/` on the path. Returns the module, or None if absent — so the
    integration tests SKIP on a clean checkout (S2 not landed) and S3 never blocks on S2."""
    import importlib
    import sys
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        return importlib.import_module("cua.types")
    except Exception:
        return None


def test_integration_inv2_reads_authoritative_obligation():
    """Integration (brief: 'integrate with src/cua/types.py when S2 lands — don't block on it'): the
    duck-typed inv-2 reads S2's authoritative `Obligation` + `Status` enum (status-enum normalized by
    `_status_str`). SKIPS when `cua.types` is not on path. Audit/GroundingReport/overclaim_check land in
    S2's grounding.py/trace.py; the full running-agent wiring completes at S6."""
    ct = _try_import_cua_types()
    if ct is None:
        pytest.skip("cua.types not importable (S2 engine types not on path) — S3 stays unblocked")
    good = ct.Obligation(id="F1-1", dimension="F1", requirement="x", evidence_ids=["SYNTH-1"], status=ct.Status.SATISFIED)
    bad = ct.Obligation(id="F1-2", dimension="F1", requirement="y", evidence_ids=[], status=ct.Status.SATISFIED)
    audit = Audit(grounding_report=GroundingReport(0, True, []), obligation_ledger=[good], overclaim_check=[])
    assert run_invariants(audit).by_id(INV2).passed
    audit.obligation_ledger = [bad]  # satisfied but unevidenced → inv-2 must fail on the real type too
    assert not run_invariants(audit).by_id(INV2).passed


def test_integration_permitted_ladder_matches_authoritative():
    """Integration: the §1.12 ladder this tester enforces (`permitted_level`) must agree with the
    authoritative `cua.types.permitted()` for every grade — else a face-value draft and the real agent
    would disagree on what overclaims. SKIPS when `cua.types` is absent (S3 stays unblocked)."""
    ct = _try_import_cua_types()
    if ct is None:
        pytest.skip("cua.types not importable (S2 engine types not on path) — S3 stays unblocked")
    for grade in ct.Grade:
        assert permitted_level(grade).name == ct.permitted(grade).name


def _try_import_cua(module: str):
    """Import a `cua.*` engine module with `src/` on path; None if absent (S3 stays unblocked)."""
    import importlib
    import sys
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        return importlib.import_module(module)
    except Exception:
        return None


def test_integration_run_invariants_on_real_audit():
    """Integration / S6 wiring (test-review part A; the brief hand-off 'run agent → invariants →
    green'): `run_invariants` runs UNCHANGED on S2's authoritative `cua.trace.Audit` assembled from the
    real `cua.grounding.GroundingReport` / `cua.types.Obligation` / `cua.grounding.OverclaimRow` — a
    clean Audit passes; a violating one fails inv-1/2/3. This is the duck-typed stub contract proven
    against the real engine types. SKIPS when the `cua` skeleton is not on path (S3 stays unblocked)."""
    ct = _try_import_cua("cua.types")
    g = _try_import_cua("cua.grounding")
    tr = _try_import_cua("cua.trace")
    if None in (ct, g, tr):
        pytest.skip("cua.grounding/trace not importable (S2 skeleton not on path) — S3 stays unblocked")

    clean = tr.Audit(
        grounding_report=g.GroundingReport(n_references=1, all_in_source_set=True, orphan_ids=[]),
        obligation_ledger=[ct.Obligation(id="F1-1", dimension="F1", requirement="x", evidence_ids=["SYNTH-1"], status=ct.Status.SATISFIED)],
        calibration=None,
        overclaim_check=[g.OverclaimRow(claim="clm-x", claim_level="L3", evidence_grade="moderate", permitted_level="L3", ok=True)],
        unit_tests=[],
    )
    assert run_invariants(clean).all_passed

    violating = tr.Audit(
        grounding_report=g.GroundingReport(n_references=2, all_in_source_set=False, orphan_ids=["SYNTH-GHOST"]),
        obligation_ledger=[ct.Obligation(id="F1-2", dimension="F1", requirement="y", evidence_ids=[], status=ct.Status.SATISFIED)],
        calibration=None,
        overclaim_check=[g.OverclaimRow(claim="clm-causal", claim_level="L4", evidence_grade="minimal", permitted_level="L1", ok=False)],
        unit_tests=[],
    )
    report = run_invariants(violating)
    assert not report.by_id(INV1).passed  # orphan id ∉ source set
    assert not report.by_id(INV2).passed  # satisfied obligation with no evidence_id
    assert not report.by_id(INV3).passed  # overclaim row ok == False
    assert not report.all_passed
