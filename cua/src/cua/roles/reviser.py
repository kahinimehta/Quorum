"""reviser.py — Reviser [LLM, mid].

Implements: contracts.md §1.5 (Reviser signature: `(prior_draft, CritiqueReport, external_critiques,
            flagged_obligations) -> Draft` — a targeted edit, re-routed through Grounding by the
            Orchestrator), §2.4 (RoleConfig: Sonnet 4.6, temp 0.25), §1.11 (the revise leg of the loop).
            Decision: 2026-06-02-critic-scoring-rubric §B (the Critic→Reviser repair protocol).
Generic role: Reviser — applies the critique as a surgical edit and returns the next draft.
NIH binding: Reviser (design §2/§3) — edits must be SURGICAL: preserve what passed, change only what
             was flagged. v1 deterministic surrogate of the Sonnet editor (offline, no network).
Owner: S5 (builder 1).

The Reviser is a DUMB surgical editor by design (principle 2 / §1.5): its frozen signature gives it
neither EvidenceScores nor the GroundingReport, so it cannot know grades or orphans on its own — it
ACTS on the structured directives the (grade-aware) Critic placed in the CritiqueReport spans
(`_repair`). It re-phrases a flagged claim by reversing the writer's §1.12 round-trip (the claim's
stored subject/predicate → `_writing.phrase` at the Critic-supplied permitted rung) and drops
fabricated reference ids — touching only the named claims/ids, nothing that passed.
"""

from __future__ import annotations

import copy

from pydantic import BaseModel, Field, model_validator

from .. import llm
from ..config import RoleConfig
from ..nih.framework import SONNET_4_6
from ..types import Draft, DraftFragment, Level
from ._cites import strip_cites
from ._repair import parse_directives
from ._rigor_booster import boost_rigor
from ._writing import phrase


# === live path (the overclaim resister) — forced-tool-use schema + prompt ========================
# `decisions/2026-06-02-live-reviser-overclaim-finding.md`: the SURROGATE Reviser re-phrases via the
# claim's stored subject/predicate handles — but LIVE writer claims are real Opus prose with NO handles,
# so a live overclaim is detected-not-resisted. The LIVE Reviser (Sonnet) RE-WRITES the flagged claim
# prose down to the permitted rung. The LLM rewrites only the FLAGGED claims; the CODE owns all
# structural surgery (claim ids / evidence_ids / reference_ids / serves_dimension, payload propagation,
# orphan drops) so the re-Ground + re-overclaim-check run clean and the edit is verifiably surgical.


_RUNG_GUIDE = (
    "Rung legend (assertiveness, strongest→weakest): L4 causal ('causes', 'drives', 'restores'); "
    "L3 associative ('is associated with', 'correlates with', 'predicts'); L2 suggestive ('may', "
    "'might', 'could', 'suggests', 'appears to'); L1 exploratory ('we will investigate / examine "
    "whether …', 'to determine whether …'). To hedge to L1, state the OPEN QUESTION / the work to be "
    "done — assert no relationship; remove every L2/L3/L4 cue above the target rung."
)


class _HedgedClaim(BaseModel):
    """One flagged claim re-written down to its permitted rung. `claim_id` binds the rewrite to the exact
    claim the code edits in place (the code owns ids/bindings). Tolerant of an 'id' alias / a flattened
    {claim_id: text} mapping (live-structured-output-robustness; complete()'s retry covers the rest)."""

    claim_id: str = Field(description="the id of the claim to re-write (from the hedge directive)")
    text: str = Field(min_length=1, description="the claim re-written at the permitted rung (lower assertiveness)")

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, dict):
            if "claim_id" not in data and "id" in data:
                data = {**data, "claim_id": data["id"]}
            if "claim_id" not in data and len(data) == 1:  # {"<id>": "<text>"} shorthand
                (k, v), = data.items()
                if isinstance(v, str):
                    return {"claim_id": k, "text": v}
        return data


class _RevisedDraft(BaseModel):
    """The live Reviser's forced-tool output: the re-written text for each FLAGGED claim (hedges). Orphan
    drops are NOT here — they are pure, non-fabricable id removal the code applies from the directives.
    Tolerant of the model returning the list bare instead of under `hedged_claims`."""

    hedged_claims: list[_HedgedClaim] = Field(default_factory=list, description="one entry per flagged (overclaiming) claim")

    @model_validator(mode="before")
    @classmethod
    def _tolerate(cls, data):
        if isinstance(data, list):
            return {"hedged_claims": data}
        return data


