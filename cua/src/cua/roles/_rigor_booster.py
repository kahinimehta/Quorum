"""_rigor_booster.py — F2-booster: in-loop rigor hardening from the UN-SELECTED corpus [role-internal, binding].

Implements: `build/decisions/2026-06-03-f2-booster-design.md` + relay `build/live/F2-BOOSTER_relay.md`.
            The lever `graded2` (`build/decisions/2026-06-03-graded2-cap-vs-base.md`) proved is the REAL
            F2 gate: the BASE (rigor *content*), not the overclaim cap (grades already lift that). Both the
            Critic and the blinded judge flag the same binding gap every round — `pitfalls_alternatives`
            and `expected_outcomes` are emitted as filler, not substance.
Generic role: none — this is the NIH binding's live pre-rewrite step on the Reviser path (no new engine
              seam). Domain nouns are legal here (binding layer, CONVENTIONS rule 1).
NIH binding: the F2-booster. Owner: F2-BOOSTER (builder 1).

What it does (one live call per revise round): contrast the draft's aims against the corpus papers the
Ingestion Layer bounded OUT of the writer's view (the ~340 "road not taken") and rewrite the two weak
fields with substantive content — failure modes + alternative/contingency strategies (→
`pitfalls_alternatives`) and quantitative expected outcomes drawn from the comparison literature (→
`expected_outcomes`), kept HEDGED. It is **test-time compute that consults MORE of the corpus than the
writer ever saw.**

PRINCIPLE COMPLIANCE (the part that must be right):
- FEEDS THE REVISER, NEVER THE CRITIC (principle 2). The booster only writes the aims' prose fields; the
  Critic re-scores `f.text` (= the approach) + the claims INDEPENDENTLY and never reads these fields, so
  the booster's content cannot leak into the critique. The blinded judge DOES read them (it is the arbiter
  of real lift) — so a judge-F2 rise is genuine, not the `graded2` grade-leakage trap.
- DOES NOT RE-GRADE EVIDENCE (principle 6). It touches NO claim, evidence_id, reference_id, or grade — the
  ladder is the skeptic's out-of-loop output and stays fixed mid-loop. ⇒ inv-1 and inv-3 are UNAFFECTED:
  the hypothesis claims (and their GRADE-BIND grades) are byte-untouched, the references deck is unchanged,
  and the overclaim check is identical. Surfaced un-selected ids are validated ∈ corpus (fabrications
  dropped + logged) for provenance only; they are never written into the claim graph.
- LIVE-ONLY / INERT-OFFLINE. The booster runs only inside the Reviser's LIVE path AND only when the binding
  injected a corpus — so the offline fixture oracle (`python -m cua.nih.run`, surrogate Reviser, no corpus)
  never reaches it and stays byte-identical (`9434280f…` at PYTHONHASHSEED 0 AND 7).
"""

from __future__ import annotations

import sys

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ..config import RoleConfig
from ..nih.framework import F2, OPUS_4_8
# Reuse the Ingestion Layer's EXACT finding-similarity so the booster diversifies the un-selected subset on
# the SAME axis the bounded writer view was built on (per the design — corpus Papers carry no per-paper
# study_type, so distinct-finding diversity is the available, consistent axis). Binding-internal reuse.
from ..nih.ingestion import CONTRADICTION_IDS_ATTR, WRITER_VIEW_ATTR, _jaccard, _tokens
from ._cites import coerce_expansion, strip_cites

# Live output budget — the same non-streaming discipline as the writers (`aim_architect._WRITER_MAX_TOKENS`):
# a per-aim {pitfalls, outcomes} rewrite for a few aims fits well under the ceiling.
_BOOSTER_MAX_TOKENS = 16384

# How many UN-SELECTED papers to feed the booster per round (the documented cap — no silent truncation:
# `select_unselected_subset` returns the dropped count and `boost_rigor` logs it). Bounded so the prompt
# stays under the streaming ceiling even at full ~400-paper corpus scale (~340 un-selected).
_SUBSET_CAP = 24

