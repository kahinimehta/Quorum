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

from dataclasses import asdict, is_dataclass

from .types import Claim, CritiqueReport, Draft, DraftFragment, ScoredFragment


def _claim_dict(c: Claim) -> dict:
    return {
        "id": c.id,
        "text": c.text,
        "serves_dimension": c.serves_dimension,
        "reference_ids": list(c.reference_ids),
        "evidence_ids": list(c.evidence_ids),
    }


def _serialize_payload(p):
    """Serialize ONE `provides` payload to a plain, JSON-safe value EAGERLY (CONTENT-CAP-ALL item A). The
    payloads are the roles' structured outputs (the Synthesizer's skeleton, the AimArchitect's + booster's
    full aims) — carried through GENERICALLY (capture.py names no domain nouns, CONVENTIONS rule 1): a
    pydantic `model_dump()`, else a dataclass `asdict` (deep copy → no aliasing, so a later in-place edit
    like the booster's per-round aim rewrite can't retro-alter this snapshot), else a shallow dict of a
    plain object's attrs, else the value as-is (dict/primitive)."""
    dump = getattr(p, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:
            pass
    if is_dataclass(p) and not isinstance(p, type):
        return asdict(p)  # deep copy — eager, no aliasing
    if isinstance(p, dict):
        return dict(p)
    if hasattr(p, "__dict__"):
        return dict(vars(p))
    return p


def _provides_dict(f: DraftFragment) -> dict:
    """The fragment's `provides` (item collections a downstream stage maps over) serialized generically —
    where the Synthesizer's skeleton + the AimArchitect's/booster's full aims live (the biggest blind
    spot). EAGER per-payload serialization so each round/candidate snapshot is independent."""
    return {ref: [_serialize_payload(p) for p in (payloads or [])] for ref, payloads in f.provides.items()}


def _fragment_dict(f: DraftFragment) -> dict:
    return {
        "stage": f.stage,
        "section": f.section,
        "segment_id": f.segment_id,
        "serves_dimension": f.serves_dimension,
        "text": f.text,
        "claims": [_claim_dict(c) for c in f.claims],
        "provides": _provides_dict(f),  # CONTENT-CAP-ALL item A — the writers'/booster's structured output
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
        # CONTENT-CAP-ALL: the three previously-unhooked inter-role messages.
        self.conditioner: dict | None = None  # B — the obligation contract (round 0, once)
        self.grounding: list[dict] = []        # C — per-round GroundingReport (inv-1 enforcement, live)
        self.booster: list[dict] = []          # D — per-round F2-booster provenance (road-not-taken → aim)

    # --- best-of-N (generation.py) -------------------------------------------------------------

    def record_best_of_n(
        self,
        round: int,
        label: str,
        dimension: str,
        candidates: list[DraftFragment],
        ranked: list[ScoredFragment],
        chosen: DraftFragment,
        drops: list[dict] | None = None,
        requested: int | None = None,
        attempts: int | None = None,
    ) -> None:
        """One best-of-N generation point: the M SUCCESSFUL candidate contents + each candidate's reward
        score + the chosen index + the selection rationale, PLUS the BON-RESILIENCE top-up accounting —
        `requested` (N), `attempts`, `succeeded` (M), `dropped` (J = attempts − M), and `dropped_attempts`
        (`[{attempt, error}]` for each retry-exhausted structured-output failure that was topped up). The
        successes are the run's surviving candidates (`best` is chosen among them); the dropped attempts are
        the only record of what failed and why. Scores are matched to candidates by identity (robust to the
        ranker's return order); a candidate the ranker did not score → None. `n` is the kept (success) count
        — equal to `requested` whenever the cap was not hit. The `rationale` is the driver-level selection
        summary — the per-candidate LLM rationale is not on the ScoredFragment contract."""
        score_by_cand = {id(sf.fragment): sf.score for sf in ranked}
        # CONTENT-CAP-ALL item E: the ranker's per-candidate rationale (additive on ScoredFragment; '' offline).
        rationale_by_cand = {id(sf.fragment): getattr(sf, "rationale", "") for sf in ranked}
        drops = drops or []
        succeeded = len(candidates)
        requested = succeeded if requested is None else requested
        attempts = (succeeded + len(drops)) if attempts is None else attempts
        chosen_index = next((p for p, c in enumerate(candidates) if c is chosen), 0)
        chosen_score = score_by_cand.get(id(chosen))

        self.best_of_n.append(
            {
                "round": round,
                "label": label,
                "dimension": dimension,
                "n": succeeded,           # kept (== requested unless the top-up cap was reached)
                "requested": requested,
                "attempts": attempts,
                "succeeded": succeeded,
                "dropped": len(drops),
                "chosen_index": chosen_index,
                "rationale": (
                    f"best-of-{requested} ranked on reward={dimension or 'n/a'}; "
                    f"chose candidate {chosen_index} (score={chosen_score})"
                    + (
                        f"; {len(drops)} dropped, topped-up to {succeeded}/{requested}"
                        if drops else ""
                    )
                ),
                "candidates": [
                    {
                        "index": p,
                        "score": score_by_cand.get(id(c)),
                        "rationale": rationale_by_cand.get(id(c), ""),  # item E — the ranker's per-candidate note
                        "chosen": c is chosen,
                        "fragment": _fragment_dict(c),
                    }
                    for p, c in enumerate(candidates)
                ],
                "dropped_attempts": [{"attempt": d["attempt"], "error": d["error"]} for d in drops],
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

    # --- conditioner / grounding / booster (CONTENT-CAP-ALL B/C/D) -----------------------------

    def record_conditioner(self, obligations: list, budget=None) -> None:
        """B — the obligation contract the whole proposal is built against (round 0, once): per obligation
        `{id, dimension, requirement}` + the compiled Budget (if any). The planner's output the Critic later
        scores against — captured here as the opening artifact of the subagent conversation."""
        self.conditioner = {
            "obligations": [
                {"id": getattr(o, "id", ""), "dimension": getattr(o, "dimension", ""), "requirement": getattr(o, "requirement", "")}
                for o in obligations
            ],
            "budget": _serialize_payload(budget) if budget is not None else None,
        }

    def record_grounding(self, round: int, report) -> None:
        """C — the GroundingReport for this round: `{round, n_references, all_in_source_set, orphan_ids}`
        (+ `resolve_rate` when present). The per-round record of inv-1 enforcement (citation integrity), live."""
        entry = {
            "round": round,
            "n_references": getattr(report, "n_references", None),
            "all_in_source_set": getattr(report, "all_in_source_set", None),
            "orphan_ids": list(getattr(report, "orphan_ids", []) or []),
        }
        resolve_rate = getattr(report, "resolve_rate", None)
        if resolve_rate is not None:
            entry["resolve_rate"] = resolve_rate
        self.grounding.append(entry)

    def record_booster(self, round: int, provenance: dict) -> None:
        """D — the F2-booster's per-round message: the subset stats (un-selected total, cap, dropped) + the
        per-aim provenance (`{aim_id, drawn_from, dropped_non_corpus}`) — the road-not-taken → aim linkage.
        `provenance` is already plain dicts (eager, from the booster); stored verbatim under `round`."""
        self.booster.append({"round": round, **provenance})

    # --- serialization -------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """The `<run>.content.json` payload — the captured streams, keyed EXACTLY as the relay names them
        (the viewer reads these keys). `critique`/`rounds`/`grounding`/`booster` are per-round lists;
        `conditioner` is a single round-0 entry (or None if unrecorded)."""
        return {
            "capture": "content-cap v2 (CONTENT-CAP-ALL; observation-only; not in the trust path)",
            "best_of_n": self.best_of_n,
            "rounds": self.rounds,
            "reviser_hedges": self.reviser_hedges,
            "critique": self.critique,
            "conditioner": self.conditioner,
            "grounding": self.grounding,
            "booster": self.booster,
        }
