"""_corpus.py — bounded corpus serialization for the live writer prompts [role-internal, binding].

The live writer prompt must not dump every finding at full corpus scale (~400 papers) — that overloads
the model and drives structured-output omissions / truncation. The bound is now the **Ingestion Layer**
(`cua/nih/ingestion.py`, INGEST-1 v2): a deterministic key_finding-clustering rerank-and-bound that
attaches a `writer_view` (the diversified top-K representatives + corroboration counts) to the corpus.
`findings_block` serializes THAT bounded view; `id_list_block` still lists the FULL set of citable ids.

GUARDRAIL — ID-PRESERVING (inv-1 unchanged): the bound shapes the writer's VIEW only. `corpus.sources`
(the full set) is untouched, so `id_list_block` lists every real id and the Grounder's cite-∈-corpus check
still runs against ALL sources (principle 6 — the closed-world corpus is untouched). The model can cite any
real corpus id, even one whose finding the bounded view didn't surface.

Note: the interim LIVE-2 recency cap (`FINDINGS_CAP`) is SUPERSEDED by the ingestion bound. `recent_sources`
is retained as a deterministic recency helper (no clock); `findings_block` no longer applies a recency cap —
when no `writer_view` is attached (e.g. the fixture path, which never goes live), it serializes all sources.

Owner: INGEST-1 v2 (builder 1), superseding LIVE-2 scale-robustness. Domain nouns are legal here (binding).
"""

from __future__ import annotations

# Retained recency helper (no longer the prompt bound — the ingestion top-K is). A generous historical
# default kept only so `recent_sources` has a cap when called without one; the live prompt no longer uses it.
FINDINGS_CAP = 120


def recent_sources(corpus, cap: int = FINDINGS_CAP) -> list:
    """The most-recent `cap` sources by year (descending; stable for ties → corpus order). A missing/None
    year sinks to the end. Deterministic — no clock, pure of the corpus. A recency helper (e.g. for ranking
    empty-key_finding singletons); the prompt bound is now the Ingestion Layer's top-K, not this cap."""
    sources = list(getattr(corpus, "sources", []) or [])
    ranked = sorted(sources, key=lambda p: getattr(p, "year", 0) or 0, reverse=True)
    return ranked[:cap]


def _writer_view(corpus):
    """The bounded writer VIEW the Ingestion Layer attached (a list of `ingestion.WriterRow`-likes), or
    None when no ingestion ran (the fixture/offline path) — read defensively so the spine `SourceSet` type
    is untouched (the attribute is set instance-side by `ingestion.attach_writer_view`)."""
    view = getattr(corpus, "writer_view", None)
    return view if view else None


def _view_row(row) -> str:
    """One findings row from a bounded-view entry: '[id] title — key_finding', annotating a representative
    of a multi-paper cluster with its corroboration COUNT (an int — descriptive metadata, NOT a grade)."""
    base = f"[{row.id}] {getattr(row, 'title', '') or ''} — {getattr(row, 'key_finding', '') or ''}"
    count = getattr(row, "count", 1) or 1
    if getattr(row, "is_representative", False) and count > 1:
        others = [m for m in getattr(row, "member_ids", ()) if m != row.id]
        shown = ", ".join(others[:6]) + (" …" if len(others) > 6 else "")
        base += f"  [corroborated by {count} papers: {shown}]"
    return base


def findings_block(corpus, cap: int = FINDINGS_CAP) -> str:
    """The BOUNDED prompt view of findings. When the Ingestion Layer attached a `writer_view`, serialize the
    diversified top-K representatives (+ corroboration counts). Otherwise (no ingestion — the fixture path,
    which never goes live) serialize every source's '[id] title — key_finding'. NOT the full id-list — that
    is `id_list_block` (inv-1 citability)."""
    view = _writer_view(corpus)
    if view is not None:
        rows = "\n".join(_view_row(r) for r in view)
        return rows or "(no corpus rows)"
    rows = "\n".join(
        f"[{p.id}] {getattr(p, 'title', '') or ''} — {getattr(p, 'key_finding', '') or ''}"
        for p in getattr(corpus, "sources", []) or []
    )
    return rows or "(no corpus rows)"


def id_list_block(corpus) -> str:
    """The FULL citable id list — EVERY corpus id, so the model can only cite real ids (inv-1 unchanged),
    even those whose finding the bounded view above didn't show (ID-PRESERVING: the gate's referent is the
    full corpus)."""
    ids = [p.id for p in getattr(corpus, "sources", []) or []]
    return ", ".join(ids) or "(none)"
