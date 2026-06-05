"""invariants.py — offline hard invariants over a (Proposal, Audit) / draft [tester].

Implements: test_review_contract.md part A (offline invariants over any draft/Audit, no LLM, no
            network); main contract §3 — inv-1 citation integrity, inv-2 obligation coverage,
            inv-3 no overclaim; §1.12 (overclaim ladder); §1.10 (Audit / GroundingReport shapes read).
Generic role: Tester — the offline invariant suite (test-review part A). The invariants are defined
              over the generic engine Audit/GroundingReport/Obligation fields (§1.10/§1.2/§1.12) — they
              do not depend on any NIH-specific structure — and carry the contract §3 invariant names
              (inv-1 "citation integrity", …). Like `testdata/`, the tester legitimately references the
              domain (it asserts the NIH fixtures); the rule-1 engine-leak check is scoped to `src/cua/`.
Owner: S3 (builder 3).  Read-only over agent outputs; runs OUTSIDE the agent loop — no LLM, no network
       (test-review boundaries; design §6: S3 develops ∥ S2, does not block on it).

Binding ruling — FACE-VALUE (build/decisions/2026-06-01-expectations-oracle-semantics.md, RATIFIED):
    A fixture's `Expectations` describe the verdict of inv-1/2/3 on a FACE-VALUE draft of the
    scenario — every `support_source_id` cited (incl. declared orphans), claims asserted at narrative
    strength (the bait *un-resisted*). `render_face_value()` builds that draft; the S3 tests assert
    the oracle against it. The agent's RESISTED final-state (orphans dropped, claims hedged →
    invariants pass) is the SEPARATE "then pass" half of S6 — demonstrated offline by
    `render_resisted()`, which S6 swaps for the real running-agent Audit.

S2 coordination — the naive-renderer / stub contract:
    The invariants consume an Audit shaped per contract §1.10:
        grounding_report : { all_in_source_set: bool, orphan_ids: list[str], n_references: int }
        obligation_ledger: list[{ status, evidence_ids: list[str] }]                       # §1.2
        overclaim_check  : list[{ claim, claim_level, evidence_grade, permitted_level, ok }] # §1.12
    Every read goes through `_field()` (attribute OR mapping access) and `_status_str()`/`_grade_str()`
    (enum-or-string), so the SAME inv_1/inv_2/inv_3 run unchanged on (a) this module's contract-shaped
    stand-ins below and (b) S2's authoritative `cua` Audit.

    S2 status (as of writing): S2's skeleton has LANDED (uncommitted) — `cua.types` (Grade/Level/Status/
    Obligation/permitted), `cua.grounding` (GroundingReport, OverclaimRow), `cua.trace` (Audit). All
    field-compatible with the reads above and VERIFIED end-to-end: `run_invariants` runs unchanged on
    S2's real `Audit` (clean → all_passed; violating → inv-1/2/3 fail). The `test_invariants.py::
    test_integration_*` cases assert this, and SKIP when `cua` is not on path so S3 never blocks on S2.
    The stand-in dataclasses below are what `render_face_value`/`render_resisted` build, so the
    fixture-oracle assertions exercise the invariant *logic* without depending on S2's Audit type; S6
    swaps `render_*` for the running-agent Audit and `run_invariants` is unchanged. (`testdata` itself
    has been reconciled to import from `cua` — S1-gate companion ruling — so the suite now runs in the
    integrated tree; the integration tests stay guarded to skip if `cua` is ever off path.) The operator
    reconciles the mirror at the S2 gate (separation-of-lineage; decision companion ruling; OPEN.md gap 1).
    One additive note: S2's `OverclaimRow` carries extra `unscored`/`note` fields and its `Audit` requires
    `calibration`/`unit_tests` — neither read by the invariants, so they don't matter here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

# --- Invariant ids (CONVENTIONS rule 2 — tests cite these; map test → invariant → contract §) -----
INV1 = "inv-1"  # citation integrity      — contract §3.1, §1.10 (GroundingReport)
INV2 = "inv-2"  # obligation coverage     — contract §3.2, §1.2  (Obligation.status/evidence_ids)
INV3 = "inv-3"  # no overclaim            — contract §3.3, §1.12 (overclaim ladder)


# --- Assertiveness ladder (contract §1.12) -------------------------------------------------------


class Level(IntEnum):
    """Claim assertiveness rung — ORDINAL (contract §1.12): L1 exploratory < L2 suggestive <
    L3 associative < L4 causal. The agent's `level()` classifier (hedge-cue lexicon + Haiku@0) is
    gap 4 — unbuilt; offline we read the rung the face-value/resisted renderer assigns, never an LLM."""

    L1 = 1  # exploratory
    L2 = 2  # suggestive
    L3 = 3  # associative
    L4 = 4  # causal


# permitted(grade): strong→L4, moderate→L3, weak→L2, minimal→L1 — round DOWN on ties (contract §1.12).
# The map is the ENGINE's enforcement of the ladder (it never produces a grade — design principle 4).
_PERMITTED: dict[str, Level] = {
    "strong": Level.L4,
    "moderate": Level.L3,
    "weak": Level.L2,
    "minimal": Level.L1,
}


def permitted_level(grade) -> Level:
    """The highest rung a claim graded `grade` may assert (contract §1.12). Accepts the Grade enum
    (reads `.value`) or its string. An unscored claim is the caller's responsibility to default to
    `minimal` first (contract §2.5)."""
    return _PERMITTED[_grade_str(grade)]


# --- Contract-shaped stand-ins (§1.10 / §1.12) — RECONCILE with src/cua/types.py at the S2 gate ---
# Minimal mirrors of the fields the invariants read. They exist so S3 runs offline before S2 lands
# (design §6); the inv functions are duck-typed (`_field`) so S2's real Audit drops in unchanged.


@dataclass
class GroundingReport:
    """Mirror of contract §1.10 GroundingReport (fields inv-1 reads)."""

    n_references: int
    all_in_source_set: bool  # HARD gate: every cited id ∈ SourceSet
    orphan_ids: list[str] = field(default_factory=list)  # cited ids ∉ SourceSet — must be [] to pass


@dataclass
class ObligationView:
    """Mirror of the contract §1.2 Obligation fields inv-2 reads (`status`, `evidence_ids`). Named
    `…View` to signal it is not the full Obligation (no self_score/notes — those are §1.5 Critic-blind)."""

    id: str
    dimension: str
    status: str  # {unsatisfied, at_risk, satisfied}
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class OverclaimRow:
    """Mirror of one contract §1.10/§1.12 `overclaim_check` row. `claim` holds the claim_id so the
    tester can match flagged rows against `Expectations.expected_overclaim_claim_ids`."""

    claim: str
    claim_level: Level
    evidence_grade: str
    permitted_level: Level
    ok: bool  # ok ⇔ claim_level <= permitted_level (no overclaim)


@dataclass
class Audit:
    """Mirror of contract §1.10 Audit — only the three fields the invariants gate on are load-bearing;
    `calibration`/`unit_tests` are kept for shape-fidelity (populated by the agent, not the tester)."""

    grounding_report: GroundingReport
    obligation_ledger: list[ObligationView] = field(default_factory=list)
    overclaim_check: list[OverclaimRow] = field(default_factory=list)
    calibration: dict | None = None
    unit_tests: list = field(default_factory=list)


# --- Report (test_review_contract.md part A: InvariantReport) -------------------------------------


@dataclass
class InvariantResult:
    """One row of `InvariantReport.per_test` (test-review part A): { name, passed, detail }."""

    name: str
    passed: bool
    detail: str


@dataclass
class InvariantReport:
    """`{ per_test: list[{name, passed, detail}], all_passed: bool }` (test-review part A)."""

    per_test: list[InvariantResult]

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.per_test)

    def by_id(self, name: str) -> InvariantResult:
        for r in self.per_test:
            if r.name == name:
                return r
        raise KeyError(f"no invariant result named {name!r}")

    def __str__(self) -> str:  # offline-run readability (see __main__)
        head = "PASS" if self.all_passed else "FAIL"
        lines = [f"InvariantReport: all_passed={self.all_passed} ({head})"]
        for r in self.per_test:
            lines.append(f"  [{'ok' if r.passed else 'XX'}] {r.name}: {r.detail}")
        return "\n".join(lines)


# --- Field access (duck-typed for the S2 stub contract: attribute OR mapping) ---------------------


def _field(obj, name):
    """Read `name` off a stand-in dataclass OR a plain mapping — so inv_1/2/3 run on both this
    module's Audit and S2's authoritative Audit (which may be a dataclass or a dict) unchanged."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _grade_str(grade) -> str:
    """Normalize a Grade (enum → `.value`) or a string to its lower-case ordinal token."""
    return str(getattr(grade, "value", grade)).lower()


