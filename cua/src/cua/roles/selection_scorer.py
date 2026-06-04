"""selection_scorer.py — Selection Scorer (best-of-N ranker) [LLM, light].

Implements: contracts.md §1.5 (SelectionScorer signature), §1.6 (best-of-N), §2.4 (RoleConfig).
Generic role: SelectionScorer — ranks best-of-N candidates on a single dimension, pre-grounding.
NIH binding: the fast F1/F2 picker (design §2 "Best-of-N") — a SEPARATE, cheap judge, kept out of the
             writer's lineage and NOT the Internal Critic (principle 2).
Owner: S4 (builder 1).  Decision: build/decisions/2026-06-02-selection-scorer-prompt.md.

Its only quality bar: the candidate it ranks highest should survive the Critic on the stage's reward
dimension. The DEFAULT is a deterministic offline surrogate of the Sonnet judge (the prompt is in the
decision); since the offline candidates are identical, ranking is a stable no-op (logged in the Trace,
not hidden). The LIVE branch (Sonnet, temp 0.0) ranks real, distinct candidates — design §0's PARALLEL
test-time-compute axis (LIVE-4). It PICKS; it is never the reward/stopping signal (the Critic MEASURES).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ..config import RoleConfig
from ..grounding import level
from ..nih.framework import SONNET_4_6
from ..types import DraftFragment, Level, ScoredFragment


# === live path (the cheap proxy that PICKS) — forced-tool-use schema + prompt =====================
# LIVE-4: when is_live() + a recorder is reachable, real Sonnet ranks the N candidate fragments on the
# stage's reward dimension. It is NOT the Critic (principle 2): a separate, light judge, never the
# reward/stopping signal. The LLM returns a score per candidate INDEX; the code maps it back to the
# ScoredFragments the driver picks the max of (higher = better).


class _CandidateScore(BaseModel):
    """One candidate's score on the dimension (the BASE; higher = better). `index` is the 0-based
    position in the candidate list. Tolerant of a flattened bare number under a 'score'-only object."""

    index: int = Field(description="0-based index of the candidate being scored")
    score: float = Field(description="quality score on the dimension; higher = better")
    rationale: str = Field(default="")


class _RankingOut(BaseModel):
    """The live Selection Scorer's forced-tool output: a score per candidate. Tolerant of the model
    returning the list bare instead of under `rankings`."""

    rankings: list[_CandidateScore] = Field(default_factory=list, description="one entry per candidate")

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, list):
            return {"rankings": data}
        return data


def _rank_prompt(candidates: list[DraftFragment], dimension: str) -> str:
    """Serialize the N candidates (index + their claims on the dimension) for the ranker. Pre-grounding,
    so the Grounder hasn't run — the proxy reads the claim text/cites off each candidate."""
    blocks: list[str] = []
    for i, cand in enumerate(candidates):
        dim_claims = [c for c in cand.claims if c.serves_dimension == dimension]
        lines = [
            f"  - claim[{c.id}]: {c.text} (cites {', '.join(c.reference_ids) or 'none'})"
            for c in dim_claims
        ] or ["  - (no claims on this dimension)"]
        blocks.append(f"CANDIDATE {i}:\n" + "\n".join(lines))
    body = "\n\n".join(blocks) or "(no candidates)"
    return (
        f"Rank these {len(candidates)} candidate draft fragments on dimension {dimension} ONLY "
        "(pre-grounding). Reward grounded, calibrated claims that cover the dimension; penalize overclaim "
        "(asserting above the evidence) and vague phrasing. You are a fast proxy that PICKS — a separate "
        "Critic later MEASURES, and your top pick should survive it.\n\n"
        f"{body}\n\n"
        "Return `rankings`: one {index, score, rationale} per candidate — `index` is the 0-based CANDIDATE "
        "number, `score` is higher=better. Score EVERY candidate.\n"
    )


