"""blueprint.py — Conditioner (Blueprint Planner) [LLM, light].

Implements: contracts.md §1.5 (Conditioner signature), §1.2 (Obligation), §2.4 (RoleConfig); emits the
            files/conclusion_update_agent_nih_obligations.md set.
Generic role: Conditioner — compiles a Condition into Obligation[] + Budget.
NIH binding: Blueprint Planner (design §2/§3) — the NIH rubric compiled into typed constraints.
Owner: S4 (builder 1).  Decision: build/decisions/2026-06-02-obligation-specialization.md.

The DEFAULT is near-deterministic (templated, per design §3): the obligation rows, topic specialization,
and per-aim instantiation live in `nih/obligations.py`; the surrogate Conditioner emits them (the rubric
compiled, not graded at the end — principle 1). The LIVE branch (Haiku 4.5, temp 0.1, LIVE-1) lets a real
model TOPIC-SPECIALIZE each obligation's requirement prose — but the CODE owns the obligation STRUCTURE
(ids / dimensions / satisfied_by / status / per-aim id format), which inv-2 binds against, so a live run
stays inv-2-checkable by construction. It specializes the fixed rubric; it never invents its structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ..config import RoleConfig
from ..nih.framework import HAIKU_4_5
from ..nih.obligations import compile_budget, compile_obligations


# === live path (topic-specialize the rubric) — forced-tool-use schema + prompt ===================
# LIVE-1: when is_live() + a recorder is reachable, real Haiku re-writes each obligation's REQUIREMENT to
# the GrantCall topic, kept a concrete checkable predicate (principle 1). The CODE keeps every structural
# field (id / dimension / satisfied_by / status / notes / the F2-x/aim-k id format) — inv-2's ledger
# marking binds by id+dimension, never by the requirement text, so the live prose can't break inv-2.


class _SpecializedObligation(BaseModel):
    """One topic-specialized obligation: the SAME id + dimension, with a concrete, checkable requirement.
    The code matches by `id` and replaces ONLY `requirement` (dimension is context for the model)."""

    id: str = Field(description="the obligation id, unchanged (e.g. 'F1-1', 'F2-1/aim-1', 'X-1')")
    dimension: str = Field(default="", description="F1 / F2 / F3 / X — unchanged")
    requirement: str = Field(default="", description="the topic-specialized, concrete, checkable predicate")


class _ObligationSet(BaseModel):
    """The live Blueprint's forced-tool output: the specialized requirement per obligation id. Tolerant of
    the model returning the list bare instead of under `obligations`."""

    obligations: list[_SpecializedObligation] = Field(default_factory=list, description="one entry per rubric row")

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, list):
            return {"obligations": data}
        return data


def _blueprint_prompt(topic: str, obligations) -> str:
    """Show the fixed rubric skeleton (id + dimension + the checkable core in `notes` + the current
    template) and ask for the topic-specialized, concrete requirement per id. The structure is fixed —
    the model specializes the noun phrase to the topic, never adds/removes/renumbers rows."""
    rows = "\n".join(
        f"- id={o.id} [{o.dimension}] (checkable core: {o.notes})\n    current: {o.requirement}"
        for o in obligations
    )
    return (
        f"TOPIC: {topic}\n\n"
        "Specialize each NIH RubricObligation below to the TOPIC. Keep the SAME id and dimension. Keep the "
        "requirement a CONCRETE, CHECKABLE predicate (countable / presence / structural) — NEVER vague "
        "('is compelling', 'is strong', 'is well-motivated'). Specialize only the noun phrase to the topic; "
        "PRESERVE the checkable core (e.g. '>=1 corpus citation', 'states one explicit testable hypothesis', "
        "'includes a pitfalls/alternatives paragraph', 'defaults to insufficient'). Do NOT add, remove, "
        "renumber, or re-dimension any obligation.\n\n"
        f"RUBRIC OBLIGATIONS ({len(obligations)} rows):\n{rows}\n\n"
        "Return `obligations`: one {id, dimension, requirement} per row above (same ids), each requirement "
        "the topic-specialized, concrete, checkable predicate.\n"
    )


class BlueprintPlanner:
    """Conditioner (§1.5/§2.4): `(Task) -> (list[Obligation], Budget)`. Haiku 4.5 @ temp 0.1 — cheap
    structured instantiation of a known template; low temp keeps the obligation set stable so traces
    and audits stay comparable across runs (design §3). Knob idle in v1."""

    config = RoleConfig(
        model_id=HAIKU_4_5,
        temperature=0.1,
        system_prompt_template=(
            "Compile the NIH Simplified Review Framework into a concrete, checkable RubricObligation "
            "set for this GrantCall: one obligation per rubric row, specialized to the topic but with "
            "the predicate still checkable; per-aim rows instantiated over the planned aims; F3 "
            "defaults to insufficient. Emit obligations + a section/word Budget."
        ),
    )

    def compile(self, task, *, recorder=None, round: int = 0):
        """§1.5 compile. The obligation STRUCTURE + Budget are always code-owned (the templated
        `compile_obligations`/`compile_budget`). LIVE branch (Haiku topic-specializes each requirement
        PROSE) when is_live() AND the Orchestrator threaded a recorder (the §1.5 domain signature — task
        in, (obligations, Budget) out — is unchanged; recorder/round are engine transport). Else the
        templated surrogate (the default — offline, byte-identical). Falls back on LiveUnavailable."""
        obligations = compile_obligations(task)
        budget = compile_budget(task)
        if recorder is not None and llm.is_live():
            try:
                obligations = self._specialize_live(task, obligations, recorder, round)
            except llm.LiveUnavailable:
                pass
        return obligations, budget

    def _specialize_live(self, task, obligations, recorder, round: int):
        """Real Haiku re-writes each obligation's requirement to the topic (forced tool-use →
        `_ObligationSet`); complete() records the one TraceEvent. The code matches the model's output back
        by obligation id and replaces ONLY `requirement` — every structural field (id / dimension /
        satisfied_by / status / notes) is preserved, so inv-2's id-bound ledger marking is untouched. An
        obligation the model didn't return keeps its templated requirement."""
        topic = getattr(task.grant_call, "title", "the proposed work")
        out: _ObligationSet = llm.complete(
            self.config,
            system=self.config.system_prompt_template,
            user=_blueprint_prompt(topic, obligations),
            schema=_ObligationSet,
            trace_role="blueprint",
            recorder=recorder,
            round=round,
            input_refs=("rubric", "grant_call"),
            # output_ref defaults to "blueprint:live" (the live-event convention).
        )
        specialized = {s.id: s.requirement.strip() for s in out.obligations if s.id and (s.requirement or "").strip()}
        for o in obligations:
            if o.id in specialized:
                o.requirement = specialized[o.id]  # PROSE only — structure (id/dimension/satisfied_by/...) preserved
        return obligations
