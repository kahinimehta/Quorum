"""obligations.py — NIH binding: the RubricObligation loader + ledger marking.

Implements: contracts.md §1.2 (Obligation), §2.1 (RubricObligation), §3 inv-2; the
            `files/conclusion_update_agent_nih_obligations.md` set; design §1 principle 1.
Generic role: compiles a Condition into Obligation[] + Budget (the Conditioner's work) and marks the
              ledger from the written draft (the writer's satisfied_by / evidence_ids / status).
NIH binding: the NIH Simplified Review Framework rows (F1/F2/F3 + cross-cutting X-1/X-2).
Owner: S4 (builder 1).  Decisions: build/decisions/2026-06-02-obligation-specialization.md
       (topic specialization gap 2a + inv-2 evidence binding, the S2-gate finding 0).

Domain nouns are legal here (binding). The rows below mirror the nih_obligations.md template; the
Blueprint specializes each `requirement` to the topic at plan time while keeping the predicate checkable.
"""

from __future__ import annotations

from collections import namedtuple

from ..grounding import build_overclaim_check
from ..types import Budget, Obligation, Status
from .framework import F1, F2, F3

# One structured row per nih_obligations.md row. `template` carries {topic} (and {aim} for per-aim
# rows); `check` mirrors the [hard structure · soft check] split. X-1/X-2 are the cross-cutting rows
# enforced by the hard invariants (dimension "X" — not a scored/gated axis).
_Row = namedtuple("_Row", "id dimension per_aim check template")

X = "X"  # cross-cutting (inv-1 / inv-3) — not gated by the stopping rule

RUBRIC: list[_Row] = [
    _Row("F1-1", F1, False, "critic+code(>=1 evidence_id)",
         "Significance names the specific barrier to progress in {topic} and states why resolving it "
         "matters to the field, with >=1 corpus citation."),
    _Row("F1-2", F1, False, "code+critic",
         "A single central hypothesis for {topic} is stated explicitly and follows from the named gap."),
    _Row("F1-3", F1, False, "critic",
         "Innovation names the specific departure from current concepts/methods/practice in {topic} "
         "(not a generic 'novel')."),
    _Row("F2-1", F2, True, "code+critic",
         "{aim} states one explicit, testable hypothesis or objective for {topic}."),
    _Row("F2-2", F2, True, "critic",
         "{aim}'s approach names the key methods/design at enough specificity to judge rigor "
         "(not goals alone)."),
    _Row("F2-3", F2, True, "code",
         "{aim} includes a pitfalls / alternative-strategies paragraph."),
    _Row("F2-4", F2, True, "code+critic",
         "{aim} states expected outcomes tied to its hypothesis."),
    _Row("F3-1", F3, True, "code",
         "{aim} surfaces the expertise and resources its approach assumes, for "
         "investigator/environment confirmation."),
    _Row("F3-2", F3, False, "code/policy",
         "The agent does not assert F3 sufficiency for {topic}; self_score defaults to insufficient "
         "pending external confirmation."),
    _Row("X-1", X, False, "code/inv-1",
         "Every empirical claim in {topic} carries an evidence_id and every citation is in corpus (inv-1)."),
    _Row("X-2", X, False, "code/inv-3",
         "No claim's assertiveness exceeds the rung its evidence grade permits (inv-3)."),
]

# Role-claim ids the Synthesizer emits for the flat F1 rows (the writer's satisfied_by targets).
_F1_ROLE_CLAIM = {"F1-1": "significance", "F1-2": "central-hypothesis", "F1-3": "innovation"}

# Planned aim count by grant mechanism (decision §A). NIH norms: R01 ~3 aims, R21 ~2 (exploratory).
_AIM_COUNT = {"R01": 3, "R21": 2}
_DEFAULT_AIM_COUNT = 2


# === plan-time compile (the Conditioner's work) ==================================================


def aim_count(mechanism: str) -> int:
    """Planned number of aims for a grant mechanism (decision §A) — conditions the writer."""
    return _AIM_COUNT.get(mechanism, _DEFAULT_AIM_COUNT)


def planned_aim_ids_for_task(task) -> list[str]:
    """The aim slots the Blueprint plans for `task` (e.g. ['aim-1','aim-2','aim-3'])."""
    n = aim_count(getattr(task.grant_call, "mechanism", ""))
    return [f"aim-{i + 1}" for i in range(n)]


def planned_aim_ids(obligations: list[Obligation]) -> list[str]:
    """Recover the planned aim ids from a compiled obligation set (the per-aim 'F2-1/aim-k' ids).
    The Synthesizer reads this so the rubric drives how many aim_stubs it emits (principle 1)."""
    out: list[str] = []
    for o in obligations:
        if "/" in o.id:
            aim_id = o.id.split("/", 1)[1]
            if aim_id not in out:
                out.append(aim_id)
    return out


def specialize(template: str, topic: str, aim: str | None = None) -> str:
    """Bind the topic (and aim label) into a requirement template, preserving the checkable predicate
    (gap 2a). Only the noun phrase is specialized; the countable/presence/structural core is untouched."""
    return template.format(topic=topic, aim=aim or "each aim")


