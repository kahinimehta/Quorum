"""reporter_reference.py — the RePORTER comparison reference set + contamination guard [tester].

Implements: test_review_contract.md part B1 (same-domain funded abstracts / Specific Aims from NIH
            RePORTER as the comparison corpus) + B4 matching + Boundaries (contamination rule);
            design §5 (few-shot disjointness). Decision: build/decisions/2026-06-02-eval-methodology.md §A.
Generic role: eval-only reference data — the *high-end* competitiveness bar (funded human work). NOT a
              pipeline role; read-only, outside the agent loop. NIH binding: RePORTER funded projects.
Owner: S7 (builder 3).

Contamination rule (HARD — test-review Boundaries; the load-bearing guard of this whole eval): RePORTER
text is used for scoring ONLY and is NEVER inserted into any agent input; the writer few-shot exemplars
stay DISJOINT from this set and abstracted to structure. v1 ships a small STORED set abstracted to
structure (RePORTER-shaped records, NO funded-grant verbatim text) so nothing can leak and determinism
holds; the live `api.reporter.nih.gov` sampler is specified + network-gated (NOT called offline),
mirroring the decision-A resolve path (OPEN.md). `assert_contamination_free` proves the rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReferenceItem:
    """One funded human comparison item (RePORTER-shaped; decision §A). `domain_terms` is the MATCHING
    key (B4 — it MAY overlap a fixture's disease vocabulary; that is the comparison axis, not leakage).
    `app_id` + `structural_note` are the *identifying content* that must NEVER reach an agent input
    (the note is the abstracted stand-in for funded prose — a skeleton, not verbatim text)."""

    app_id: str  # RePORTER-style application id (synthetic in v1; the real pull carries the live id)
    activity_code: str  # mechanism — R01 | R21 (B4 match key)
    domain_terms: tuple[str, ...]  # disease/topic terms (RCDC-style); the domain match key
    fiscal_year: int
    n_aims: int  # structural count (Specific Aims)
    has_central_hypothesis: bool
    est_references: int  # structural count (citation deck size)
    structural_note: str  # ABSTRACTED skeleton (move-structure), never funded-grant prose


# === v1 stored reference set (abstracted to structure; matched to the S1 fixtures' mechanisms/domains)
# Funded human bar. Each note is an explicit "[abstracted structure: ...]" skeleton — NO verbatim
# funded text — so the contamination rule holds by construction. Domains chosen to give ≥1 matched
# human item per (mechanism, domain) the fixtures exercise (GI/immunology, neuro, cardiometabolic).
REFERENCE_SET: list[ReferenceItem] = [
    ReferenceItem(
        app_id="RPT-R01-GI-0001", activity_code="R01",
        domain_terms=("ulcerative colitis", "gut microbiome", "mucosal immunology"),
        fiscal_year=2024, n_aims=3, has_central_hypothesis=True, est_references=42,
        structural_note="[abstracted structure: gap → mechanistic central hypothesis → 3 aims (target validation, intervention, biomarker) with pitfalls]",
    ),
    ReferenceItem(
        app_id="RPT-R21-IMM-0002", activity_code="R21",
        domain_terms=("rheumatoid arthritis", "neuroimmune", "inflammation"),
        fiscal_year=2023, n_aims=2, has_central_hypothesis=True, est_references=24,
        structural_note="[abstracted structure: exploratory gap → 2 aims (proof-of-concept, feasibility) — R21 scope]",
    ),
    ReferenceItem(
        app_id="RPT-R01-NEU-0003", activity_code="R01",
        domain_terms=("alzheimer's disease", "cognitive decline", "neurodegeneration"),
        fiscal_year=2025, n_aims=3, has_central_hypothesis=True, est_references=51,
        structural_note="[abstracted structure: gap → hypothesis → 3 aims (mechanism, longitudinal cohort, intervention) with alternatives]",
    ),
    ReferenceItem(
        app_id="RPT-R01-CMD-0004", activity_code="R01",
        domain_terms=("familial hypercholesterolemia", "gene editing", "cardiometabolic"),
        fiscal_year=2024, n_aims=3, has_central_hypothesis=True, est_references=47,
        structural_note="[abstracted structure: gap → hypothesis → 3 aims (in vivo editing, durability, safety) with rigor/feasibility plan]",
    ),
    ReferenceItem(
        app_id="RPT-R01-CMD-0005", activity_code="R01",
        domain_terms=("metabolic syndrome", "time-restricted eating", "cardiometabolic"),
        fiscal_year=2023, n_aims=3, has_central_hypothesis=True, est_references=39,
        structural_note="[abstracted structure: gap → hypothesis → 3 aims (RCT, mechanism, subgroup) with pitfalls/alternatives]",
    ),
]


# === B4 matching ================================================================================


def matched_subset(mechanism: str, topic: str) -> list[ReferenceItem]:
    """The matched human comparison subset for an AI proposal (decision §A, B4): same mechanism AND a
    shared domain term. `topic` is the AI proposal's `GrantCall.title` (matched on contained terms).
    Falls back to mechanism-only if no domain term overlaps (still a fair within-mechanism bar)."""
    t = topic.lower()
    same_mech = [r for r in REFERENCE_SET if r.activity_code == mechanism]
    domain = [r for r in same_mech if any(term in t for term in r.domain_terms)]
    return domain or same_mech


# === The live sampler (specified; network-gated — NOT run offline) ==============================


def fetch_reference_set(*, allow_network: bool = False) -> list[ReferenceItem]:
    """The production RePORTER sampler (decision §A criteria). v1 OFFLINE posture: with the default
    `allow_network=False` this returns the stored `REFERENCE_SET` (no network — the suite uses this).
    The live path (`allow_network=True`) is specified but NOT wired in v1 (mirrors the decision-A
    resolve path, OPEN.md): POST `https://api.reporter.nih.gov/v2/projects/search` with
    `criteria={activity_codes:[mechanism], fiscal_years:[…recent…], award_amount_range:{min_amount:1}}`,
    keep `abstract_text` + Specific Aims for items passing §A (funded · mechanism · domain · recent ·
    DISJOINT from the writer exemplars), abstract each to a `structural_note` skeleton, and store. It is
    intentionally unimplemented offline so the test suite cannot touch the network."""
    if allow_network:  # pragma: no cover — production path, not exercised in the offline v1 suite
        raise NotImplementedError(
            "live RePORTER fetch is network-gated and not wired in v1 (decision §B); "
            "the offline suite uses the stored REFERENCE_SET"
        )
    return list(REFERENCE_SET)


# === Contamination rule (HARD) — provably honored ===============================================


def _reference_identifying_strings(items: list[ReferenceItem]) -> set[str]:
    """The reference content that must NEVER leak into an agent input: the app_id + the abstracted
    structural note (the stand-in for funded prose). `domain_terms` are EXCLUDED — they are the match
    key and legitimately overlap the fixtures' disease vocabulary (decision §A)."""
    out: set[str] = set()
    for r in items:
        out.add(r.app_id)
        out.add(r.structural_note)
    return out


def writer_exemplar_strings() -> set[str]:
    """Every few-shot exemplar string carried by the two writer roles (the only roles that take them —
    §2.4 / design §5). The reference set must be disjoint from these (the §5 / decision §A invariant)."""
    from cua.roles import AimArchitect, ArgumentSynthesizer

    out: set[str] = set()
    for role in (ArgumentSynthesizer(), AimArchitect()):
        out.update(str(e) for e in (role.config.few_shot_exemplars or []))
    return out


def agent_input_strings(fixture) -> set[str]:
    """Every string a fixture feeds the agent (corpus papers, evidence, GrantCall) — what the writers
    could possibly copy. The contamination check asserts no reference-identifying string appears here."""
    out: set[str] = set()
    gc = fixture.grant_call
    for attr in ("title", "mechanism", "foa_id"):
        v = getattr(gc, attr, None)
        if v:
            out.add(str(v))
    for p in fixture.corpus.sources:
        for attr in ("id", "title", "key_finding", "venue", "resolvable_id"):
            v = getattr(p, attr, None)
            if v:
                out.add(str(v))
        out.update(str(a) for a in getattr(p, "authors", []) or [])
    for entry in fixture.evidence.values():
        out.update(str(c) for c in getattr(entry, "caveats", []) or [])
        out.update(str(s) for s in getattr(entry, "support_source_ids", []) or [])
    return out


def contamination_report(items: list[ReferenceItem] | None = None) -> dict:
    """Check the contamination rule over the stored set against ALL fixtures + the writer exemplars.
    Returns a structured report (used by `assert_contamination_free` and the EvalReport). HONORS iff:
      (1) reference identifying strings ∩ writer few-shot exemplars = ∅ (disjointness invariant); and
      (2) no reference identifying string appears (as a substring) in ANY fixture's agent inputs."""
    from testdata import all_fixtures

    items = items if items is not None else list(REFERENCE_SET)
    ref_strings = _reference_identifying_strings(items)

    exemplar_overlap = sorted(ref_strings & writer_exemplar_strings())

    input_leaks: list[str] = []
    for fx in all_fixtures():
        blob = "\n".join(agent_input_strings(fx))
        for s in ref_strings:
            if s in blob:
                input_leaks.append(f"{fx.name}:{s}")

    honored = not exemplar_overlap and not input_leaks
    return {
        "honored": honored,
        "n_reference_items": len(items),
        "exemplar_overlap": exemplar_overlap,
        "input_leaks": input_leaks,
    }


def assert_contamination_free(items: list[ReferenceItem] | None = None) -> None:
    """Raise AssertionError if the contamination rule is violated (test-review Boundaries; the rigged-
    comparison hard fail). Provable honoring for `test_eval.py`."""
    rep = contamination_report(items)
    assert rep["honored"], (
        f"contamination rule violated — exemplar_overlap={rep['exemplar_overlap']}, "
        f"input_leaks={rep['input_leaks']}"
    )
