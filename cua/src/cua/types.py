"""types.py — engine value types [code].

Implements: contracts.md §1.1 (Source/SourceSet/Grade/EvidenceScores), §1.2 (Obligation/
            ObligationPublic), §1.3 (Task), §1.4 (DraftFragment/Draft/GroundedDraft/Artifact),
            §1.7 (CritiqueReport), §1.12 (Level ladder + permitted()).
Generic role: the task-agnostic value vocabulary every engine role exchanges.
NIH binding: bound under cua.nih (Source→Paper, EvidenceScores→EvidenceAssessment, …; design §2 map).
Owner: S2 (builder 1).  Authoritative engine types; testdata/types.py mirrors a subset and imports
       from here (S1-gate ruling, build/decisions/2026-06-01-expectations-oracle-semantics.md).

Leak rule (CONVENTIONS rule 1): this file names no domain nouns — only generic vocabulary
(source / reference / draft / artifact / dimension / obligation / grade / level / claim).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # forward-only; defined in grounding.py to keep that module the report builder
    from .grounding import GroundingReport


# === §1.1 Value types =============================================================================


class Grade(Enum):
    """Evidence strength — ordinal, NOT a probability (contracts.md §1.1). Ordering is via
    GRADE_RANK below; the enum itself is unordered. Decision B (OPEN.md) confirms this ordinal set
    upstream, but the engine already treats grade as ordinal here."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    MINIMAL = "minimal"


# Ordinal rank (strong > moderate > weak > minimal).
GRADE_RANK: dict[Grade, int] = {Grade.MINIMAL: 0, Grade.WEAK: 1, Grade.MODERATE: 2, Grade.STRONG: 3}
GRADE_VALUES: frozenset[str] = frozenset(g.value for g in Grade)


class Level(Enum):
    """Assertiveness ladder for a claim (contracts.md §1.12). Ordinal via LEVEL_RANK; L4 most
    assertive (causal) down to L1 (exploratory). MEASURED independently by level() (grounding.py)."""

    L4 = "L4"  # causal
    L3 = "L3"  # associative
    L2 = "L2"  # suggestive
    L1 = "L1"  # exploratory


LEVEL_RANK: dict[Level, int] = {Level.L1: 1, Level.L2: 2, Level.L3: 3, Level.L4: 4}

# permitted(grade): strong→L4, moderate→L3, weak→L2, minimal→L1 (contracts.md §1.12, round DOWN).
_PERMITTED: dict[Grade, Level] = {
    Grade.STRONG: Level.L4,
    Grade.MODERATE: Level.L3,
    Grade.WEAK: Level.L2,
    Grade.MINIMAL: Level.L1,
}


def permitted(grade: Grade) -> Level:
    """Highest assertiveness `grade` licenses (contracts.md §1.12). Pure value map — no model."""

    return _PERMITTED[grade]


@dataclass
class Source:
    """A citable evidence item (contracts.md §1.1: { id, metadata, resolvable_id? }). The binding
    specializes this (a concrete Source carries domain fields); the engine relies only on `.id`."""

    id: str
    metadata: dict = field(default_factory=dict)
    resolvable_id: str | None = None


@dataclass
class SourceSet:
    """The citable evidence set (contracts.md §1.1). Holds any object exposing `.id` (the binding's
    concrete Source). `ids()` is the membership set the reference-integrity gate checks against."""

    sources: list = field(default_factory=list)

    def ids(self) -> set[str]:
        return {s.id for s in self.sources}


@dataclass
class EvidenceEntry:
    """One value of EvidenceScores: `{ grade, evidence_features, support_source_ids[], caveats }`
    (contracts.md §1.1). The agent only ENFORCES the ladder over these grades — it never produces or
    revises a grade (§1.12)."""

    grade: Grade
    evidence_features: dict
    support_source_ids: list[str]
    caveats: list[str] = field(default_factory=list)


class EvidenceScores(dict):
    """`map claim_id -> EvidenceEntry` (contracts.md §1.1). A claim_id absent from this map is an
    UNSCORED claim → the agent defaults it to `minimal` and flags it (§1.12, §2.5). The binding
    aliases this (EvidenceAssessment)."""


@dataclass
class InputDelta:
    """A mutation to a Task input (contracts.md §1.1). Consumed at PLAN time by a SteeringSource;
    never an in-loop edit of obligations (§1.9)."""

    target: str
    change: Any


@dataclass
class SectionSpec:
    """A section of the artifact and the dimension it serves (contracts.md §1.1)."""

    name: str
    serves_dimension: str
    target_words: int


@dataclass
class Budget:
    """Word budget compiled from the Condition (contracts.md §1.1)."""

    sections: dict[str, int] = field(default_factory=dict)
    total_word_limit: int = 0


