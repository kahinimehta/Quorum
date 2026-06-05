"""types.py — fixture types [test-data].

Implements: test_data_contract §1 (Fixture bundle), §2 (synthetic Paper), §3 (EvidenceAssessment),
            §5 (Expectations), §6 (determinism helpers).
Populates : contracts.md §1.1 (Source/SourceSet/Grade/EvidenceScores), §2.1 (Paper/EvidenceAssessment),
            §2.3 (NIHGrantTask.input_contract slots: GrantCall, corpus, EvidenceAssessment +
            optional subgroups/treatments/commercial).
Generic role: stand-in upstream inputs (SourceSet / Source / EvidenceScores) · NIH binding:
              corpus / Paper / EvidenceAssessment + GrantCall (design §2 map).
Owner: S1 (builder 2); reconciled against the engine at the S2 gate (builder 1).

RECONCILED (S2 gate — companion ruling, build/decisions/2026-06-01-expectations-oracle-semantics.md;
OPEN.md gap 1): the generic value types `Grade`, `SourceSet`, `EvidenceEntry` are now IMPORTED from
the authoritative engine `cua.types`, and the NIH-binding types `Paper`, `EvidenceAssessment` from
`cua.nih.framework` — the fixtures no longer mirror them locally. Field shapes are byte-identical to
the former mirror, so the determinism digests (test-data §6) are preserved. `GrantCall`, `Subgroup`,
`Treatment`, `CommercialLandscape`, `ExternalCritique` remain **minimal stand-in shapes** here
(real upstream output contracts unpinned; OPEN.md gap 1) until their owners ship contracts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

# --- Authoritative engine types (reconciled — imported, not mirrored) --------------------------
from cua.nih.framework import EvidenceAssessment, Paper  # NIH-binding Source + EvidenceScores alias
from cua.types import (  # generic value vocabulary (contracts.md §1.1)
    GRADE_RANK,
    GRADE_VALUES,
    EvidenceEntry,
    Grade,
    SourceSet,
)

# Re-exported so scenarios.py / validate.py / testdata.__init__ can keep importing from `.types`.
_RECONCILED_NAMES = (Grade, GRADE_RANK, GRADE_VALUES, SourceSet, EvidenceEntry, Paper, EvidenceAssessment)


# --- Minimal stand-in upstream shapes (UNPINNED upstream; OPEN.md gap 1) ------------------------
# Their real output contracts are owned by other teams and still missing (design §6 gap). Builder 2
# defines a minimal shape so the agent can run; any mismatch with the real contract is a fixture bug,
# not an agent bug. Each is flagged in build/decisions/OPEN.md for reconciliation.


@dataclass
class GrantCall:
    """STAND-IN (unpinned). Carries the `NIHGrantTask` intake the Orchestrator needs to NOT refuse:
    mechanism + limits must be KNOWN, else the agent refuses to start (contracts.md §2.5). The
    Conditioner (Blueprint Planner) compiles these limits into a `Budget` (§1.1) — not S1's job."""

    mechanism: str  # e.g. "R01" — activity code
    title: str
    foa_id: str  # funding-opportunity announcement id, e.g. "PAR-25-123"
    specific_aims_page_limit: int  # NIH: Specific Aims = 1 page
    research_strategy_page_limit: int  # mechanism-dependent (R01 ≈ 12)
    due_date: str  # ISO date; RPG due dates ≥ 2025-01-25 use the Simplified Review Framework
    review_framework: str = "NIH Simplified Review Framework (2025)"


@dataclass
class Subgroup:
    """STAND-IN (unpinned, Patient Subgroup agent). Optional input (§2.3) — raises the ceiling."""

    name: str
    definition: str
    rationale: str


@dataclass
class Treatment:
    """STAND-IN (unpinned, Treatment Connection agent). Optional input (§2.3)."""

    name: str
    modality: str
    target: str
    development_stage: str


