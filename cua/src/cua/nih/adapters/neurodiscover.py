"""neurodiscover.py — NIH binding: adapter from the upstream `neurodiscover` DB → input_contract.

Implements: PLAN §(c) adapter spec; contracts.md §1.1 (Source/Grade/EvidenceScores), §2.1
            (Paper/EvidenceAssessment), §2.5 (degradation via NULL→minimal).
Governing: build/integration/adaption.md #1–#10 (the mapping rules) and the GATE-1 decision
           `build/decisions/2026-06-02-decisionB-v1-surrogate-grade-RATIFIED.md` (the grade surrogate).
Generic role: none — this is a binding-layer INPUT adapter; it never enters the engine spine.
NIH binding: reads upstream's `neurodiscover` blackboard (evidence / subgroups / treatment_connections
             / connection_evidence) and assembles `corpus` + `EvidenceAssessment` + `subgroups` +
             `treatments`, then calls the UNCHANGED `cua.nih.task.build_task(...)`.
Owner: INT-2 (builder 1). Domain nouns are legal here (binding layer, CONVENTIONS rule 1).

Posture (adaption.md): CUA is a READ-ONLY downstream consumer. This module issues **SELECT only** —
never `build`/DDL/`INSERT`/`UPDATE`. It does NOT depend on upstream's Python package; it takes a DB
connection / URL / path and duck-types the read.

Determinism + offline: every SELECT carries an `ORDER BY` on a stable key, so the assembled task is
byte-stable regardless of DB row order; no clock, no RNG. Importing this module connects nothing —
a connection is opened only when a URL/path is passed (psycopg is imported lazily, inside that branch).

Two corrections the upstream PLAN/AGENT_IO would get WRONG (and that this adapter deliberately avoids):
  1. We do NOT apply the "Agent-6 read" filter (`evidence_strength IS NOT NULL AND commercial_potential
     IS NOT NULL`). Agents 4 & 5 are unbuilt → every score is NULL → that filter returns zero rows.
     We read ALL `treatment_connections` regardless of score; NULL `evidence_strength` → `minimal`.
  2. The domain tables (evidence/subgroups/treatment_connections/connection_evidence) are NOT
     run-scoped — they have no `run_id` column. The blackboard is cumulative; we read CURRENT state.
     `run_id` is carried for provenance/labeling only and never filters a domain read.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ..task import NIHGrantTask, build_task
from ...types import EvidenceEntry, Grade, SourceSet
from ..framework import EvidenceAssessment, Paper

# Provenance flag REQUIRED by GATE-1: every bucketed grade is marked uncalibrated so no downstream
# reader (Critic, eval, review, dashboard) can mistake it for a calibrated skeptic grade.
GRADE_SOURCE = "neurodiscover_bucket_v1"
_UNCALIBRATED = {"grade_source": GRADE_SOURCE, "calibrated": False}


# === authoritative optional-slot types (field-identical to the testdata stand-ins) ===============
# Production must not import `testdata`. The engine consumes these duck-typed (nothing reads their
# fields in v1; they are carried-through context that raises the ceiling). Field-identical to the
# stand-ins (testdata/types.py) so any future duck-typed read matches — same rationale as INT-1's
# authoritative GrantCall.


@dataclass
class Subgroup:
    """A patient subgroup (optional §2.3 input). `definition ← defining_features`, `rationale ←
    notes` (adaption.md #8)."""

    name: str
    definition: str
    rationale: str


@dataclass
class Treatment:
    """A treatment connection (optional §2.3 input). `name ← treatment`, `target ← mechanism`,
    `modality=""` (no upstream signal — don't invent), `development_stage` = the most-advanced
    backing `study_type` (adaption.md #9, descriptive only — NOT a grade, inv-3 untouched)."""

    name: str
    modality: str
    target: str
    development_stage: str


@dataclass
class _DbInputs:
    """A fixture-shaped carrier so `build_task` is called UNCHANGED (it reads these attributes off a
    fixture). NOT a fixture / NOT from testdata — assembled here from the live DB read."""

    grant_call: object
    corpus: SourceSet
    evidence: EvidenceAssessment
    subgroups: list = field(default_factory=list)
    treatments: list = field(default_factory=list)
    commercial: object | None = None  # omitted at v1 (adaption.md #10)
    external_critiques: list = field(default_factory=list)


# === grade surrogate (GATE-1) ====================================================================


def bucket_grade(evidence_strength) -> Grade:
    """Bucket upstream's `evidence_strength ∈ [0,100]` REAL → ordinal `Grade` (GATE-1), round DOWN on
    ties; NULL/absent → `minimal`. Emits a real ordinal Grade — NO raw float leaks past the adapter.

      strong [75,100] · moderate [50,75) · weak [25,50) · minimal [0,25) and NULL.

    We do NOT author grades (separation-of-lineage §1.12) — we only bucket the upstream float or
    default minimal; the result is flagged UNCALIBRATED in `evidence_features`."""

    if evidence_strength is None:
        return Grade.MINIMAL
    s = float(evidence_strength)
    if s >= 75:
        return Grade.STRONG
    if s >= 50:
        return Grade.MODERATE
    if s >= 25:
        return Grade.WEAK
    return Grade.MINIMAL


# === resolvable-id scheme detection (adaption.md #1 / decision A) =================================


def resolvable_id(source_type: str, source_id: str, doi: str | None = None) -> str:
    """The id the (gated/offline) resolver would use, scheme-detected per decision A:
      - literature: PMID iff `source_id.isdigit()`, else DOI (a PMID-less lit row carries the DOI AS
        `source_id`; the `doi` column mirrors it, so prefer `doi` when present);
      - trial → NCT id; grant → core_project_num — both are the `source_id` directly.
    The resolver re-detects the scheme by shape (#1); DEMO ids are never resolved (real=False)."""

    sid = str(source_id)
    if source_type == "literature" and not sid.isdigit():
        return str(doi) if doi else sid  # DOI scheme
    return sid  # PMID / NCT / core_project_num


# === study-type ordinal (adaption.md #9) =========================================================
# in vitro < mouse/preclinical < cohort < RCT < Phase 1 < Phase 2 < Phase 3. Substring + max() so a
# compound descriptor ("preclinical + cohort") ranks at its most-advanced token, and roman nesting
# ("phase iii" ⊃ "phase ii" ⊃ "phase i") resolves to the highest matched rank.
_STAGE_PATTERNS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("in vitro",), 1),
    (("mouse", "preclinical"), 2),
    (("cohort",), 3),
    (("rct",), 4),
    (("phase 1", "phase i"), 5),
    (("phase 2", "phase ii"), 6),
    (("phase 3", "phase iii"), 7),
)