@dataclass
class RunConfig:
    """Orchestrator hyperparameters (contracts.md §1.1, §1.11). `dimension_thresholds` is the gated
    bar per scored dimension — unset values (gap 8) mean that dimension is not gated; the operator
    sets the real bar at S6.

    `force_rounds` is an additive, defaulted compute knob (peer of `max_rounds`): when set, the loop
    runs EXACTLY that many revise rounds regardless of the pass-based stopping rule — a fixed loop
    depth that guarantees the revise leg fires. `None` (default) → the §1.11 pass-based path is
    unchanged, byte-for-byte. It only ADDS revisions; every trust gate (the decide, inv-1/2/3) still
    runs each round, so it can never bypass a check (orchestrator §1.11)."""

    max_rounds: int
    dimension_thresholds: dict[str, int] = field(default_factory=dict)
    force_rounds: int | None = None


# === §1.2 Condition & obligations ================================================================


class Status(Enum):
    UNSATISFIED = "unsatisfied"
    AT_RISK = "at_risk"
    SATISFIED = "satisfied"


@dataclass
class Obligation:
    """A compiled, checkable unit of a Condition (contracts.md §1.2). `requirement` is a CONCRETE
    predicate; `self_score` is the writer's self-assessment (int for a scored dimension, or a
    {sufficient|insufficient} string)."""

    id: str
    dimension: str
    requirement: str
    satisfied_by: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    self_score: int | str | None = None
    status: Status = Status.UNSATISFIED
    notes: str = ""


@dataclass
class ObligationPublic:
    """Obligation MINUS { self_score, notes } — the view passed to the Critic for scoring
    independence (contracts.md §1.2, §1.5). Built by `public_view()`."""

    id: str
    dimension: str
    requirement: str
    satisfied_by: list[str]
    evidence_ids: list[str]
    status: Status


def public_view(obligation: Obligation) -> ObligationPublic:
    """Strip the writer's self_score/notes before handing an obligation to the Critic (§1.5)."""

    return ObligationPublic(
        id=obligation.id,
        dimension=obligation.dimension,
        requirement=obligation.requirement,
        satisfied_by=list(obligation.satisfied_by),
        evidence_ids=list(obligation.evidence_ids),
        status=obligation.status,
    )


# === §1.4 Drafts =================================================================================


@dataclass
class Claim:
    """An empirical/evaluative claim the writer emits, tagged with the dimension it serves and the
    evidence ids backing it (contracts.md §1.4; generation tags every claim, §2.2). `reference_ids`
    are the source ids this claim cites — the reference-integrity gate (inv-1) checks them.

    `subject`/`predicate` carry the claim's cue-free proposition (the parts the writer rendered into
    `text` at a chosen assertiveness rung). They are the handle that lets a downstream surgical edit
    RE-PHRASE the claim at a different rung without re-running the writer — the reverse of the §1.12
    write↔measure round-trip. Generic (no domain noun); never serialized into an Artifact/Audit."""

    id: str
    text: str
    evidence_ids: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    serves_dimension: str | None = None
    subject: str = ""
    predicate: str = ""


@dataclass
class DraftFragment:
    """Partial artifact content emitted by one GenerationStage (contracts.md §1.4). `provides`
    exposes named item collections a downstream stage can `map_over` (the engine resolves a stage's
    `map_over` ref against these — the ref name is binding data, never an engine identifier)."""

    stage: str
    section: str
    text: str
    segment_id: str | None = None
    claims: list[Claim] = field(default_factory=list)
    serves_dimension: str | None = None
    provides: dict[str, list] = field(default_factory=dict)

    def reference_ids(self) -> list[str]:
        out: list[str] = []
        for c in self.claims:
            out.extend(c.reference_ids)
        return out


@dataclass
class Draft:
    """Artifact-in-progress (sections + segments), pre-grounding (contracts.md §1.4). The Generator
    driver merges each DraftFragment into here."""

    fragments: list[DraftFragment] = field(default_factory=list)

    def claims(self) -> list[Claim]:
        out: list[Claim] = []
        for f in self.fragments:
            out.extend(f.claims)
        return out

    def reference_ids(self) -> list[str]:
        """Every source id cited anywhere in the draft, de-duplicated, order-preserved."""
        out: list[str] = []
        for f in self.fragments:
            out.extend(f.reference_ids())
        return list(dict.fromkeys(out))


@dataclass
class GroundedDraft:
    """A Draft after the Grounder binds references; carries a GroundingReport (contracts.md §1.4).
    `grounding_report` is a forward reference — GroundingReport is defined in grounding.py."""

    draft: Draft
    grounding_report: "GroundingReport"


class Artifact:
    """The finished, grounded deliverable (contracts.md §1.4). The binding defines the concrete
    subtype; the engine only carries it through as an opaque result."""


# === §1.7 Critic output ==========================================================================