# Two un-selected findings whose token-Jaccard is at/above this are near-duplicates — keep only the
# higher-priority one so the subset spans DISTINCT rigor/failure-mode sources (a touch above the Ingestion
# Layer's 0.5 cluster threshold, so only clearly-redundant findings are skipped).
_DIVERSITY_THRESH = 0.6

# The booster writes the rigor CONTENT the blinded judge reads — judge-F2 is the success metric — so it
# runs at writer-grade quality (Opus 4.8, effort high), mirroring the AimArchitect that OWNS these fields.
_BOOSTER_CONFIG = RoleConfig(
    model_id=OPUS_4_8,
    effort="high",
    system_prompt_template=(
        "You harden one NIH proposal's Specific Aims for the Approach criterion (rigor & feasibility) by "
        "contrasting them against comparable studies the proposal did NOT cite. For each aim, write a "
        "substantive pitfalls/alternatives paragraph (real failure modes other studies hit + concrete "
        "contingency designs) and quantitative expected outcomes (effect sizes / directions grounded in "
        "the comparison literature). Keep assertiveness HEDGED (exploratory/suggestive) — you describe what "
        "comparable work found and what could go wrong; you do NOT assert the proposal's own causal claims, "
        "and you do NOT change its hypotheses or citations."
    ),
)


# === forced-tool-use schema (live-structured-output-robustness — mirrors the writers/Reviser) =========


class _AimRigor(BaseModel):
    """The hardened rigor content for ONE aim. `aim_id` binds it to the aim the code rewrites in place.
    Tolerant (mode="before"): accepts an `id` alias and recovers any `[type:id]` cite the model inlined
    into a prose field into `drawn_from_ids` (cleaning the prose) — the citation survives, the prose stays
    clean, and the code validates each id ∈ corpus before using it for provenance."""

    aim_id: str = Field(description="the id of the aim these fields belong to, e.g. 'aim-1'")
    pitfalls_alternatives: str = Field(
        min_length=1,
        description="substantive failure modes comparable studies hit + concrete alternative/contingency designs",
    )
    expected_outcomes: str = Field(
        min_length=1,
        description="quantitative expected outcomes — values/directions/effect-sizes drawn from the comparison literature",
    )
    drawn_from_ids: list[str] = Field(
        default_factory=list,
        description="the un-selected corpus ids this content draws on (only ids from the provided subset)",
    )

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, dict):
            if "aim_id" not in data and "id" in data:
                data = {**data, "aim_id": data["id"]}
            data = coerce_expansion(
                data, ("pitfalls_alternatives", "expected_outcomes"), id_field="drawn_from_ids"
            )
        return data


class _RigorBoost(BaseModel):
    """The booster's forced-tool output: one `_AimRigor` per aim. Tolerant of the model returning the list
    bare instead of under `aims` (mirrors `_RevisedDraft`/`_AimExpansion` robustness)."""

    aims: list[_AimRigor] = Field(default_factory=list, description="one rigor entry per aim")

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, list):
            return {"aims": data}
        return data


# === un-selected subset selection (pure, deterministic — unit-tested directly) ========================


def _selected_ids(corpus) -> set[str]:
    """The ids the writer's bounded VIEW already showed (so the booster mines only the rest)."""
    return {getattr(r, "id", None) for r in (getattr(corpus, WRITER_VIEW_ATTR, None) or [])}