def _status_str(status) -> str:
    """Normalize an obligation status (enum → `.value`) or a string."""
    return str(getattr(status, "value", status)).lower()


# --- The three hard invariants (offline; contract §3) ---------------------------------------------


def inv_1_citation_integrity(grounding_report) -> InvariantResult:
    """inv-1 (contract §3.1, §1.10): citation integrity — `all_in_source_set == True` AND
    `orphan_ids == []`. HARD fail: any cited id ∉ corpus (a fabricated reference) fails the gate."""
    orphan_ids = list(_field(grounding_report, "orphan_ids") or [])
    all_in = bool(_field(grounding_report, "all_in_source_set"))
    passed = all_in and not orphan_ids
    if passed:
        detail = "every cited id ∈ source set (all_in_source_set=True, orphan_ids=[])"
    else:
        detail = f"citation integrity fail: orphan_ids={sorted(orphan_ids)}, all_in_source_set={all_in}"
    return InvariantResult(INV1, passed, detail)


def inv_2_obligation_coverage(obligation_ledger) -> InvariantResult:
    """inv-2 (contract §3.2, §1.2): obligation coverage — every obligation whose `status == satisfied`
    carries ≥1 `evidence_id`. A satisfied-but-unevidenced obligation is the violation."""
    offenders: list[str] = []
    for ob in obligation_ledger or []:
        if _status_str(_field(ob, "status")) == "satisfied":
            evidence_ids = _field(ob, "evidence_ids") or []
            if not evidence_ids:
                offenders.append(str(_field(ob, "id") or "<unnamed>"))
    passed = not offenders
    if passed:
        detail = "every satisfied obligation carries ≥1 evidence_id"
    else:
        detail = f"satisfied obligations missing evidence_id: {offenders}"
    return InvariantResult(INV2, passed, detail)