def _stage_rank(study_type: str | None) -> int:
    """Most-advanced ordinal rank present in a (possibly compound) study_type string; 0 if none."""
    if not study_type:
        return 0
    t = str(study_type).lower()
    rank = 0
    for patterns, r in _STAGE_PATTERNS:
        if any(p in t for p in patterns):
            rank = max(rank, r)
    return rank


def _representative(backing: list[dict]) -> dict | None:
    """The single most-advanced backing evidence row (max stage rank; tie → first, where rows are
    already ordered by source_type, source_id). None if the connection has no backing evidence."""
    if not backing:
        return None
    return max(backing, key=lambda b: _stage_rank(b.get("study_type")))


def _development_stage(backing: list[dict]) -> str:
    """The most-advanced backing `study_type` string (descriptive); "" if no backing carries a
    recognized stage (adaption.md #9 fallback)."""
    rep = _representative(backing)
    if rep is None or _stage_rank(rep.get("study_type")) == 0:
        return ""
    return str(rep["study_type"])


# === DB read (SELECT only; parameter-free → identical on SQLite and Postgres) =====================

_Q_EVIDENCE = (
    "SELECT source_type, source_id, title, year, publication_year, venue, "
    "key_result, evidence_snippet, abstract, doi, study_type, sample_size, access_status "
    "FROM evidence ORDER BY source_type, source_id"
)
_Q_SUBGROUPS = "SELECT name, defining_features, notes FROM subgroups ORDER BY name"
_Q_CONNECTIONS = (
    "SELECT connection_id, mechanism, treatment, evidence_strength "
    "FROM treatment_connections ORDER BY connection_id"
)
_Q_CONNECTION_EVIDENCE = (
    "SELECT ce.connection_id AS connection_id, e.source_type AS source_type, "
    "e.source_id AS source_id, e.study_type AS study_type, e.sample_size AS sample_size, "
    "e.access_status AS access_status "
    "FROM connection_evidence ce JOIN evidence e ON e.evidence_id = ce.evidence_id "
    "ORDER BY ce.connection_id, e.source_type, e.source_id"
)


def _rows(db, sql: str) -> list[dict]:
    """Run a SELECT and return rows as dicts, duck-typing the connection shape (read-only):
      - a raw DBAPI connection (stdlib sqlite3 / psycopg): use a cursor + `description` for keys;
      - an upstream `DbConnection`-style wrapper (has `.execute`+`.fetchall`): use its dict rows."""
    if hasattr(db, "cursor"):
        cur = db.cursor()
        try:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            try:
                cur.close()
            except Exception:
                pass
    # DbConnection-style wrapper: .execute(sql[, params]) -> self ; .fetchall() -> list[dict]
    db.execute(sql)
    return [dict(r) for r in db.fetchall()]