def select_unselected_subset(corpus, cap: int = _SUBSET_CAP) -> tuple[list, int]:
    """The UN-SELECTED corpus subset to mine = `corpus.sources` − `writer_view`, prioritized by
    `possible_contradiction` (the contrast signal) then diversity-bounded by distinct finding, capped at
    `cap`. Returns `(subset, dropped)` where `dropped` is how many un-selected papers were left out (the
    caller LOGS it — no silent truncation). PURE + deterministic (no clock/RNG); every sort has a stable
    tiebreak.

    GUARDRAIL (inv-1): this only SELECTS which un-selected papers to show the booster — every paper is
    already in `corpus.sources`, so nothing here can introduce an out-of-corpus id."""
    sources = list(getattr(corpus, "sources", []) or [])
    selected = _selected_ids(corpus)
    contra = set(getattr(corpus, CONTRADICTION_IDS_ATTR, None) or ())
    unselected = [p for p in sources if getattr(p, "id", None) not in selected]

    # Priority: contradiction members first, then recency (year desc), then a stable id tiebreak.
    ordered = sorted(
        unselected,
        key=lambda p: (
            0 if str(getattr(p, "id", "")) in contra else 1,
            -(getattr(p, "year", 0) or 0),
            str(getattr(p, "id", "")),
        ),
    )

    # Diversity-bounded greedy: skip a near-duplicate finding (Jaccard ≥ threshold) of an already-picked
    # one so the subset spans DISTINCT sources; if the cap is not reached, fill from the deferred (priority
    # order preserved) so the budget is not wasted.
    picked: list = []
    picked_tokens: list = []
    deferred: list = []
    for p in ordered:
        toks = _tokens(getattr(p, "key_finding", "") or "")
        if len(picked) < cap and not any(_jaccard(toks, t) >= _DIVERSITY_THRESH for t in picked_tokens):
            picked.append(p)
            picked_tokens.append(toks)
        else:
            deferred.append(p)
    for p in deferred:
        if len(picked) >= cap:
            break
        picked.append(p)

    dropped = len(unselected) - len(picked)
    return picked, dropped


# === prompt + draft helpers ===========================================================================


def _aim_entries(fragments) -> list:
    """The aim objects to harden (one per aim DraftFragment), paired with their fragment. Reads the
    `provides['aims']` payloads the AimArchitect emitted — NOT the claims (the booster never touches a
    claim). An aim missing its prose fields is still returned (the booster fills them)."""
    out = []
    for f in fragments:
        for aim in f.provides.get("aims", []) or []:
            out.append(aim)
    return out


def _f2_feedback(critique) -> str:
    """The Critic's F2 (Approach) justification — the booster's STEERING input (reading the Critic's OUTPUT
    is the normal revise flow; the booster's own content never flows back into the critique)."""
    ds = getattr(critique, "dimension_scores", {}).get(F2) if critique is not None else None
    return (getattr(ds, "justification", "") or "").strip() if ds is not None else ""


def _unselected_block(subset) -> str:
    """Serialize the un-selected subset for the prompt: `[id] (year) title — key_finding`. These are the
    'road not taken' papers the writer never saw; the booster mines their rigor/failure-modes/effect-sizes."""
    rows = [
        f"[{getattr(p, 'id', '')}] ({getattr(p, 'year', '') or '?'}) "
        f"{getattr(p, 'title', '') or ''} — {getattr(p, 'key_finding', '') or ''}"
        for p in subset
    ]
    return "\n".join(rows) or "(none)"


def _aims_block(aims) -> str:
    """Serialize each aim's current state for the prompt: hypothesis + approach + the CURRENT (filler)
    pitfalls/outcomes the booster must replace with substance."""
    blocks = []
    for a in aims:
        blocks.append(
            f"- aim_id={getattr(a, 'id', 'aim')}\n"
            f"    hypothesis: {getattr(a, 'hypothesis', '') or ''}\n"
            f"    approach: {getattr(a, 'approach', '') or ''}\n"
            f"    current pitfalls_alternatives: {getattr(a, 'pitfalls_alternatives', '') or ''}\n"
            f"    current expected_outcomes: {getattr(a, 'expected_outcomes', '') or ''}"
        )
    return "\n".join(blocks) or "(no aims)"