@dataclass
class CommercialLandscape:
    """STAND-IN (unpinned, Commercial Discovery agent). Optional (§2.3); MUST carry
    `grant_contribution` (test-data §1). Consumed by the Synthesizer; deltas enter via
    CommercialDiscoverySteering at PLAN time (§1.9, §2.3) — never an in-loop edit."""

    grant_contribution: str
    market_note: str = ""
    competitors: list[str] = field(default_factory=list)
    ip_position: str = ""


@dataclass
class ExternalCritique:
    """STAND-IN (unpinned). `external_critiques` enter via the Orchestrator as inputs to the Critic/
    Reviser, never as tool calls (contracts.md §1.5). Minimal shape for the revise-loop fixtures."""

    source: str  # "skeptic" | "commercial"
    severity: str  # "low" | "medium" | "high"
    comment: str
    target_ref: str = ""


# --- Oracle + bundle (test-data §5, §1) --------------------------------------------------------


@dataclass
class Expectations:
    """Best-effort oracle for the tester (builder 3), NOT ground-truth science (test-data §5;
    brief req 6). SEMANTICS (S1 interpretation — the contract leaves these as "best-effort"; flagged
    in OPEN.md gap 1): the block describes the verdict of the offline hard-invariant suite
    (inv-1 citation / inv-2 coverage / inv-3 overclaim, contracts.md §3) on the scenario taken at
    FACE VALUE — i.e. the bait un-resisted. That snapshot is what gives the negatives teeth
    (design §6 S6: negatives "fail-as-expected first, then pass" once the agent hedges/drops).

    - `expect_pass`: would a faithful, un-defended draft of this scenario pass inv-1/2/3?
    - `expected_overclaim_claim_ids`: claim_ids whose tempting (narrative-level) assertiveness exceeds
      what their evidence grade permits → inv-3/overclaim_check must flag them; a correct agent must
      hedge them down (§1.12). For `unscored_claim`, the unscored claim_id appears HERE while being
      intentionally ABSENT from `evidence` — that absence IS the unscored condition (→ minimal → L1).
    - `expected_orphan_ids`: cited ids NOT in corpus (fabrications); inv-1 must list them (fabrication_bait).
    - `min_obligations_satisfied`: coarse best-effort LOWER bound on satisfiable obligations. The real
      `RubricObligation` instantiation is S4's (nih_obligations specialization, gap 2); treat as a
      floor, not an exact count.
    """

    expect_pass: bool
    expected_overclaim_claim_ids: list[str] = field(default_factory=list)
    expected_orphan_ids: list[str] = field(default_factory=list)
    min_obligations_satisfied: int = 0


@dataclass
class Fixture:
    """The bundle satisfying `NIHGrantTask.input_contract` (contracts.md §2.3; test-data §1).
    required{ grant_call, corpus, evidence } · optional{ subgroups, treatments, commercial }.
    `external_critiques` feeds the revise loop (§1.5); `expectations` is the tester oracle (§5)."""

    name: str
    seed: int
    grant_call: GrantCall
    corpus: SourceSet
    evidence: EvidenceAssessment
    expectations: Expectations
    subgroups: list[Subgroup] | None = None
    treatments: list[Treatment] | None = None
    commercial: CommercialLandscape | None = None
    external_critiques: list[ExternalCritique] | None = None


# --- Determinism helpers (test-data §6: same seed ⇒ identical Fixture) --------------------------


def _json_default(obj):
    if isinstance(obj, Grade):
        return obj.value
    raise TypeError(f"not JSON-serializable: {type(obj).__name__}")


def canonical_json(fixture: Fixture) -> str:
    """Canonical, key-sorted JSON of a Fixture. Stable across runs: no sets, no timestamps, no RNG
    state — dict keys (incl. claim_ids and evidence_features) are sorted, list order is preserved
    (corpus order is deterministic). Two Fixtures are byte-identical iff this string is identical."""

    return json.dumps(
        asdict(fixture),
        default=_json_default,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def digest(fixture: Fixture) -> str:
    """sha256 of `canonical_json` — the determinism fingerprint (test-data §6; brief done-criterion
    'same seed ⇒ byte-identical fixture')."""

    return hashlib.sha256(canonical_json(fixture).encode("utf-8")).hexdigest()
