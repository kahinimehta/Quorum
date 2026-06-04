"""_cites.py — recover inline `[type:id]` citations when a live writer flattens a nested field [role-internal].

Non-deterministically the forced-tool-use model collapses a nested `{text, cited_corpus_ids}` claim/stub
into a bare STRING, inlining the cite as `[type:id]` (the corpus-list format the prompt shows). Strict
pydantic would reject the string AFTER the paid Opus call (hard-fail, no artifact). These helpers back the
live schemas' `model_validator(mode="before")` so the object coerces from the string (or recovers cites
inlined into an object's prose) — the run completes live and the citation survives → the Grounder still
checks it (inv-1). Decision: build/decisions/2026-06-02-live-structured-output-robustness.md.

Generic string processing — no model, no network. These touch ONLY live schema parsing; the surrogate path
never instantiates these schemas, so offline output is unchanged. Owner: LIVE-2/3 robustness (builder 1).
"""

from __future__ import annotations

import re

# Corpus ids are `f"{source_type}:{source_id}"` (lowercase type), shown in the prompt as `[type:id]`.
_CITE = re.compile(r"\[([a-z]+:[^\]]+)\]")
_CITE_SPAN = re.compile(r"\s*\[[a-z]+:[^\]]+\]")


def extract_cites(text) -> list[str]:
    """The `type:id` ids inlined as `[type:id]` in `text`, de-duplicated, order-preserved."""
    return list(dict.fromkeys(_CITE.findall(text))) if isinstance(text, str) else []


def strip_cites(text):
    """`text` with the `[type:id]` cite brackets removed, so the visible prose stays clean."""
    return _CITE_SPAN.sub("", text).strip() if isinstance(text, str) else text


def coerce_cited(data, text_field: str):
    """`mode="before"` coercion for a `{<text_field>, cited_corpus_ids}` object (e.g. _CitedClaim/_AimStub).

    - a bare STRING → `{<text_field>: <cleaned>, cited_corpus_ids: <recovered>}` (fallback to the raw
      string if stripping the cites would empty it);
    - an OBJECT whose `<text_field>` inlines `[type:id]` cites → recover them into `cited_corpus_ids`
      (merged, never dropping existing ids) and clean the text;
    - an already-clean object → unchanged.
    """
    if isinstance(data, str):
        return {text_field: strip_cites(data) or data, "cited_corpus_ids": extract_cites(data)}
    if isinstance(data, dict):
        text = data.get(text_field)
        inline = extract_cites(text)
        if inline:
            merged = list(dict.fromkeys([*(data.get("cited_corpus_ids") or []), *inline]))
            return {**data, text_field: strip_cites(text) or text, "cited_corpus_ids": merged}
    return data


def coerce_expansion(data, prose_fields: tuple[str, ...], id_field: str = "citation_ids"):
    """`mode="before"` coercion for a multi-part expansion (e.g. _AimExpansion).

    - a bare STRING (fully flattened aim) → spread the cleaned string across every prose part so the
      object is valid (degenerate but real model text — keeps the run from hard-failing), cites recovered;
    - an OBJECT with `[type:id]` cites inlined into any prose part → recover them into `id_field` (merged)
      and clean those parts;
    - an already-clean object → unchanged.
    """
    if isinstance(data, str):
        body = strip_cites(data) or data
        out = {f: body for f in prose_fields}
        out[id_field] = extract_cites(data)
        return out
    if isinstance(data, dict):
        out = dict(data)
        recovered: list[str] = []
        for f in prose_fields:
            v = out.get(f)
            inline = extract_cites(v)
            if inline:
                recovered.extend(inline)
                out[f] = strip_cites(v) or v
        if recovered:
            out[id_field] = list(dict.fromkeys([*(out.get(id_field) or []), *recovered]))
        return out
    return data
