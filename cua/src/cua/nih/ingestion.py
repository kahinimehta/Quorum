"""ingestion.py — NIH binding: the corpus Ingestion Layer (deterministic, rule-based, stdlib-only).

Implements: `build/decisions/2026-06-02-ingestion-keyfinding-clustering-amendment.md` (RATIFIED — the
            contract-amendment record for `IngestionConfig` + the clustering guardrail) and its parent
            `2026-06-02-ingestion-layer-rank-and-bound.md`. Relay: `build/live/INGEST-1-v2_relay.md`.
Generic role: none — this is a binding-side PREPROCESSING stage. It reranks-and-bounds the assembled
              corpus BEFORE the engine orchestrator (it is NOT retrieval — upstream already retrieved).
              It never enters the engine spine; it carries NO LLM, NO embeddings, NO new deps.
NIH binding: domain nouns are legal here (binding layer, CONVENTIONS rule 1).
Owner: INGEST-1 v2 (builder 1).

What it does (pipeline): `cluster-by-key_finding → relevance-score → diversity-bounded top-K → writer view`.
It groups papers whose `key_finding`s say the same thing (a real diversity axis sourced from findings,
since per-paper tags don't reach the agent), ranks by topic relevance, and draws a diversified top-K that
spans distinct findings — so the live writer reads a denser, deduplicated, breadth-preserving view instead
of ~400 undifferentiated findings (the `full1` truncation / `dem3` streaming-wall fix).

═══════════════════════════════════════════════════════════════════════════════════════════════════════
HONESTY LINE (must travel with this layer — decision record, demo narrative, and the drop-audit):
  Clustering gives a REAL diversity axis and tames redundancy, but with grade flat (skeptic unbuilt) it
  spreads FINDINGS, not STANCES — it MITIGATES confirmation bias, it does NOT prevent it. Corroboration
  count is NOT calibration. The negation penalty is weak partial mitigation; the `possible_contradiction`
  flag is the safety net.
═══════════════════════════════════════════════════════════════════════════════════════════════════════

THREE HARD GUARDRAILS (built in, not bolted on):
  1. ID-PRESERVING — clustering shapes the WRITER'S BOUNDED VIEW only. The citation gate's referent stays
     the FULL corpus (cited ⊆ full corpus; inv-1 unchanged). This module NEVER deletes a source and NEVER
     touches what the Grounder checks against — it only produces a `writer_view` over the full corpus.
  2. COUNT ≠ GRADE — a cluster's corroboration `count` is an INTEGER, descriptive metadata. It is NEVER a
     float/score, never bucketed to a grade, never fed to calibration (the decision-B trap). The skeptic
     grades; ingestion counts.
  3. CONTRADICTION-MERGE — corroborators are RETAINED (member ids + count kept, never deleted). Lexically
     similar findings can be opposite claims; the `possible_contradiction` audit flag is the safety net
     that makes a merged contradiction visible (see `_DropAudit`).

Determinism + offline: stable canonical order (by id) drives greedy clustering, every sort carries an
explicit tiebreak, there is no clock and no RNG. Importing this module touches nothing external.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# === config — the layer's OWN binding-side dataclass (NOT §1.8 RoleConfig, which is LLM-role-scoped) ===
# The amendment doc is the contract-amendment record sanctioning these knobs; this is NOT a `files/` type.


@dataclass(frozen=True)
class IngestionConfig:
    """Knobs for the deterministic ingestion stage (amendment doc — binding-side, NOT `RoleConfig`).

    - `top_k`: the max number of representatives the writer's bounded VIEW carries (the budget bound).
    - `cluster_similarity_threshold`: token-Jaccard over `key_finding`s at/above which two findings merge
      into one cluster (0.0 merges everything, 1.0 merges only identical token sets).
    - `per_cluster_cap`: the max members one cluster may contribute to the top-K — the diversity floor, so
      one dense finding cannot dominate the writer's view (DIVERSIFY, not dedup-to-one).
    - `polarity_aware`: apply the negation-cue penalty during clustering (CHEAP PARTIAL mitigation — see
      `_negation_penalty`). The `possible_contradiction` flag is computed regardless.
    - `relevance_weight`: scales the topic-overlap relevance contribution (a small relevance knob; the
      ranking is relevance → recency tiebreak → stable id tiebreak)."""

    top_k: int = 60
    cluster_similarity_threshold: float = 0.5
    per_cluster_cap: int = 2
    polarity_aware: bool = True
    relevance_weight: float = 1.0

    def as_dict(self) -> dict:
        return {
            "top_k": self.top_k,
            "cluster_similarity_threshold": self.cluster_similarity_threshold,
            "per_cluster_cap": self.per_cluster_cap,
            "polarity_aware": self.polarity_aware,
            "relevance_weight": self.relevance_weight,
        }


DEFAULT_CONFIG = IngestionConfig()

# The cheap-partial-mitigation penalty: when two findings differ on a negation cue, their similarity is
# docked by this much so they are LESS likely to merge. ⚠️ This is NOT a contradiction FIX — see
# `_negation_penalty`. A module constant (not a config knob) so the partial nature stays in the code.
_POLARITY_PENALTY = 0.35

RANKING_METHOD = (
    "key_finding_token_jaccard_clustering + topic_relevance + recency_tiebreak "
    "(deterministic, rule-based; NO embeddings, NO LLM)"
)
GUARDRAIL_LABEL = "key_finding_clustering_diversity_floor"
ANTI_CONFIRMATION_NOTE = (
    "MITIGATION ONLY — spreads findings not stances; pending skeptic grade / Agent-2/3 tags"
)
HONESTY_LINE = (
    "Clustering gives a real diversity axis and tames redundancy, but with grade flat it spreads "
    "FINDINGS, not STANCES — it MITIGATES confirmation bias, it does NOT prevent it. Corroboration "
    "count is NOT calibration. The negation penalty is weak partial mitigation; the "
    "possible_contradiction flag is the safety net."
)


# === text features (deterministic; stdlib `re` only) =============================================

_WORD = re.compile(r"[a-z0-9]+")

# A tiny stopword set so Jaccard keys on content words, not glue. Generic English — no domain terms.
_STOP = frozenset(
    "the a an of in on at to for with and or but is are was were be been being as by from that this "
    "these those it its their our we will can may might could should would not no than then into over "
    "under between within across via using used use also more most less least via per".split()
)

# Negation / contrary cues — the SAME signal the penalty and the contradiction flag both read. Cheap and
# lexical: it catches "does not increase" vs "increases" but MISSES antonyms ("improved"/"worsened"),
# hedging, and effect-direction reversals with no negation word at all (see `_negation_penalty`).
_NEGATION_CUES = (
    " no ", " not ", "n't", " non-", " fails to", " fail to", " failed to", " does not", " did not",
    " do not", " without ", " lack ", " lacks ", " lacked ", " absence of", " unable ", " negative ",
    " no effect", " not significant", " no significant", " no difference", " did not improve",
    " not associated", " no association", " unaffected", " independent of",
)


def _tokens(text: str) -> frozenset[str]:
    """Content-word token set of `text` (lowercased, stopworded, length>1). Deterministic."""
    return frozenset(w for w in _WORD.findall((text or "").lower()) if len(w) > 1 and w not in _STOP)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """|a ∩ b| / |a ∪ b| (0.0 when both empty). The clustering similarity."""
    if not a and not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _has_negation(text: str) -> bool:
    """Whether `text` carries a negation/contrary cue (the cheap polarity signal). Pads with spaces so
    word-boundary-ish cues match at the edges."""
    t = " " + (text or "").lower() + " "
    return any(cue in t for cue in _NEGATION_CUES)


def _negation_penalty(neg_a: bool, neg_b: bool, config: IngestionConfig) -> float:
    """The polarity penalty between two findings — CHEAP PARTIAL MITIGATION, **NOT a contradiction FIX**.

    When two findings differ on a negation cue, dock their similarity so naive lexical overlap is less
    likely to merge a finding with its negation. This narrows the EASY case only: it MISSES antonym
    contradictions ("improved" vs "worsened"), hedging, and effect-direction reversals with no negation
    word. Full separation needs stance detection, which we cannot do rule-based — so the real safety net
    is the `possible_contradiction` audit flag (a merged mixed-polarity cluster is surfaced even when this
    penalty failed to split it). Off when `polarity_aware` is False."""
    if not config.polarity_aware or neg_a == neg_b:
        return 0.0
    return _POLARITY_PENALTY


# === cluster + result shapes =====================================================================


@dataclass
class _RawCluster:
    """A cluster under construction (greedy leader clustering). `seed_*` is the canonical-first member
    used as the comparison leader; members accumulate as findings join. `has_neg`/`has_non_neg` track
    whether the cluster has BOTH polarities (the `possible_contradiction` signal)."""

    cluster_id: int
    seed_tokens: frozenset[str]
    seed_neg: bool = False  # the leader's negation polarity (the penalty compares against this)
    members: list = field(default_factory=list)  # Paper-likes (the corroborators — never deleted)
    has_neg: bool = False
    has_non_neg: bool = False
    empty: bool = False  # empty key_finding → singleton with no text signal (recency-ranked, flagged)


@dataclass(frozen=True)
class Cluster:
    """A finalized cluster (audit + selection unit). `count` is an INTEGER — descriptive corroboration
    metadata, GUARDRAIL 2: NEVER a grade, never a float, never fed to calibration."""

    cluster_id: int
    representative_id: str  # the highest-relevance member (what the writer reads first)
    member_ids: tuple[str, ...]  # ALL members (corroborators retained — guardrail 3)
    count: int  # == len(member_ids); a plain int (guardrail 2)
    possible_contradiction: bool  # members carry MIXED negation polarity (the safety-net flag)
    empty_finding: bool  # the cluster's seed had an empty key_finding (no text signal)
    shown_in_topk: bool  # at least one member made the bounded top-K view


@dataclass(frozen=True)
class WriterRow:
    """One row of the writer's bounded VIEW — a representative finding + its corroboration count. The
    writer serializes these (see `roles/_corpus.findings_block`); `count`/`member_ids` are the honest
    corroboration metadata (an int, never a grade)."""

    id: str
    title: str
    key_finding: str
    count: int  # corroboration count of this row's cluster (1 for a singleton)
    is_representative: bool  # this row is its cluster's representative (carries the count annotation)
    member_ids: tuple[str, ...]


@dataclass(frozen=True)
class IngestionResult:
    """The output of `ingest`. Carries the bounded `writer_view` (what the live writer reads), the full
    cluster set, and the drop-audit payload for `<run>.ingestion.json`. ID-PRESERVING (guardrail 1): this
    NEVER mutates the corpus and NEVER narrows the citation gate — `selected_ids` is the writer VIEW, not
    a new SourceSet."""

    corpus_n: int
    config: IngestionConfig
    clusters: tuple[Cluster, ...]
    selected_ids: tuple[str, ...]  # the bounded top-K view ids, in draw order
    excluded_ids: tuple[str, ...]  # corpus ids NOT in the view (retained + citable; listed in the audit)
    writer_view: tuple[WriterRow, ...]

    def audit(self) -> dict:
        """The `<run>.ingestion.json` payload — THE honesty mechanism (with grade flat, this is what makes
        a swallowed contradiction or a one-sided selection VISIBLE to the operator and a judge).
        `possible_contradiction` is kept prominent (per cluster + a roll-up)."""
        return {
            "corpus_n": self.corpus_n,
            "top_k": self.config.top_k,
            "config": self.config.as_dict(),
            "ranking_method": RANKING_METHOD,
            "possible_contradiction_cluster_ids": [
                c.cluster_id for c in self.clusters if c.possible_contradiction
            ],
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "representative_id": c.representative_id,
                    "member_ids": list(c.member_ids),
                    "count": c.count,  # int — descriptive corroboration, NOT a grade (guardrail 2)
                    "shown_in_topk": c.shown_in_topk,
                    "possible_contradiction": c.possible_contradiction,
                }
                for c in self.clusters
            ],
            "excluded_ids": list(self.excluded_ids),
            "guardrail": GUARDRAIL_LABEL,
            "anti_confirmation": ANTI_CONFIRMATION_NOTE,
            "honesty": HONESTY_LINE,
        }


# === the pipeline ================================================================================


def _greedy_clusters(sources: list, config: IngestionConfig) -> list[_RawCluster]:
    """Greedy leader clustering by `key_finding` token-Jaccard over a STABLE canonical order (by id), so
    clusters reproduce byte-for-byte. Each paper joins the most-similar existing cluster whose effective
    similarity (Jaccard minus the polarity penalty) meets the threshold, else seeds a new cluster. An
    empty `key_finding` (no text signal) always seeds its OWN singleton (guardrail/decision doc)."""
    order = sorted(sources, key=lambda p: str(getattr(p, "id", "")))
    clusters: list[_RawCluster] = []
    for p in order:
        kf = getattr(p, "key_finding", "") or ""
        neg = _has_negation(kf)
        if not kf.strip():  # no text → its own singleton, flagged empty (recency-ranked downstream)
            clusters.append(_RawCluster(cluster_id=len(clusters), seed_tokens=frozenset(), seed_neg=neg,
                                        members=[p], has_neg=neg, has_non_neg=not neg, empty=True))
            continue
        toks = _tokens(kf)
        best, best_sim = None, 0.0
        for c in clusters:
            if c.empty:
                continue
            sim = _jaccard(toks, c.seed_tokens) - _negation_penalty(neg, c.seed_neg, config)
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= config.cluster_similarity_threshold:
            best.members.append(p)
            best.has_neg = best.has_neg or neg
            best.has_non_neg = best.has_non_neg or (not neg)
        else:
            clusters.append(_RawCluster(cluster_id=len(clusters), seed_tokens=toks, seed_neg=neg,
                                        members=[p], has_neg=neg, has_non_neg=not neg))
    return clusters


def _relevance(paper, topic_tokens: frozenset[str], config: IngestionConfig) -> float:
    """Topic relevance: the count of topic terms present in the paper's `title` + `key_finding`, scaled by
    `relevance_weight`. Lexical, deterministic; the real-text relevance source (per-paper tags are absent).
    0.0 when there is no topic signal — ranking then falls through to the recency + id tiebreaks."""
    text = (getattr(paper, "title", "") or "") + " " + (getattr(paper, "key_finding", "") or "")
    if not topic_tokens:
        return 0.0
    return config.relevance_weight * len(_tokens(text) & topic_tokens)


def _member_sort_key(paper, topic_tokens: frozenset[str], config: IngestionConfig):
    """Rank key: relevance DESC, then recency DESC (None/0 sinks), then stable id ASC."""
    return (
        -_relevance(paper, topic_tokens, config),
        -(getattr(paper, "year", 0) or 0),
        str(getattr(paper, "id", "")),
    )


def _select_view_ids(clusters_sorted: list[tuple[_RawCluster, list]], target_size: int,
                     per_cluster_cap: int) -> list[str]:
    """Diversity-bounded top-K draw (DIVERSIFY, NOT dedup-to-one): a round-robin ACROSS clusters (already
    ordered by representative relevance), each member already ranked within its cluster.

    Phase 1 (diversify) — rounds 0..per_cluster_cap-1: in each round take the next member of every cluster
    in turn, so one dense finding contributes at most `per_cluster_cap` and cannot dominate.
    Phase 2 (fill) — only if budget remains under `target_size` AND members are left (few clusters, each
    large): relax the cap and keep drawing across clusters. This is what makes `top_k ≥ N` an IDENTITY
    (every paper is drawn); for `top_k < N` the cap binds and the view stays diversified."""
    selected: list[str] = []

    def _draw_round(r: int) -> bool:
        progressed = False
        for _c, members in clusters_sorted:
            if len(selected) >= target_size:
                return progressed
            if r < len(members):
                selected.append(str(getattr(members[r], "id", "")))
                progressed = True
        return progressed

    for r in range(per_cluster_cap):  # phase 1: capped, diversified
        if len(selected) >= target_size:
            return selected
        _draw_round(r)
    r = per_cluster_cap  # phase 2: fill to reach target_size when budget remains
    while len(selected) < target_size and _draw_round(r):
        r += 1
    return selected


def ingest(corpus, topic: str = "", config: IngestionConfig = DEFAULT_CONFIG) -> IngestionResult:
    """Rerank-and-bound the assembled corpus into a diversified writer VIEW (the pipeline). PURE of the
    corpus — never mutates it (guardrail 1: the full corpus stays the citation gate's referent). `topic`
    is the GrantCall topic the relevance key scores against (e.g. `grant_call.title`)."""
    sources = list(getattr(corpus, "sources", []) or [])
    n = len(sources)
    topic_tokens = _tokens(topic)
    by_id = {str(getattr(p, "id", "")): p for p in sources}

    raw = _greedy_clusters(sources, config)

    # Rank members within each cluster (relevance → recency → id), and order clusters by their
    # representative's rank. Representative = the highest-relevance member (what the writer reads first).
    ranked: list[tuple[_RawCluster, list]] = []
    for c in raw:
        members_sorted = sorted(c.members, key=lambda p: _member_sort_key(p, topic_tokens, config))
        ranked.append((c, members_sorted))
    ranked.sort(key=lambda cm: _member_sort_key(cm[1][0], topic_tokens, config))

    target_size = min(config.top_k, n)
    selected_ids = _select_view_ids(ranked, target_size, max(1, config.per_cluster_cap))
    selected_set = set(selected_ids)

    # Finalize clusters (stable cluster_id order) + the drop-audit flags.
    clusters: list[Cluster] = []
    for c, members_sorted in sorted(ranked, key=lambda cm: cm[0].cluster_id):
        member_ids = tuple(str(getattr(p, "id", "")) for p in members_sorted)
        clusters.append(Cluster(
            cluster_id=c.cluster_id,
            representative_id=member_ids[0],
            member_ids=member_ids,
            count=len(member_ids),  # int (guardrail 2)
            possible_contradiction=(c.has_neg and c.has_non_neg),  # mixed polarity → the safety-net flag
            empty_finding=c.empty,
            shown_in_topk=any(mid in selected_set for mid in member_ids),
        ))

    # Writer view rows, in draw order. The representative of a multi-member cluster carries the count.
    rep_ids = {c.representative_id for c in clusters}
    count_by_member = {mid: c.count for c in clusters for mid in c.member_ids}
    members_by_rep = {c.representative_id: c.member_ids for c in clusters}
    writer_view = tuple(
        WriterRow(
            id=sid,
            title=getattr(by_id.get(sid), "title", "") or "",
            key_finding=getattr(by_id.get(sid), "key_finding", "") or "",
            count=count_by_member.get(sid, 1),
            is_representative=sid in rep_ids,
            member_ids=members_by_rep.get(sid, (sid,)),
        )
        for sid in selected_ids
    )

    excluded_ids = tuple(
        str(getattr(p, "id", "")) for p in sources if str(getattr(p, "id", "")) not in selected_set
    )

    return IngestionResult(
        corpus_n=n,
        config=config,
        clusters=tuple(clusters),
        selected_ids=tuple(selected_ids),
        excluded_ids=excluded_ids,
        writer_view=writer_view,
    )


# === binding-side wiring helper ==================================================================

# The attribute name the live writer prompt reads off the corpus (see `roles/_corpus.findings_block`).
# It carries the bounded VIEW only; `corpus.sources` (the full set) is untouched, so the Grounder's
# `source_set.ids()` and the Proposal's references still span the FULL corpus (guardrail 1).
WRITER_VIEW_ATTR = "writer_view"


def attach_writer_view(corpus, result: IngestionResult) -> None:
    """Attach the bounded writer VIEW to the corpus object for the live writer prompt to serialize, WITHOUT
    touching `corpus.sources` (guardrail 1 — the citation gate's referent stays the full corpus). This sets
    a binding-side instance attribute only; it adds no field to the spine `SourceSet` type and leaves the
    full source list — and therefore inv-1 — exactly as it was."""
    setattr(corpus, WRITER_VIEW_ATTR, list(result.writer_view))