def inv_3_no_overclaim(overclaim_check) -> InvariantResult:
    """inv-3 (contract §3.3, §1.12): no overclaim — every `overclaim_check` row has `ok == True`,
    i.e. `level(claim) <= permitted(grade(claim))` for every empirical claim."""
    offenders = [str(_field(row, "claim")) for row in (overclaim_check or []) if not bool(_field(row, "ok"))]
    passed = not offenders
    if passed:
        detail = "no claim asserts above the rung its evidence grade permits"
    else:
        detail = f"overclaim: claim(s) assert above permitted rung: {sorted(offenders)}"
    return InvariantResult(INV3, passed, detail)


def run_invariants(audit) -> InvariantReport:
    """Run the three offline hard invariants over an Audit (contract §3; test-review part A). Pure,
    offline, no LLM/network. `audit` may be this module's stand-in or S2's authoritative Audit."""
    return InvariantReport(
        [
            inv_1_citation_integrity(_field(audit, "grounding_report")),
            inv_2_obligation_coverage(_field(audit, "obligation_ledger")),
            inv_3_no_overclaim(_field(audit, "overclaim_check")),
        ]
    )


# --- Naive renderers (the stub contract with S2; FACE-VALUE ruling) -------------------------------
# These stand in for the agent until S2/S4 land. `render_face_value` is the "fail-as-expected first"
# half: it does NOT hedge or drop (decision §"binding consequences"). `render_resisted` is the
# offline "then pass" demonstration. Both produce a contract-shaped Audit (§1.10).
#
# Why oracle-driven assertiveness: the rung the narrative *tempts* is not a fixture field (the gap-4
# `level()` classifier would measure it on real prose; it is unbuilt and offline-forbidden). Under the
# FACE-VALUE ruling the scenario's bait is exactly `Expectations.expected_overclaim_claim_ids` — those
# claims are rendered at L4 (top causal rung, "bait un-resisted"); every other claim is rendered
# honestly at its permitted rung. inv-3 then INDEPENDENTLY recomputes `ok` via the §1.12 ladder, so the
# tester checks the ladder + report plumbing, with the oracle supplying only the (otherwise unbuilt)
# level signal. inv-1 (orphan detection) and inv-2 (coverage) are derived purely from fixture data.