class SelectionScorer:
    """Selection Scorer (§1.5/§2.4) — Sonnet 4.6 @ temp 0.0 (Sonnet accepts temperature). NOT the
    Critic and NOT a writer: separate lineage, separate context, ranks F1/F2 only, never the
    reward/stopping signal (design §2/§5)."""

    config = RoleConfig(
        model_id=SONNET_4_6,
        temperature=0.0,
        system_prompt_template=(
            "Rank candidate draft fragments on dimension {DIM} only, pre-grounding. You are a fast "
            "proxy that PICKS; a separate Critic later MEASURES — your top pick should survive it. "
            "Reward grounded, calibrated claims that cover {DIM}; penalize overclaim and vague "
            "phrasing. You are not the Critic and do not see the writer's reasoning."
        ),
    )

    def score(
        self, candidates: list[DraftFragment], dimension: str, *, recorder=None, round: int = 0
    ) -> list[ScoredFragment]:
        """§1.5 score. LIVE branch (real Sonnet ranks distinct candidates) when is_live() AND the driver
        threaded a recorder (the §1.5 domain signature — candidates + dimension — is unchanged;
        recorder/round are engine transport). Else the deterministic SURROGATE (the default — offline,
        a stable no-op over identical candidates). Falls back to the surrogate on LiveUnavailable."""
        if recorder is not None and llm.is_live():
            try:
                return self._score_live(candidates, dimension, recorder, round)
            except llm.LiveUnavailable:
                pass
        return self._score_surrogate(candidates, dimension)

    def _score_surrogate(self, candidates: list[DraftFragment], dimension: str) -> list[ScoredFragment]:
        """Deterministic surrogate of the {DIM} judge (decision §'Deterministic v1 surrogate'):
        reward grounded coverage + citations on `dimension`; penalize risky causal claims (L4 with
        thin grounding) as a calibration proxy (the frozen signature passes no evidence, so the proxy
        reads level() off the text). Identical offline candidates tie → the driver keeps the first."""

        out: list[ScoredFragment] = []
        for cand in candidates:
            dim_claims = [c for c in cand.claims if c.serves_dimension == dimension]
            grounded = sum(1 for c in dim_claims if c.evidence_ids)
            refs = len(set(cand.reference_ids()))
            risky = sum(1 for c in dim_claims if level(c.text) is Level.L4 and len(c.evidence_ids) <= 1)
            score = 2.0 * grounded + 1.0 * refs - 3.0 * risky
            out.append(ScoredFragment(fragment=cand, score=score))
        return out

    def _score_live(self, candidates: list[DraftFragment], dimension: str, recorder, round: int) -> list[ScoredFragment]:
        """Real Sonnet ranks the N candidates on `dimension` (forced tool-use → `_RankingOut`);
        complete() records the one TraceEvent. Maps the per-index scores back to ScoredFragments; a
        candidate the model didn't score sinks below the scored ones; if the model returns no usable
        ranking at all, fall back to the deterministic surrogate (the event is already recorded)."""
        out: _RankingOut = llm.complete(
            self.config,
            system=self.config.system_prompt_template.replace("{DIM}", dimension or "the reward dimension"),
            user=_rank_prompt(candidates, dimension),
            schema=_RankingOut,
            trace_role="selection_scorer",
            recorder=recorder,
            round=round,
            input_refs=("candidates", "dimension"),
            # output_ref defaults to "selection_scorer:live" (the live-event convention).
        )
        scores = {r.index: float(r.score) for r in out.rankings if 0 <= r.index < len(candidates)}
        if not scores:  # no usable ranking → deterministic surrogate (one live event already recorded)
            return self._score_surrogate(candidates, dimension)
        # CONTENT-CAP-ALL item E: carry the per-candidate rationale onto the ScoredFragment (observation-only —
        # the driver still picks by `score`; the content-capture sink reads `rationale`).
        rationale = {r.index: (r.rationale or "") for r in out.rankings if 0 <= r.index < len(candidates)}
        floor = min(scores.values()) - 1.0  # an unscored candidate never outranks a scored one
        return [
            ScoredFragment(fragment=cand, score=scores.get(i, floor), rationale=rationale.get(i, ""))
            for i, cand in enumerate(candidates)
        ]
