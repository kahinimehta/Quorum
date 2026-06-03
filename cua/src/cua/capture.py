"""capture.py — Content Capture sink [code, observation-only].

CONTENT-CAP (build/live/CONTENT-CAP_relay.md): a GATED, SEPARATE observability artifact that persists the
intermediate content the Trace (flow/refs) and the Audit (ratification) drop — the best-of-N REJECTED
candidates + their reward scores, the per-round draft evolution, the Reviser hedge diffs, and the full
per-round critique. A viewer (build/viz/render_full2.py) reads `<run>.content.json` to watch content move
and get judged at each step.

OBSERVATION-ONLY (the load-bearing invariant): this is a WRITE-ONLY sink OUT of the trust path. It is
threaded alongside the TraceRecorder ONLY when capture is enabled (`None` when off → zero overhead, zero
behavior change). It NEVER feeds back into generation / grounding / critic decisions; a run with capture
ON and a run with it OFF produce BYTE-IDENTICAL proposal/trace/audit — capture-ON merely ADDS the
content.json. Every `record_*` method serializes to plain primitives EAGERLY (at capture time) so a later
in-place edit (e.g. the Reviser's surgical hedge) can never retro-alter a captured snapshot.

Generic role (CONVENTIONS rule 1): this file names no domain nouns — only the engine's generic content
vocabulary (draft / fragment / claim / candidate / dimension / critique / segment / round). Owner:
CONTENT-CAP (builder 1).
"""

from __future__ import annotations

from .types import Claim, CritiqueReport, Draft, DraftFragment, ScoredFragment


def _claim_dict(c: Claim) -> dict:
    return {
        "id": c.id,
        "text": c.text,
        "serves_dimension": c.serves_dimension,
        "reference_ids": list(c.reference_ids),
        "evidence_ids": list(c.evidence_ids),
    }


def _fragment_dict(f: DraftFragment) -> dict:
    return {
        "stage": f.stage,
        "section": f.section,
        "segment_id": f.segment_id,
        "serves_dimension": f.serves_dimension,
        "text": f.text,
        "claims": [_claim_dict(c) for c in f.claims],
    }


def _draft_dict(draft: Draft) -> dict:
    return {"fragments": [_fragment_dict(f) for f in draft.fragments]}


def _claim_text_by_id(draft: Draft) -> dict[str, str]:
    return {c.id: c.text for f in draft.fragments for c in f.claims}


class ContentCapture:
    """The optional content sink (see module docstring). Construct ONE per run and pass it alongside the
    TraceRecorder; `None` disables capture entirely. A pure accumulator — every method appends a
    primitive snapshot and returns None; nothing here is ever read back into the run."""

    def __init__(self) -> None:
        self.best_of_n: list[dict] = []
        self.rounds: list[dict] = []
        self.reviser_hedges: list[dict] = []
        self.critique: list[dict] = []

    # --- best-of-N (generation.py) -------------------------------------------------------------

    def record_best_of_n(
        self,
        round: int,
        label: str,
        dimension: str,
        candidates: list[DraftFragment],
        ranked: list[ScoredFragment],
        chosen: DraftFragment,
    ) -> None:
        """One best-of-N generation point: the N candidate contents + each candidate's reward score +
        the chosen index + the selection rationale. Today only the winner survives the run, so this is
        the ONLY record of the rejected candidates and why they lost. Scores are matched to candidates by
        identity (robust to the ranker's return order); a candidate the ranker did not score → None. The
        `rationale` is the driver-level selection summary — the per-candidate LLM rationale is not on the
        ScoredFragment contract (the reward score IS the selection signal the driver acts on)."""
        score_by_cand = {id(sf.fragment): sf.score for sf in ranked}
        chosen_index = next((i for i, c in enumerate(candidates) if c is chosen), 0)
        chosen_score = score_by_cand.get(id(chosen))
        self.best_of_n.append(
            {
                "round": round,
                "label": label,
                "dimension": dimension,
                "n": len(candidates),
                "chosen_index": chosen_index,
                "rationale": (
                    f"best-of-{len(candidates)} ranked on reward={dimension or 'n/a'}; "
                    f"chose candidate {chosen_index} (score={chosen_score})"
                ),
                "candidates": [
                    {
                        "index": i,
                        "score": score_by_cand.get(id(c)),
                        "chosen": c is chosen,
                        "fragment": _fragment_dict(c),
                    }
                    for i, c in enumerate(candidates)
                ],
            }
        )

    # --- per-round draft snapshot (orchestrator.py) --------------------------------------------

    def record_round(self, round: int, draft: Draft) -> None:
        """The draft state at this round (round 0 = generated; round n = after the nth revise) — the
        evolution the Proposal/Trace flatten to the final artifact + a flow."""
        self.rounds.append({"round": round, "draft": _draft_dict(draft)})

    # --- per-round critique (orchestrator.py) --------------------------------------------------

    def record_critique(self, round: int, critique: CritiqueReport) -> None:
        """The full per-round critique that drove the §1.11 stopping rule: per-dimension scores +
        justification + repair spans, per-segment (aim) scores, the pass/revise decision, and the
        flagged obligation ids."""
        self.critique.append(
            {
                "round": round,
                "decision": critique.decision,
                "dimension_scores": {
                    dim: {"score": ds.score, "justification": ds.justification, "spans": list(ds.spans)}
                    for dim, ds in critique.dimension_scores.items()
                },
                "segment_scores": {
                    ref: {"dimension": ss.dimension, "score": ss.score, "justification": ss.justification}
                    for ref, ss in critique.segment_scores.items()
                },
                "flagged_obligations": list(critique.flagged_obligations),
            }
        )

    # --- per-round reviser hedge diff (orchestrator.py) ----------------------------------------

    def record_reviser_hedges(self, round: int, prior_draft: Draft, new_draft: Draft) -> None:
        """The exact claim-text changes the Reviser made this round: `[{claim_id, before, after}]` for
        every claim whose text changed (the surgical hedges). Computed from the prior vs the returned
        draft — so the Reviser itself stays untouched (observation-only)."""
        before = _claim_text_by_id(prior_draft)
        after = _claim_text_by_id(new_draft)
        hedges = [
            {"claim_id": cid, "before": before[cid], "after": after[cid]}
            for cid in before
            if cid in after and before[cid] != after[cid]
        ]
        self.reviser_hedges.append({"round": round, "hedges": hedges})

    # --- serialization -------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """The `<run>.content.json` payload — the four captured streams, keyed EXACTLY as the relay
        names them (the viewer reads these keys). `critique` is a per-round list (one entry per round)."""
        return {
            "capture": "content-cap v1 (observation-only; not in the trust path)",
            "best_of_n": self.best_of_n,
            "rounds": self.rounds,
            "reviser_hedges": self.reviser_hedges,
            "critique": self.critique,
        }