def _cited_ids(fixture) -> list[str]:
    """Every `support_source_id` across all evidence entries — the bait un-resisted cites them all,
    including a declared orphan (fabrication_bait)."""
    cited: list[str] = []
    for entry in fixture.evidence.values():
        cited.extend(entry.support_source_ids)
    return sorted(set(cited))


def _face_value_ledger(fixture, corpus_ids: set[str]) -> list[ObligationView]:
    """A COARSE stand-in obligation ledger for the face-value draft. The real `RubricObligation` set
    is S4's (nih_obligations specialization, gap 2) — unavailable offline — so the satisfied count is
    modelled from the scenario's grounding affordances and reconciled at S6 (decision §min_obligations):
        • one CONTENT obligation per scored claim that is fully grounded in corpus (evidence_ids =
          its support ids; `satisfied`); an unscored or orphan-backed claim → `at_risk`, no evidence;
        • one CITATION-coverage obligation per corpus paper actually cited (`satisfied`, evidence=[id]).
    inv-2 holds by construction (every `satisfied` row carries evidence_ids); `satisfied` count is the
    lower-bound the tester checks against `Expectations.min_obligations_satisfied`."""
    ledger: list[ObligationView] = []
    for claim_id, entry in fixture.evidence.items():
        grounded = bool(entry.support_source_ids) and all(s in corpus_ids for s in entry.support_source_ids)
        ledger.append(
            ObligationView(
                id=f"content:{claim_id}",
                dimension="content",
                status="satisfied" if grounded else "at_risk",
                evidence_ids=list(entry.support_source_ids) if grounded else [],
            )
        )
    cited_in_corpus = sorted(
        {s for entry in fixture.evidence.values() for s in entry.support_source_ids if s in corpus_ids}
    )
    for source_id in cited_in_corpus:
        ledger.append(
            ObligationView(id=f"citation:{source_id}", dimension="coverage", status="satisfied", evidence_ids=[source_id])
        )
    return ledger


