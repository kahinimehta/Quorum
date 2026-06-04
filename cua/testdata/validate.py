"""validate.py — fixture validation gate [test-data].

Implements: test_data_contract §6 (validate: type-check every field vs the main contract; confirm
            `input_contract.required` populated; internal consistency claim_id ↔ support_source_ids
            ↔ corpus BEFORE the fixture is handed to the agent). Brief req 7 + done-criteria.
Checks against: contracts.md §1.1 (value types), §2.1 (Paper/EvidenceAssessment), §2.3
            (NIHGrantTask.input_contract: required{GrantCall, corpus, EvidenceAssessment}),
            §2.5 (corpus non-empty, stable ids). test-data §2 (SYNTH- prefix, resolvable_id format),
            §3 (grade set, support ∈ corpus), §5 (Expectations).
Generic role: input gate over stand-in upstream data · NIH binding: corpus / EvidenceAssessment.
Owner: S1 (builder 2).

This is the test-data layer's own gate — NOT the agent's hard invariants (inv-1/2/3, contract §3,
owned by S3). It runs offline, no LLM, no network, and rejects a malformed fixture before the agent
ever sees it. A *declared* fabrication plant (an orphan id listed in Expectations.expected_orphan_ids)
is legal; an *undeclared* out-of-corpus support id is a fixture bug and is rejected.
"""

from __future__ import annotations

from .types import (
    EvidenceEntry,
    Expectations,
    Fixture,
    Grade,
    GrantCall,
    Paper,
    SourceSet,
    GRADE_VALUES,
)

# `input_contract.required` slots (contracts.md §2.3). Optional slots (subgroups/treatments/
# commercial) are not required to be populated and so are validated only when present.
REQUIRED_SLOTS = ("grant_call", "corpus", "evidence")


class FixtureValidationError(ValueError):
    """Raised by `validate()` when a Fixture is not safe to hand to the agent (test-data §6)."""


def _looks_like_doi(s: str) -> bool:
    return s.startswith("10.") and "/" in s


def _looks_like_pmid(s: str) -> bool:
    return s.isdigit() and 4 <= len(s) <= 9