def _live_revise_prompt(prior_draft: Draft, hedges: dict[str, str], drops: list[str], critique, external_critiques: list) -> str:
    """Feed the FLAGGED claims (current text + target rung) + the rung legend + the Critic's justifications.
    Only the overclaiming claims are shown — the Reviser is surgical (everything else is preserved by the
    code). Drops are listed for context but the code removes the ids (no fabrication can be introduced)."""
    by_id = {c.id: c for f in prior_draft.fragments for c in f.claims}
    flagged_lines: list[str] = []
    for cid, rung in hedges.items():
        c = by_id.get(cid)
        cur = c.text if c is not None else "(claim not found)"
        flagged_lines.append(f"- claim_id={cid} → rewrite DOWN to rung {rung}\n    current: {cur}")
    flagged_block = "\n".join(flagged_lines) or "(no claims to hedge)"

    just = "; ".join(
        ds.justification for ds in critique.dimension_scores.values() if getattr(ds, "justification", "")
    ) or "(none)"
    ext = external_critiques or []
    ext_block = "\n".join(
        f"- targets {getattr(c, 'target_ref', '?')}: {getattr(c, 'text', '')}" for c in ext
    ) or "(none)"

    return (
        "Apply the critique as a SURGICAL edit. For each FLAGGED claim below, re-write ONLY that claim's "
        "prose down to the named rung — lower the assertiveness to what its evidence permits, preserving "
        "the topic and the meaning. Do NOT touch any claim that is not listed. Do NOT add citations.\n\n"
        f"{_RUNG_GUIDE}\n\n"
        f"FLAGGED CLAIMS (re-write each to its target rung):\n{flagged_block}\n\n"
        f"CRITIC JUSTIFICATIONS:\n{just}\n\n"
        f"EXTERNAL CRITIQUES:\n{ext_block}\n\n"
        f"FABRICATED CITATIONS being dropped by the system (do not re-introduce): {', '.join(drops) or '(none)'}\n\n"
        "Return `hedged_claims`: one {claim_id, text} per FLAGGED claim, where `text` is the re-written "
        "claim at its target rung (cite no ids in the text).\n"
    )