def _open(target: str):
    """Open a connection from a URL/path (the only place a connection is established). Postgres URL →
    lazy `psycopg`; otherwise a stdlib SQLite path (a `file:...?mode=ro` URI is honored for
    read-only). The caller of `task_from_db` owns/closes a passed-in connection; we close only what
    we open here."""
    if target.startswith("postgresql://") or target.startswith("postgres://"):
        import psycopg  # lazy — importing this module must not require/contact psycopg

        return psycopg.connect(target)
    if target.startswith("file:"):
        return sqlite3.connect(target, uri=True)
    return sqlite3.connect(target)


# === the boundary ================================================================================


def task_from_db(conn, run_id, grant_call) -> NIHGrantTask:
    """Read the upstream `neurodiscover` blackboard (READ-ONLY) and assemble the `input_contract`,
    then hand to the UNCHANGED `cua.nih.task.build_task(...)`.

    `conn` is a DB connection, an upstream `DbConnection` wrapper, or a URL/SQLite path (str).
    `run_id` is provenance/labeling ONLY — it never filters a domain read (the domain tables are not
    run-scoped, correction #2). `grant_call` is supplied at our boundary (INT-1, adaption.md #11).

    Mapping (adaption.md #1–#10): corpus = ALL `evidence` rows, all three source_types, as `Paper`s
    with stable ids (`source_type:source_id`, #2), scheme-detected `resolvable_id` (#1), DEMO→real=False
    (#3); `EvidenceAssessment` keyed at CONNECTION granularity (GATE-1) with bucketed grades
    (NULL→minimal) flagged uncalibrated; subgroups (#8) and treatments (#9). `commercial` omitted (#10)."""

    owned = _open(conn) if isinstance(conn, str) else None
    db = owned if owned is not None else conn
    try:
        ev_rows = _rows(db, _Q_EVIDENCE)
        sg_rows = _rows(db, _Q_SUBGROUPS)
        conn_rows = _rows(db, _Q_CONNECTIONS)
        ce_rows = _rows(db, _Q_CONNECTION_EVIDENCE)
    finally:
        if owned is not None:
            owned.close()

    # corpus: every evidence row → Paper (all source_types, #6).
    corpus = SourceSet(sources=[_paper(r) for r in ev_rows])

    # backing evidence per connection (ordered) — for support ids, features, development_stage.
    backing: dict[object, list[dict]] = {}
    for r in ce_rows:
        backing.setdefault(r["connection_id"], []).append(r)

    # EvidenceAssessment: one entry per connection (connection-granularity, GATE-1).
    evidence = EvidenceAssessment()
    treatments: list[Treatment] = []
    for c in conn_rows:
        cid = c["connection_id"]
        b = backing.get(cid, [])
        evidence[f"connection:{cid}"] = _evidence_entry(c, b)
        treatments.append(
            Treatment(
                name=c["treatment"],
                modality="",
                target=c["mechanism"] or "",
                development_stage=_development_stage(b),
            )
        )

    subgroups = [
        Subgroup(name=r["name"], definition=r["defining_features"] or "", rationale=r["notes"] or "")
        for r in sg_rows
    ]

    inputs = _DbInputs(
        grant_call=grant_call,
        corpus=corpus,
        evidence=evidence,
        subgroups=subgroups,
        treatments=treatments,
        commercial=None,  # omit @ v1 (adaption.md #10)
        external_critiques=[],
    )
    return build_task(inputs)  # UNCHANGED


def _paper(row: dict) -> Paper:
    st, sid = row["source_type"], str(row["source_id"])
    year = row.get("year")
    if year is None:
        year = row.get("publication_year")
    key_finding = row.get("key_result") or row.get("evidence_snippet") or row.get("abstract") or ""
    return Paper(
        id=f"{st}:{sid}",  # stable natural key (#2) — NOT evidence_id (autoincrement)
        authors=[],  # absent upstream (#4)
        year=int(year) if year is not None else 0,
        title=row.get("title") or "",
        venue=row.get("venue") or "",
        resolvable_id=resolvable_id(st, sid, row.get("doi")),
        key_finding=key_finding,
        real=not sid.startswith("DEMO-"),  # DEMO ids never resolved (#3)
    )


def _evidence_entry(conn_row: dict, backing: list[dict]) -> EvidenceEntry:
    rep = _representative(backing)
    features = {
        "study_type": (rep.get("study_type") if rep else "") or "",
        "sample_size": rep.get("sample_size") if rep else None,
        "access_status": rep.get("access_status") if rep else None,
        **_UNCALIBRATED,  # REQUIRED — GATE-1 provenance flag
    }
    return EvidenceEntry(
        grade=bucket_grade(conn_row.get("evidence_strength")),  # NULL→minimal; real ordinal Grade
        evidence_features=features,
        support_source_ids=[f'{b["source_type"]}:{b["source_id"]}' for b in backing],
        caveats=[],
    )