def validation_errors(fx: Fixture) -> list[str]:
    """Return every problem found (empty ⇒ valid). `validate()` wraps this and raises."""
    errs: list[str] = []

    # --- 0. bundle shape (test-data §1) --------------------------------------------------------
    if not isinstance(fx, Fixture):
        return [f"not a Fixture: {type(fx).__name__}"]
    if not isinstance(fx.name, str) or not fx.name:
        errs.append("name: must be a non-empty str")
    if not isinstance(fx.seed, int) or isinstance(fx.seed, bool):
        errs.append("seed: must be an int (determinism key, test-data §6)")

    # --- 1. required slots populated (input_contract.required, §2.3) ---------------------------
    for slot in REQUIRED_SLOTS:
        if getattr(fx, slot, None) is None:
            errs.append(f"required slot '{slot}' is missing (input_contract.required, §2.3)")

    # --- 2. GrantCall: mechanism + limits KNOWN, else refuse to start (§2.5) --------------------
    gc = fx.grant_call
    if isinstance(gc, GrantCall):
        if not gc.mechanism:
            errs.append("grant_call.mechanism: required (mechanism KNOWN, §2.5)")
        if not gc.due_date:
            errs.append("grant_call.due_date: required")
        for lim in ("specific_aims_page_limit", "research_strategy_page_limit"):
            v = getattr(gc, lim, None)
            if not isinstance(v, int) or v <= 0:
                errs.append(f"grant_call.{lim}: must be a positive int (limits KNOWN, §2.5)")
    elif gc is not None:
        errs.append(f"grant_call: must be GrantCall, got {type(gc).__name__}")

    # --- 3. corpus: non-empty, SYNTH- ids, key_finding, plausible resolvable_id (§2.5, td §2) ---
    corpus_ids: set[str] = set()
    cs = fx.corpus
    if isinstance(cs, SourceSet):
        if not cs.sources:
            errs.append("corpus: must be non-empty with stable ids (§2.5)")
        seen: set[str] = set()
        for i, p in enumerate(cs.sources):
            where = f"corpus[{i}]"
            if not isinstance(p, Paper):
                errs.append(f"{where}: must be Paper, got {type(p).__name__}")
                continue
            if not p.id or not p.id.startswith("SYNTH-"):
                errs.append(f"{where}.id '{p.id}': every synthetic Paper.id needs the SYNTH- prefix (td §2)")
            if p.id in seen:
                errs.append(f"{where}.id '{p.id}': duplicate corpus id")
            seen.add(p.id)
            corpus_ids.add(p.id)
            if not p.authors:
                errs.append(f"{where}.authors: required (§2.1)")
            if not isinstance(p.year, int):
                errs.append(f"{where}.year: must be int (§2.1)")
            if not p.title:
                errs.append(f"{where}.title: required (§2.1)")
            if not p.key_finding:
                errs.append(f"{where}.key_finding: required — a claim must be groundable on it (td §2; req 5)")
            if not isinstance(p.real, bool):
                errs.append(f"{where}.real: must be bool (td §2)")
            if not p.resolvable_id or not (_looks_like_doi(p.resolvable_id) or _looks_like_pmid(p.resolvable_id)):
                errs.append(f"{where}.resolvable_id '{p.resolvable_id}': must look like a DOI or PMID (td §2)")
    elif cs is not None:
        errs.append(f"corpus: must be SourceSet, got {type(cs).__name__}")

    # --- 4. evidence: grade set + features + caveats shape (§1.1, td §3) ------------------------
    ev = fx.evidence
    if ev is not None and not hasattr(ev, "items"):
        errs.append(f"evidence: must be a claim_id->entry map, got {type(ev).__name__}")
        ev = {}
    if isinstance(ev, dict) and not ev:
        errs.append("evidence: EvidenceAssessment must be non-empty (required slot, §2.3)")
    for claim_id, entry in (ev or {}).items():
        where = f"evidence['{claim_id}']"
        if not isinstance(claim_id, str) or not claim_id:
            errs.append(f"evidence: claim_id keys must be non-empty str (got {claim_id!r})")
        if not isinstance(entry, EvidenceEntry):
            errs.append(f"{where}: must be EvidenceEntry, got {type(entry).__name__}")
            continue
        if not isinstance(entry.grade, Grade) or entry.grade.value not in GRADE_VALUES:
            errs.append(f"{where}.grade: must be one of {sorted(GRADE_VALUES)} (ordinal, §1.1/td §3)")
        if not isinstance(entry.evidence_features, dict) or not entry.evidence_features:
            errs.append(f"{where}.evidence_features: required non-empty dict (design/n/effect…, td §3; req 3)")
        if not isinstance(entry.support_source_ids, list) or not entry.support_source_ids:
            errs.append(f"{where}.support_source_ids: a scored claim needs >=1 supporting id (td §3)")
        if not isinstance(entry.caveats, list):
            errs.append(f"{where}.caveats: must be a list (§1.1)")

    # --- 5. Expectations shape (test-data §5) ---------------------------------------------------
    exp = fx.expectations
    if isinstance(exp, Expectations):
        if not isinstance(exp.expect_pass, bool):
            errs.append("expectations.expect_pass: must be bool (td §5)")
        for fld in ("expected_overclaim_claim_ids", "expected_orphan_ids"):
            v = getattr(exp, fld)
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errs.append(f"expectations.{fld}: must be list[str] (td §5)")
        if not isinstance(exp.min_obligations_satisfied, int) or exp.min_obligations_satisfied < 0:
            errs.append("expectations.min_obligations_satisfied: must be int >= 0 (td §5)")
    elif exp is None:
        errs.append("expectations: required oracle block (td §5)")
    else:
        errs.append(f"expectations: must be Expectations, got {type(exp).__name__}")

    # --- 6. INTERNAL CONSISTENCY: claim_id ↔ support_source_ids ↔ corpus (td §6; req 4) ---------
    # This is the gate's teeth. Every support id must be in corpus, EXCEPT a deliberately-planted
    # orphan declared in expectations.expected_orphan_ids (fabrication_bait). An UNDECLARED
    # out-of-corpus support id is a misaligned-fixture bug and is rejected.
    declared_orphans: set[str] = set(exp.expected_orphan_ids) if isinstance(exp, Expectations) else set()
    referenced_support: set[str] = set()
    for claim_id, entry in (ev or {}).items():
        if not isinstance(entry, EvidenceEntry):
            continue
        for sid in entry.support_source_ids:
            referenced_support.add(sid)
            if sid not in corpus_ids and sid not in declared_orphans:
                errs.append(
                    f"evidence['{claim_id}'].support_source_ids: '{sid}' is neither in corpus nor a "
                    f"declared orphan (expected_orphan_ids) — misaligned claim↔source (td §6; req 4)"
                )

    # A declared orphan must be (a) genuinely absent from corpus and (b) actually used as support —
    # otherwise the negative test plants nothing real for inv-1 to catch.
    for orphan in declared_orphans:
        if orphan in corpus_ids:
            errs.append(f"expected_orphan_ids: '{orphan}' is IN corpus — not an orphan (td §6)")
        if orphan not in referenced_support:
            errs.append(f"expected_orphan_ids: '{orphan}' is not referenced by any claim — nothing to catch (td §6)")

    return errs


def validate(fx: Fixture) -> None:
    """Type-check every field vs the main contract, confirm `input_contract.required` is populated,
    and confirm internal consistency (claim_id ↔ support_source_ids ↔ corpus) BEFORE the fixture is
    handed to the agent (test-data §6). Raises `FixtureValidationError` listing every problem;
    returns None when the fixture is valid."""
    errs = validation_errors(fx)
    if errs:
        name = getattr(fx, "name", "<unknown>")
        raise FixtureValidationError(
            f"fixture '{name}' failed validation ({len(errs)} problem(s)):\n  - " + "\n  - ".join(errs)
        )