def compile_obligations(task) -> list[Obligation]:
    """Emit the full nih_obligations.md set, topic-specialized, with per-aim rows instantiated over the
    planned aim slots (decision §A/§B). Status starts UNSATISFIED; the writer fills the ledger later."""
    topic = getattr(task.grant_call, "title", "the proposed work")
    aim_ids = planned_aim_ids_for_task(task)
    obligations: list[Obligation] = []
    for row in RUBRIC:
        if row.per_aim:
            for aim_id in aim_ids:
                aim_label = aim_id.replace("aim-", "Aim ")
                obligations.append(
                    Obligation(
                        id=f"{row.id}/{aim_id}",
                        dimension=row.dimension,
                        requirement=specialize(row.template, topic, aim_label),
                        satisfied_by=[aim_id],
                        status=Status.UNSATISFIED,
                        notes=row.check,
                    )
                )
        else:
            obligations.append(
                Obligation(
                    id=row.id,
                    dimension=row.dimension,
                    requirement=specialize(row.template, topic),
                    status=Status.UNSATISFIED,
                    notes=row.check,
                )
            )
    return obligations


def compile_budget(task) -> Budget:
    """Coarse section/word Budget from the section specs (contracts.md §1.1). v1 mirrors S2; the
    Blueprint refines word limits from the GrantCall page limits later (not asserted)."""
    sections = {s.name: s.target_words for s in task.sections}
    return Budget(sections=sections, total_word_limit=sum(sections.values()))


# === assembly-time ledger marking (the writer's satisfied_by / evidence_ids / status) ============


def _aim_evidence(draft) -> dict[str, list[str]]:
    """Map aim segment id -> the evidence_ids of the claims written for that aim (from the draft
    fragments the AimArchitect emits with segment_id == aim id)."""
    out: dict[str, list[str]] = {}
    for f in draft.fragments:
        if f.segment_id:
            bucket = out.setdefault(f.segment_id, [])
            for c in f.claims:
                bucket.extend(c.evidence_ids)
    return out


def mark_ledger(obligations: list[Obligation], draft, grounding_report, evidence_scores) -> None:
    """Mark the obligation ledger from the written draft (decision §C; design principle 1).

    inv-2 invariant: an obligation is `satisfied` ONLY when its requirement is fulfilled AND the
    fulfilling segment is evidence-grounded (>=1 evidence_id) — `evidence_ids` are bound from the
    backing claims. F3 is never asserted (at_risk/insufficient). X-1/X-2 are decided by the code
    invariants. A final guard downgrades any `satisfied` row that ended up unevidenced (belt-and-braces
    so inv-2 can never fail on a real Audit)."""

    claims = draft.claims()
    by_id = {c.id: c for c in claims}
    aim_ev = _aim_evidence(draft)

    overclaimed = any(not r.ok for r in build_overclaim_check(claims, evidence_scores))
    orphans = set(grounding_report.orphan_ids)
    in_source_refs = [r for r in draft.reference_ids() if r not in orphans]
    all_evidence = sorted({eid for c in claims for eid in c.evidence_ids})

    for o in obligations:
        # F3 — the agent writes from scientific evidence, not investigator/environment data: it
        # surfaces what F3 requires and defaults to insufficient (never asserts sufficiency). Not
        # `satisfied`, so inv-2-clean by construction.
        if o.dimension == F3:
            o.status = Status.AT_RISK
            o.self_score = "insufficient"
            o.evidence_ids = []
            o.notes = "F3 not asserted; insufficient pending investigator/environment confirmation"
            continue

        if o.id == "X-1":  # citation integrity — decided by inv-1 (code)
            if grounding_report.all_in_source_set:
                o.status = Status.SATISFIED
                o.evidence_ids = list(in_source_refs)
                o.satisfied_by = ["references"]
            else:
                o.status = Status.UNSATISFIED
                o.evidence_ids = []
            o.notes = "decided by inv-1 (citation integrity, code)"
            continue

        if o.id == "X-2":  # no overclaim — decided by inv-3 (code)
            if not overclaimed:
                o.status = Status.SATISFIED
                o.evidence_ids = list(all_evidence)
                o.satisfied_by = ["all claims"]
            else:
                o.status = Status.AT_RISK
                o.evidence_ids = []
            o.notes = "decided by inv-3 (overclaim ladder, code)"
            continue

        if "/" in o.id:  # per-aim F2 row — satisfied by the aim segment, evidenced by its claims
            aim_id = o.id.split("/", 1)[1]
            ev = sorted(set(aim_ev.get(aim_id, [])))
            o.satisfied_by = [aim_id]
            o.evidence_ids = ev
            o.self_score = 6 if ev else None
            o.status = Status.SATISFIED if ev else Status.AT_RISK
            continue

        # flat F1 rows — bound from the writer's role claim (significance / central / innovation)
        role_claim_id = _F1_ROLE_CLAIM.get(o.id)
        claim = by_id.get(role_claim_id) if role_claim_id else None
        ev = sorted(set(claim.evidence_ids)) if claim else []
        o.satisfied_by = [role_claim_id] if role_claim_id else []
        o.evidence_ids = ev
        o.self_score = 6 if ev else None
        o.status = Status.SATISFIED if ev else Status.AT_RISK

    # inv-2 guard — no `satisfied` obligation may carry an empty evidence_ids list.
    for o in obligations:
        if o.status == Status.SATISFIED and not o.evidence_ids:
            o.status = Status.AT_RISK
            o.notes = (o.notes + " | " if o.notes else "") + "downgraded: no evidence_id (inv-2 guard)"