def _booster_prompt(topic: str, aims, subset, f2_feedback: str) -> str:
    return (
        f"TOPIC: {topic or 'the proposed work'}\n\n"
        f"AIMS TO HARDEN (rewrite each aim's pitfalls_alternatives + expected_outcomes with SUBSTANCE):\n"
        f"{_aims_block(aims)}\n\n"
        f"CRITIC'S APPROACH (F2) FEEDBACK to address:\n{f2_feedback or '(none)'}\n\n"
        f"COMPARABLE STUDIES THE PROPOSAL DID NOT CITE (the 'road not taken' — mine these for rigor):\n"
        f"{_unselected_block(subset)}\n\n"
        "TASK — for EACH aim above, return:\n"
        "- pitfalls_alternatives: the concrete failure modes comparable studies hit (e.g. underpowered "
        "cohorts, poor model validity, confounds, attrition) AND specific alternative/contingency designs "
        "to mitigate them. Be specific to THIS aim's hypothesis + approach.\n"
        "- expected_outcomes: quantitative expected outcomes tied to the hypothesis — values, directions, "
        "and effect-size ranges grounded in what the comparable studies reported.\n"
        "- drawn_from_ids: the ids (from the comparable-studies list above ONLY) your content draws on.\n\n"
        "RULES:\n"
        "- Keep assertiveness HEDGED/exploratory — describe what comparable work found and what could go "
        "wrong; do NOT assert the proposal's own causal/associative claims.\n"
        "- Do NOT change any hypothesis, approach, or citation. You write ONLY the two fields above.\n"
        "- drawn_from_ids must be ids from the comparable-studies list; any other id is dropped.\n"
    )


# === apply + the live step ============================================================================


def _log(message: str) -> None:
    """One STDERR line (live-only path) — so the cap + what was dropped + which un-selected papers each aim
    drew on are VISIBLE (no silent truncation). STDERR-only ⇒ the offline byte oracle's stdout is untouched."""
    print(message, file=sys.stderr, flush=True)


def _suffix_map(corpus_ids: set[str]) -> dict[str, str]:
    """Map each corpus id's `source_id` (the part after the FIRST `:`) → the FULL `source_type:source_id`,
    EXCLUDING any `source_id` shared by >1 corpus id (ambiguous → never guess). The recovery key for a
    bare / mis-prefixed `drawn_from` token (BOOSTER-POLISH item B)."""
    by_suffix: dict[str, str] = {}
    ambiguous: set[str] = set()
    for cid in corpus_ids:
        suffix = cid.split(":", 1)[1] if ":" in cid else cid
        if suffix in by_suffix and by_suffix[suffix] != cid:
            ambiguous.add(suffix)
        else:
            by_suffix[suffix] = cid
    for s in ambiguous:
        by_suffix.pop(s, None)
    return by_suffix


def _normalize_drawn_from(ids: list[str], corpus_ids: set[str]) -> tuple[list[str], list[str]]:
    """Normalize booster-returned `drawn_from` tokens to canonical corpus ids (BOOSTER-POLISH item B).
    PROVENANCE ONLY — these never become a claim/citation/grade, so inv-1/inv-3 are unaffected; this just
    makes the captured road-not-taken → aim links complete. A full corpus id is kept; otherwise the leading
    `type:` is stripped to the candidate `source_id` and looked up — a UNIQUE match recovers the FULL correct
    corpus id, zero/ambiguous is dropped (the conservative default). Returns (valid, dropped), de-duped."""
    suffix_map = _suffix_map(corpus_ids)
    valid: list[str] = []
    dropped: list[str] = []
    for tok in ids:
        if tok in corpus_ids:  # already canonical
            valid.append(tok)
            continue
        candidate = tok.split(":", 1)[1] if ":" in tok else tok  # strip any leading `type:`
        recovered = suffix_map.get(candidate)
        if recovered is not None:  # unique source_id match → the canonical corpus id
            valid.append(recovered)
        else:  # unknown / ambiguous → drop (never guess)
            dropped.append(tok)
    return list(dict.fromkeys(valid)), list(dict.fromkeys(dropped))