@dataclass
class DimensionScore:
    """Whole-draft score on one dimension (contracts.md §1.7) — drives the stopping rule."""

    score: int
    justification: str = ""
    spans: list[str] = field(default_factory=list)


@dataclass
class SegmentScore:
    """Per fan-out item score (contracts.md §1.7) — validated per-segment quality (audit)."""

    dimension: str
    score: int
    justification: str = ""


@dataclass
class CritiqueReport:
    """The Critic's output (contracts.md §1.7). `decision` ∈ {pass, revise}."""

    dimension_scores: dict[str, DimensionScore] = field(default_factory=dict)
    segment_scores: dict[str, SegmentScore] = field(default_factory=dict)
    decision: str = "revise"
    flagged_obligations: list[str] = field(default_factory=list)


@dataclass
class ScoredFragment:
    """One ranked best-of-N candidate (contracts.md §1.5 SelectionScorer output). `rationale` is the
    ranker's per-candidate note — additive + defaulted (the surrogate leaves it ''); it is observation-only
    (read by the content-capture sink, never by the driver, which picks by `score`) and never serialized
    into the Artifact/Trace/Audit, so the offline byte oracle is unaffected."""

    fragment: DraftFragment
    score: float
    rationale: str = ""


# === §1.2 / §1.3 / §1.6 / §1.9 abstract roles ====================================================


class Condition(ABC):
    """Abstract Condition (contracts.md §1.2): compiles a Task into obligations + a Budget."""

    @abstractmethod
    def compile(self, task: "Task") -> tuple[list[Obligation], Budget]: ...


class GenerationStage(ABC):
    """One stage of the staged Generator (contracts.md §1.6). `map_over=None` runs once; otherwise
    the driver runs `produce` once per item at that ref in the draft-so-far. Only `produce` is the
    (LLM, stubbed in S2) call."""

    name: str
    config: Any  # RoleConfig (cua.config) — Any to avoid importing config into the type vocabulary
    map_over: str | None = None

    @abstractmethod
    def produce(
        self,
        obligations: list[Obligation],
        inputs: dict,
        draft_so_far: Draft,
        item: Any | None = None,
    ) -> DraftFragment: ...


class SteeringSource(ABC):
    """Emits input deltas consumed at PLAN time (contracts.md §1.9). Never an in-loop edit."""

    @abstractmethod
    def poll(self) -> InputDelta | None: ...


class Task(ABC):
    """Abstract Task (contracts.md §1.3). The binding supplies the concrete pieces and the two
    binding hooks below (artifact assembly + intake refusal), keeping the engine domain-free."""

    artifact_type: type
    condition: Condition
    input_contract: dict
    sections: list[SectionSpec]
    source_set: SourceSet
    generator: list[GenerationStage]
    steering_sources: list[SteeringSource]

    @abstractmethod
    def inputs(self) -> dict:
        """The input slots the Generator consumes (contracts.md §1.5 Generator signature)."""

    @abstractmethod
    def assemble_artifact(
        self,
        grounded: GroundedDraft,
        obligations: list[Obligation],
        revision_round: int,
        degraded: bool,
    ) -> Artifact:
        """Build the finished Artifact from the final grounded draft (binding-specific, §1.4)."""

    def intake_refusal(self) -> str | None:
        """Return a refusal reason if the Task cannot start (contracts.md §2.5), else None. The
        engine treats this as opaque; the binding decides what 'not ready' means."""
        return None


# === Role interfaces (structural; concrete impls injected into the Orchestrator) =================
# The engine drives these by duck-typing; the Protocols document the frozen §1.5 signatures.


class Conditioner(Protocol):
    """[LLM] (Task) -> (obligations, Budget) — contracts.md §1.5."""

    def compile(self, task: Task) -> tuple[list[Obligation], Budget]: ...


class Critic(Protocol):
    """[LLM] (GroundedDraft, [ObligationPublic], EvidenceScores, external_critiques) -> CritiqueReport
    — contracts.md §1.5. Receives ObligationPublic only (no self_score) for scoring independence."""

    def critique(
        self,
        grounded: GroundedDraft,
        obligations_public: list[ObligationPublic],
        evidence_scores: EvidenceScores,
        external_critiques: list,
    ) -> CritiqueReport: ...


class Reviser(Protocol):
    """[LLM] (prior_draft, CritiqueReport, external_critiques, flagged_obligations) -> Draft — §1.5."""

    def revise(
        self,
        prior_draft: Draft,
        critique: CritiqueReport,
        external_critiques: list,
        flagged_obligations: list[str],
    ) -> Draft: ...


class SelectionScorer(Protocol):
    """[LLM, light] (candidates, dimension) -> [{fragment, score}] — contracts.md §1.5. A cheap,
    separate judge kept out of the writer's lineage; NOT the Critic."""

    def score(self, candidates: list[DraftFragment], dimension: str) -> list[ScoredFragment]: ...