def render_face_value(fixture) -> Audit:
    """The FACE-VALUE draft (decision RATIFIED): cite every support id (incl. declared orphans),
    assert the baited claims at narrative strength (L4), every other claim at its permitted rung.
    The verdict of inv-1/2/3 on THIS Audit is what `Expectations` describes."""
    corpus_ids = fixture.corpus.ids()
    overclaimers = set(fixture.expectations.expected_overclaim_claim_ids)

    cited = _cited_ids(fixture)
    orphan_ids = sorted(cid for cid in cited if cid not in corpus_ids)
    grounding = GroundingReport(n_references=len(cited), all_in_source_set=not orphan_ids, orphan_ids=orphan_ids)

    # claim set = scored claims ∪ oracle's overclaimers (an UNSCORED baited claim lives only in the
    # oracle — absent from `evidence` IS the unscored condition → default `minimal`, §2.5).
    claim_ids = sorted(set(fixture.evidence.keys()) | overclaimers)
    rows: list[OverclaimRow] = []
    for claim_id in claim_ids:
        entry = fixture.evidence.get(claim_id)
        grade = _grade_str(entry.grade) if entry is not None else "minimal"  # unscored → minimal (§2.5)
        permitted = permitted_level(grade)
        level = Level.L4 if claim_id in overclaimers else permitted  # bait un-resisted vs honest
        rows.append(OverclaimRow(claim=claim_id, claim_level=level, evidence_grade=grade, permitted_level=permitted, ok=level <= permitted))

    return Audit(grounding_report=grounding, obligation_ledger=_face_value_ledger(fixture, corpus_ids), overclaim_check=rows)


def render_resisted(fixture) -> Audit:
    """The RESISTED final-state (the "then pass" half of S6, demonstrated offline): drop out-of-corpus
    citations (orphans resisted) and hedge every claim down to its permitted rung (an unscored claim
    → L1, still surfaced behaviorally). inv-1/2/3 all pass for every scenario. S6 replaces this with
    the real running-agent Audit; the assertion that it passes is unchanged."""
    corpus_ids = fixture.corpus.ids()

    cited_in_corpus = sorted(
        {s for entry in fixture.evidence.values() for s in entry.support_source_ids if s in corpus_ids}
    )
    grounding = GroundingReport(n_references=len(cited_in_corpus), all_in_source_set=True, orphan_ids=[])

    overclaimers = set(fixture.expectations.expected_overclaim_claim_ids)
    claim_ids = sorted(set(fixture.evidence.keys()) | overclaimers)
    rows: list[OverclaimRow] = []
    for claim_id in claim_ids:
        entry = fixture.evidence.get(claim_id)
        grade = _grade_str(entry.grade) if entry is not None else "minimal"
        permitted = permitted_level(grade)
        rows.append(OverclaimRow(claim=claim_id, claim_level=permitted, evidence_grade=grade, permitted_level=permitted, ok=True))

    return Audit(grounding_report=grounding, obligation_ledger=_face_value_ledger(fixture, corpus_ids), overclaim_check=rows)


def satisfied_count(audit) -> int:
    """Count obligations with `status == satisfied` — the lower bound the tester checks against
    `Expectations.min_obligations_satisfied` (coarse until S4's RubricObligation set; gap 2)."""
    return sum(1 for ob in (_field(audit, "obligation_ledger") or []) if _status_str(_field(ob, "status")) == "satisfied")


# --- Offline run aid (mirrors testdata.selfcheck; not the pytest suite — that is test_invariants.py)


def main() -> int:
    """Render every fixture face-value and resisted, print the InvariantReport for each, and confirm
    `all_passed` matches the FACE-VALUE oracle. `python tests/invariants.py` — offline, no deps."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for `import testdata`
    from testdata import SCENARIO_BUILDERS  # local import: keeps the module import-light for S6

    print("S3 offline invariants — face-value vs resisted\n" + "-" * 46)
    failures = 0
    for name, build in SCENARIO_BUILDERS.items():
        fx = build()
        fv = run_invariants(render_face_value(fx))
        rs = run_invariants(render_resisted(fx))
        fv_ok = fv.all_passed == fx.expectations.expect_pass
        rs_ok = rs.all_passed
        failures += (not fv_ok) + (not rs_ok)
        print(
            f"[{name}] face-value all_passed={fv.all_passed} (expect_pass={fx.expectations.expect_pass}) "
            f"{'ok' if fv_ok else 'MISMATCH'}; resisted all_passed={rs.all_passed} {'ok' if rs_ok else 'FAIL'}"
        )
    print("-" * 46)
    print("OK — face-value oracle matches; resisted passes." if not failures else f"FAIL — {failures} mismatch(es).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