def _apply(aims, rigor_by_aim, corpus_ids: set[str]) -> list[dict]:
    """Write the hardened content into the matching aims IN PLACE — the two prose fields ONLY (no claim,
    no grade, no citation graph). Normalizes each surfaced id to its canonical corpus id (recovering bare /
    mis-prefixed provenance; item B), DROPPING the unrecoverable. Keeps the original field if a rewrite is
    empty (so the §2.1 `_AimEnvelope` min_length still holds). Returns the per-aim provenance (validated
    drawn-from ids + dropped fabrications) for the log + the handoff/tests."""
    prov: list[dict] = []
    for aim in aims:
        r = rigor_by_aim.get(getattr(aim, "id", None))
        if r is None:
            continue
        new_pit = strip_cites(r.pitfalls_alternatives) or getattr(aim, "pitfalls_alternatives", "")
        new_out = strip_cites(r.expected_outcomes) or getattr(aim, "expected_outcomes", "")
        valid, dropped = _normalize_drawn_from(list(dict.fromkeys(r.drawn_from_ids)), corpus_ids)
        if new_pit:
            aim.pitfalls_alternatives = new_pit
        if new_out:
            aim.expected_outcomes = new_out
        prov.append({"aim_id": getattr(aim, "id", ""), "drawn_from": valid, "dropped_non_corpus": dropped})
    return prov


def boost_rigor(corpus, fragments, critique, recorder, round: int, *, topic: str = "", content_capture=None) -> list[dict]:
    """The live F2-booster step (one Opus call): mine the un-selected corpus and rewrite each aim's
    pitfalls/outcomes IN PLACE on `fragments`. Returns the per-aim provenance (empty when there is nothing
    to do). The caller (the Reviser) runs this inside its LIVE branch and treats any live failure as a
    best-effort no-op. `complete()` records the one TraceEvent (role `reviser_booster`); the optional
    `content_capture` sink (CONTENT-CAP-ALL D — None unless capture is on, out of the trust path) records the
    subset stats + per-aim provenance for `<run>.content.json`."""
    aims = _aim_entries(fragments)
    subset, dropped = select_unselected_subset(corpus, _SUBSET_CAP)
    if not aims or not subset:
        return []

    _log(
        f"[booster] round={round} aims={len(aims)} un-selected→subset={len(subset)} "
        f"(cap={_SUBSET_CAP}, dropped={dropped})"
    )
    out: _RigorBoost = llm.complete(
        _BOOSTER_CONFIG,
        system=_BOOSTER_CONFIG.system_prompt_template,
        user=_booster_prompt(topic, aims, subset, _f2_feedback(critique)),
        schema=_RigorBoost,
        trace_role="reviser_booster",
        recorder=recorder,
        round=round,
        input_refs=("aims", "critique", "unselected_corpus"),
        max_tokens=_BOOSTER_MAX_TOKENS,
        # output_ref defaults to "reviser_booster:live" (the live-event convention).
    )
    rigor_by_aim = {r.aim_id: r for r in out.aims if r.aim_id}
    prov = _apply(aims, rigor_by_aim, set(corpus.ids()) if hasattr(corpus, "ids") else set())
    for p in prov:
        note = f" (dropped {len(p['dropped_non_corpus'])} non-corpus: {p['dropped_non_corpus']})" if p["dropped_non_corpus"] else ""
        _log(f"[booster] {p['aim_id']} drew on {len(p['drawn_from'])} un-selected paper(s): {p['drawn_from']}{note}")
    # CONTENT-CAP-ALL (D, observation-only): the road-not-taken → aim linkage + subset stats. None-guarded.
    if content_capture is not None:
        content_capture.record_booster(round, {
            "unselected_total": len(subset) + dropped,
            "subset_size": len(subset),
            "cap": _SUBSET_CAP,
            "dropped": dropped,
            "aims": prov,
        })
    return prov