class Reviser:
    """Reviser (§1.5/§2.4): Sonnet 4.6 @ temp 0.25 (Sonnet accepts temperature). Surgical edits only —
    low temp / mid-tier model so working sections are preserved and only flagged content changes."""

    config = RoleConfig(
        model_id=SONNET_4_6,
        temperature=0.25,
        system_prompt_template=(
            "Apply the critique as a SURGICAL edit to the prior draft: hedge each flagged claim to the "
            "rung its evidence permits and drop every fabricated citation, leaving everything that "
            "passed unchanged. Then the draft is re-grounded and re-scored. Change only what was flagged."
        ),
    )

    def __init__(self, corpus=None, topic: str = "", content_capture=None) -> None:
        """`corpus`/`topic` are the F2-booster's binding context (F2-BOOSTER): only the NIH `run_db`
        entrypoint constructs the Reviser WITH a corpus, so the booster's live pre-rewrite step runs there
        and nowhere else. The default `Reviser()` (the fixture oracle + every existing test) carries no
        corpus → the booster is inert → the offline path stays byte-identical. `content_capture`
        (CONTENT-CAP-ALL D) is the observation-only sink the booster records its provenance to — None unless
        capture is on; out of the trust path. The §1.5 `revise()` signature is unchanged (all three are
        construction-time binding data, never engine transport)."""
        self._corpus = corpus
        self._topic = topic or ""
        self._content_capture = content_capture

    def revise(
        self,
        prior_draft: Draft,
        critique,
        external_critiques: list,
        flagged_obligations: list[str],
        *,
        recorder=None,
        round: int = 0,
    ) -> Draft:
        """§1.5 revise. LIVE branch (Sonnet re-writes the flagged overclaims down a rung) when is_live()
        AND the Orchestrator threaded a recorder (the §1.5 domain signature — the four positional args —
        is unchanged; recorder/round are engine transport). Else the deterministic SURROGATE (the default
        — offline, byte-identical). Falls back to the surrogate on LiveUnavailable. Mirrors LIVE-2/3/5."""
        if recorder is not None and llm.is_live():
            try:
                return self._revise_live(prior_draft, critique, external_critiques, flagged_obligations, recorder, round)
            except llm.LiveUnavailable:
                pass
        return self._revise_surrogate(prior_draft, critique, external_critiques, flagged_obligations)

    @staticmethod
    def _directives(critique) -> tuple[dict[str, str], list[str]]:
        """The repair directives the Critic encoded across all dimension_scores' spans (decision §B).
        hedges: {claim_id -> target rung}; drops: [orphan source_id]. CODE-owned (the Critic derives them
        from the GroundingReport + overclaim ladder); the Reviser only consumes them."""
        all_spans: list[str] = []
        for ds in critique.dimension_scores.values():
            all_spans.extend(getattr(ds, "spans", []) or [])
        return parse_directives(all_spans)

    # --- surrogate (default — deterministic offline) -------------------------------------------

    def _revise_surrogate(self, prior_draft: Draft, critique, external_critiques: list, flagged_obligations: list[str]) -> Draft:
        hedges, drops = self._directives(critique)

        # Build the next draft as a deep copy, then mutate only the flagged claims / fabricated ids so
        # the prior draft (referenced in the trace) is untouched and the edit is verifiably surgical.
        fragments = [self._copy_fragment(f) for f in prior_draft.fragments]

        for claim_id, level_label in hedges.items():
            self._hedge_claim(fragments, claim_id, level_label)
        for orphan in drops:
            self._drop_reference(fragments, orphan)

        return Draft(fragments=fragments)

    # --- live (real Sonnet — re-writes live overclaims a rung down) ----------------------------

    def _revise_live(self, prior_draft: Draft, critique, external_critiques: list, flagged_obligations: list[str], recorder, round: int) -> Draft:
        """Real Sonnet re-writes each FLAGGED claim's prose down to its permitted rung (forced tool-use →
        `_RevisedDraft`); complete() records the one TraceEvent. The CODE applies the rewrites surgically
        (only the flagged claims, propagated into the rendered prose + payloads) and owns the orphan drops
        + all id/binding structure — so the re-Ground + re-overclaim-check run clean. Falls back to the
        deterministic re-phrase for any flagged claim the model didn't return (e.g. a surrogate claim that
        still carries subject/predicate handles)."""
        hedges, drops = self._directives(critique)

        # Build the next draft as deep copies UP FRONT so the F2-booster (the live pre-rewrite step) can
        # enrich the aims before the hedge rewrite runs on the same fragments. The prior draft is untouched.
        fragments = [self._copy_fragment(f) for f in prior_draft.fragments]

        # F2-BOOSTER (F2-BOOSTER, binding-side): mine the UN-SELECTED corpus and rewrite each aim's
        # pitfalls_alternatives + expected_outcomes with substantive rigor content BEFORE the hedge. Gated on
        # an injected corpus (only the NIH run_db binding supplies one). BEST-EFFORT: a live failure leaves
        # the aims unchanged and the hedge rewrite below still runs — the booster is an enrichment, never an
        # integrity gate. It writes only the aims' prose fields (no claim/grade/citation) → inv-1/inv-3
        # unaffected; it feeds the Reviser's content, never the Critic (which re-scores independently).
        if self._corpus is not None:
            try:
                boost_rigor(
                    self._corpus, fragments, critique, recorder, round,
                    topic=self._topic, content_capture=self._content_capture,
                )
            except (llm.LiveUnavailable, llm.LiveStructuredOutputError):
                pass

        out: _RevisedDraft = llm.complete(
            self.config,
            system=self.config.system_prompt_template,
            user=_live_revise_prompt(prior_draft, hedges, drops, critique, external_critiques),
            schema=_RevisedDraft,
            trace_role="reviser",
            recorder=recorder,
            round=round,
            input_refs=("draft", "critique"),
            # output_ref defaults to "reviser:live" (the live-event convention).
        )
        new_text_by_id = {h.claim_id: strip_cites(h.text) for h in out.hedged_claims if h.claim_id and h.text}

        for claim_id, level_label in hedges.items():
            new_text = new_text_by_id.get(claim_id)
            if new_text:  # the LLM-rewritten prose at the target rung (live claims have no phrase() handle)
                self._apply_hedge_text(fragments, claim_id, new_text)
            else:  # fallback: deterministic re-phrase (surrogate claims still carry subject/predicate)
                self._hedge_claim(fragments, claim_id, level_label)
        for orphan in drops:
            self._drop_reference(fragments, orphan)

        return Draft(fragments=fragments)

    # --- surgical edits ------------------------------------------------------------------------

    @staticmethod
    def _copy_fragment(f: DraftFragment) -> DraftFragment:
        """A deep copy of a fragment (claims + provided payloads) so edits never alias the prior draft."""
        return DraftFragment(
            stage=f.stage,
            section=f.section,
            text=f.text,
            segment_id=f.segment_id,
            claims=[copy.deepcopy(c) for c in f.claims],
            serves_dimension=f.serves_dimension,
            provides=copy.deepcopy(f.provides),
        )

    def _hedge_claim(self, fragments: list[DraftFragment], claim_id: str, level_label: str) -> None:
        """Re-phrase `claim_id` down to rung `level_label` (the writer's round-trip, reversed) — the
        SURROGATE path. The claim's stored subject/predicate render the new, lower-assertiveness text
        (a live claim carries no handles → no-op here; the live path supplies the LLM rewrite instead),
        applied surgically by `_apply_hedge_text`."""
        target = self._level(level_label)
        claim = next((c for f in fragments for c in f.claims if c.id == claim_id), None)
        if claim is None:
            return
        new_text = phrase(claim.subject, claim.predicate, target) if (claim.subject or claim.predicate) else claim.text
        self._apply_hedge_text(fragments, claim_id, new_text)

    @staticmethod
    def _apply_hedge_text(fragments: list[DraftFragment], claim_id: str, new_text: str) -> None:
        """Set `claim_id`'s text to `new_text` and propagate the change into the rendered prose (the
        fragment text + any provided payload that embedded the old sentence verbatim — e.g. the
        Significance/Innovation skeleton, an aim's hypothesis) so the artifact and the overclaim check
        agree (no hollow pass). Shared by the surrogate (phrase()) and live (LLM rewrite) paths; touches
        only `claim_id` (surgical)."""
        for f in fragments:
            for c in f.claims:
                if c.id != claim_id:
                    continue
                old_text = c.text
                if not new_text or new_text == old_text:
                    return
                c.text = new_text
                for g in fragments:
                    g.text = g.text.replace(old_text, new_text)
                    for payload_list in g.provides.values():
                        for payload in payload_list:
                            _substitute_strings(payload, old_text, new_text)
                return

    @staticmethod
    def _drop_reference(fragments: list[DraftFragment], source_id: str) -> None:
        """Drop a fabricated reference id from every claim that cites it, and scrub it from any provided
        payload's id lists (e.g. an aim's citation_ids) so the dropped fabrication leaves no dangling id."""
        for f in fragments:
            for c in f.claims:
                if source_id in c.reference_ids:
                    c.reference_ids = [r for r in c.reference_ids if r != source_id]
            for payload_list in f.provides.values():
                for payload in payload_list:
                    _scrub_id(payload, source_id)

    @staticmethod
    def _level(label: str) -> Level:
        """Resolve a rung label ('L1'..'L4', by name or value) to a Level; default to the floor (L1)."""
        try:
            return Level[label]
        except KeyError:
            try:
                return Level(label)
            except ValueError:
                return Level.L1


# --- generic structure walkers (binding-agnostic; the Reviser does not import the binding payloads) ---


def _substitute_strings(obj, old: str, new: str) -> None:
    """Replace `old`→`new` in every string field reachable from `obj` (dataclass-like objects, dicts,
    lists). Strings are immutable, so each is reassigned in place on its container."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str):
                obj[k] = v.replace(old, new)
            else:
                _substitute_strings(v, old, new)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = v.replace(old, new)
            else:
                _substitute_strings(v, old, new)
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            if isinstance(v, str):
                setattr(obj, k, v.replace(old, new))
            else:
                _substitute_strings(v, old, new)


def _scrub_id(obj, bad: str) -> None:
    """Remove `bad` from every list-of-ids reachable from `obj` (dataclass-like objects, dicts, lists)."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, list):
                obj[k] = [x for x in v if x != bad]
                for x in obj[k]:
                    _scrub_id(x, bad)
            else:
                _scrub_id(v, bad)
    elif isinstance(obj, list):
        for v in obj:
            _scrub_id(v, bad)
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            if isinstance(v, list):
                setattr(obj, k, [x for x in v if x != bad])
                for x in getattr(obj, k):
                    _scrub_id(x, bad)
            else:
                _scrub_id(v, bad)
