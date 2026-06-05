"""INGEST-1 v2 — the corpus Ingestion Layer (deterministic key_finding clustering, binding-side).

`build/live/INGEST-1-v2_relay.md` + `build/decisions/2026-06-02-ingestion-keyfinding-clustering-
amendment.md`: a rule-based, stdlib-only rerank-and-bound that clusters by `key_finding`, scores topic
relevance, and draws a DIVERSIFIED top-K writer view — without embeddings/LLM/new deps. These tests pin
the pipeline + the THREE HARD GUARDRAILS:
  (1) ID-PRESERVING — the bound shapes the writer's VIEW only; `corpus.sources` (the citation gate's
      referent) is untouched, every id stays citable (inv-1 unchanged).
  (2) COUNT ≠ GRADE — corroboration `count` is a plain INT, never a float/grade, never calibration.
  (3) CONTRADICTION-MERGE — corroborators are RETAINED; a planted contradiction is split by the negation
      penalty OR (if it merges anyway) surfaced by the `possible_contradiction` audit flag (the safety net).
Plus: deterministic clusters, `per_cluster_cap`/`top_k` honored, IDENTITY when `top_k ≥ N`, empty
`key_finding` singleton, the drop-audit contents/honesty line, and `run_db` emitting `<run>.ingestion.json`.

Owner: INGEST-1 v2 (builder 1). Offline; no network; no LLM (ingestion is pure rule-based code).
"""

from __future__ import annotations

import json
import sqlite3

from cua.nih.framework import Paper
from cua.nih.ingestion import (
    IngestionConfig,
    attach_writer_view,
    ingest,
)
from cua.roles._corpus import findings_block, id_list_block
from cua.types import SourceSet


# --- fixtures -------------------------------------------------------------------------------------


def _P(pid: str, year: int, title: str, kf: str) -> Paper:
    return Paper(id=pid, authors=[], year=year, title=title, venue="J", resolvable_id=pid, key_finding=kf, real=True)


def _corpus(papers) -> SourceSet:
    return SourceSet(list(papers))


# A finding pair that is lexically near-identical but opposite in stance (only the negation differs) — the
# contradiction-merge probe. Shares enough tokens that naive Jaccard would merge them.
_POS = "the treatment improves motor function and quality of life in patients with the disease"
_NEG = "the treatment does not improve motor function or quality of life in patients with the disease"


# === deterministic clusters ======================================================================


def test_clusters_are_deterministic():
    groups = ["alpha synuclein aggregation drives loss", "gcase lysosomal dysfunction observed",
              "lrrk2 kinase activity elevated here"]
    papers = [_P(f"p{i}", 2000 + i, f"T{i}", groups[i % 3]) for i in range(9)]
    c = _corpus(papers)
    a = ingest(c, topic="parkinson", config=IngestionConfig(top_k=5)).audit()
    b = ingest(c, topic="parkinson", config=IngestionConfig(top_k=5)).audit()
    assert a == b                                              # byte-identical, no clock/RNG
    # the three finding groups → three clusters
    assert len({tuple(cl["member_ids"]) for cl in a["clusters"]}) == 3


# === per_cluster_cap + top_k honored (diversify, not dedup-to-one) ===============================


def test_per_cluster_cap_caps_a_dense_cluster():
    # 6 near-identical findings (one dense cluster) + 2 distinct singletons; cap=2 so the dense finding
    # cannot dominate the writer's view even though it has the most corroborators.
    dense = [_P(f"d{i}", 2000 + i, "Dense", "gcase activity reduced in patient cohort") for i in range(6)]
    singles = [_P("s1", 1995, "S1", "alpha synuclein spreads between neurons"),
               _P("s2", 1996, "S2", "dopamine transporter imaging tracks decline")]
    res = ingest(_corpus(dense + singles), topic="",
                 config=IngestionConfig(top_k=4, per_cluster_cap=2, cluster_similarity_threshold=0.4))
    dense_ids = {f"d{i}" for i in range(6)}
    shown_dense = [sid for sid in res.selected_ids if sid in dense_ids]
    assert len(shown_dense) == 2                               # capped at per_cluster_cap (not all 6)
    # GUARDRAIL 3: the corroborators are RETAINED — all 6 ids in the cluster, 4 merely not shown (excluded)
    dense_cluster = max(res.clusters, key=lambda c: c.count)
    assert dense_cluster.count == 6 and len(dense_cluster.member_ids) == 6
    assert len(dense_ids - set(res.selected_ids)) == 4
    assert all(d in res.excluded_ids for d in (dense_ids - set(res.selected_ids)))


def test_top_k_bounds_the_view_size():
    papers = [_P(f"p{i}", 2000 + i, f"T{i}", f"unique mechanism{i} pathway study finding") for i in range(20)]
    res = ingest(_corpus(papers), topic="", config=IngestionConfig(top_k=7))
    assert len(res.selected_ids) == 7 and len(res.writer_view) == 7   # bounded to top_k


def test_identity_when_top_k_ge_n():
    # top_k ≥ N → the bound is a no-op: every paper is in the view, nothing excluded (even with cap=1,
    # the fill pass relaxes the cap to honor identity).
    papers = [_P(f"p{i}", 2000 + i, f"T{i}", f"distinct finding alpha{i} beta{i} gamma") for i in range(8)]
    res = ingest(_corpus(papers), topic="", config=IngestionConfig(top_k=50, per_cluster_cap=1))
    assert set(res.selected_ids) == {p.id for p in papers}
    assert res.excluded_ids == ()


# === GUARDRAIL 1: ID-PRESERVING — the full corpus stays the gate's referent ======================


def test_id_preserving_full_corpus_reaches_the_gate():
    papers = [_P(f"p{i}", 2000 + i, f"T{i}", f"finding{i} about mechanism{i} in study{i}") for i in range(10)]
    corpus = _corpus(papers)
    before = corpus.ids()
    res = ingest(corpus, topic="", config=IngestionConfig(top_k=3))
    attach_writer_view(corpus, res)
    # the SourceSet is NEVER mutated — .sources / .ids() stay the FULL corpus (the Grounder's referent)
    assert corpus.ids() == before and len(corpus.sources) == 10
    # the FULL id-list is complete (every id citable, inv-1) even though only top_k findings are shown
    ids = id_list_block(corpus)
    assert all(p.id in ids for p in papers)
    # the bounded writer view is the top-K only
    assert findings_block(corpus).count("\n") + 1 == 3


def test_attach_writer_view_then_findings_block_shows_counts():
    # a 3-member cluster + a singleton; the representative row carries the corroboration COUNT (an int)
    papers = [_P("a", 2020, "A", "gcase reduced activity progression patients"),
              _P("b", 2021, "B", "gcase reduced activity progression patients cohort"),
              _P("c", 2022, "C", "gcase reduced activity progression in patients"),
              _P("z", 2019, "Z", "unrelated dopamine imaging modality finding")]
    corpus = _corpus(papers)
    res = ingest(corpus, topic="gcase", config=IngestionConfig(top_k=10, cluster_similarity_threshold=0.4))
    attach_writer_view(corpus, res)
    block = findings_block(corpus)
    assert "corroborated by 3 papers" in block                # the representative annotates the count
    # id_list_block stays the FULL corpus (inv-1)
    assert all(p.id in id_list_block(corpus) for p in papers)


# === GUARDRAIL 2: COUNT ≠ GRADE ==================================================================


def test_count_is_a_plain_int_never_a_grade():
    papers = [_P(f"p{i}", 2000 + i, "T", "gcase reduced activity progression patient") for i in range(4)]
    res = ingest(_corpus(papers), topic="", config=IngestionConfig(cluster_similarity_threshold=0.4))
    big = max(res.clusters, key=lambda c: c.count)
    assert big.count == 4 and type(big.count) is int          # a plain int, NOT a float/grade
    for c in res.audit()["clusters"]:
        assert isinstance(c["count"], int) and not isinstance(c["count"], bool)


# === GUARDRAIL 3: CONTRADICTION-MERGE — split by penalty OR flagged ==============================


def test_planted_contradiction_split_by_negation_penalty():
    # polarity_aware ON → the negation penalty docks the similarity below threshold → two clusters.
    res = ingest(_corpus([_P("pos", 2020, "Pos", _POS), _P("neg", 2021, "Neg", _NEG)]),
                 topic="", config=IngestionConfig(cluster_similarity_threshold=0.5, polarity_aware=True))
    assert len(res.clusters) == 2                              # the penalty split the contradiction
    assert all(not c.possible_contradiction for c in res.clusters)


def test_planted_contradiction_flagged_when_merged():
    # penalty OFF → the near-identical findings MERGE; the safety-net flag must still fire on mixed polarity
    # (this is the case the cheap negation penalty cannot solve — the audit flag is what surfaces it).
    res = ingest(_corpus([_P("pos", 2020, "Pos", _POS), _P("neg", 2021, "Neg", _NEG)]),
                 topic="", config=IngestionConfig(cluster_similarity_threshold=0.4, polarity_aware=False))
    merged = [c for c in res.clusters if c.count == 2]
    assert merged and merged[0].possible_contradiction is True
    assert merged[0].cluster_id in res.audit()["possible_contradiction_cluster_ids"]
    # corroborators retained — both ids kept, none deleted (guardrail 3)
    assert set(merged[0].member_ids) == {"pos", "neg"}


# === empty key_finding → singleton ===============================================================


def test_empty_key_finding_is_its_own_singleton():
    papers = [_P("a", 2020, "A", "gcase reduced activity in cohort"),
              _P("b", 2021, "B", "gcase reduced activity in cohort"),
              _P("empty", 0, "E", "")]
    res = ingest(_corpus(papers), topic="", config=IngestionConfig(top_k=10, cluster_similarity_threshold=0.5))
    empty = next(c for c in res.clusters if "empty" in c.member_ids)
    assert empty.member_ids == ("empty",) and empty.empty_finding is True
    assert empty.count == 1 and empty.possible_contradiction is False
    # a,b (identical finding) clustered together — the empty one did NOT absorb them
    assert any(set(c.member_ids) == {"a", "b"} for c in res.clusters)


# === the drop-audit: the honesty mechanism =======================================================


def test_drop_audit_shape_and_honesty_line():
    papers = [_P(f"p{i}", 2000 + i, f"T{i}", f"finding{i} about a distinct mechanism") for i in range(6)]
    res = ingest(_corpus(papers), topic="mechanism", config=IngestionConfig(top_k=3))
    a = res.audit()
    assert a["corpus_n"] == 6 and a["top_k"] == 3
    assert set(a["config"]) == {"top_k", "cluster_similarity_threshold", "per_cluster_cap",
                                "polarity_aware", "relevance_weight"}
    assert a["ranking_method"] and "NO embeddings, NO LLM" in a["ranking_method"]
    assert a["guardrail"] == "key_finding_clustering_diversity_floor"
    assert "MITIGATION ONLY" in a["anti_confirmation"]
    # the HONESTY LINE travels with the artifact (relay requirement)
    assert "MITIGATES confirmation bias" in a["honesty"] and "not calibration" in a["honesty"].lower()
    assert "negation penalty is weak" in a["honesty"]
    assert "possible_contradiction_cluster_ids" in a          # the flag kept PROMINENT (a roll-up)
    for c in a["clusters"]:
        assert {"cluster_id", "representative_id", "member_ids", "count", "shown_in_topk",
                "possible_contradiction"} <= set(c)
    # excluded ids = corpus minus the shown view — corroborators retained + LISTED (never silently deleted)
    assert len(a["excluded_ids"]) == 6 - len(res.selected_ids)
    assert set(a["excluded_ids"]).isdisjoint(set(res.selected_ids))


def test_one_sided_selection_is_visible_in_the_audit():
    # a dense mega-cluster + low-relevance singletons, top_k tiny → the audit shows which clusters did NOT
    # make the top-K (shown_in_topk=False), so a one-sided selection is VISIBLE, not silent.
    dense = [_P(f"d{i}", 2010 + i, "Dense", "gcase activity reduced progression patient cohort") for i in range(5)]
    tail = [_P("t0", 1980, "T0", "dopamine transporter imaging tracks decline"),
            _P("t1", 1981, "T1", "sleep disturbance precedes motor onset"),
            _P("t2", 1982, "T2", "gut microbiome alterations appear early"),
            _P("t3", 1983, "T3", "deep brain stimulation alleviates tremor"),
            _P("t4", 1984, "T4", "olfactory deficit common prodromal marker")]
    res = ingest(_corpus(dense + tail), topic="gcase progression",
                 config=IngestionConfig(top_k=2, per_cluster_cap=2))
    not_shown = [c for c in res.clusters if not c.shown_in_topk]
    assert not_shown                                          # some clusters are excluded → visible
    assert any(not c["shown_in_topk"] for c in res.audit()["clusters"])


# === run_db wiring: <run>.ingestion.json is emitted ==============================================


def _build_mini_db(path: str) -> None:
    """A minimal neurodiscover-shaped SQLite the INT-2 adapter can read (only the columns it SELECTs). Four
    evidence rows (incl. a GCase corroboration pair + a contrary finding) + one NULL-strength connection."""
    c = sqlite3.connect(path)
    try:
        c.executescript(
            """
            CREATE TABLE evidence(evidence_id INTEGER PRIMARY KEY, source_type TEXT, source_id TEXT, title TEXT,
                year INTEGER, publication_year INTEGER, venue TEXT, key_result TEXT, evidence_snippet TEXT,
                abstract TEXT, doi TEXT, study_type TEXT, sample_size INTEGER, access_status TEXT);
            CREATE TABLE subgroups(subgroup_id INTEGER PRIMARY KEY, name TEXT, defining_features TEXT, notes TEXT);
            CREATE TABLE treatment_connections(connection_id INTEGER PRIMARY KEY, subgroup_id INTEGER,
                mechanism TEXT, treatment TEXT, evidence_strength REAL);
            CREATE TABLE connection_evidence(connection_id INTEGER, evidence_id INTEGER);
            """
        )
        rows = [
            (1, "literature", "100", "GCase A", 2020, None, "J", "GCase activity correlates with progression", None, None, "10/100", "cohort", 50, None),
            (2, "literature", "101", "GCase B", 2021, None, "J", "GCase activity correlates with faster progression", None, None, "10/101", "cohort", 60, None),
            (3, "literature", "102", "Contra", 2022, None, "J", "GCase activity does not correlate with progression", None, None, "10/102", "cohort", 40, None),
            (4, "trial", "200", "Trial", 2023, None, "J", "Phase 2 trial of a GCase chaperone in patients", None, None, "NCT200", "phase 2", 30, None),
        ]
        c.executemany(
            "INSERT INTO evidence(evidence_id,source_type,source_id,title,year,publication_year,venue,"
            "key_result,evidence_snippet,abstract,doi,study_type,sample_size,access_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows,
        )
        c.execute("INSERT INTO subgroups(subgroup_id,name,defining_features,notes) VALUES (1,'GBA-PD','GBA mutation','n')")
        c.execute("INSERT INTO treatment_connections(connection_id,subgroup_id,mechanism,treatment,evidence_strength) "
                  "VALUES (1,1,'GCase','chaperone',NULL)")
        c.executemany("INSERT INTO connection_evidence(connection_id,evidence_id) VALUES (?,?)", [(1, 1), (1, 4)])
        c.commit()
    finally:
        c.close()


def test_run_db_emits_ingestion_audit(tmp_path):
    db = tmp_path / "mini.db"
    _build_mini_db(str(db))
    from cua.nih.run_db import run_db

    out = tmp_path / "out"
    rc = run_db(db=str(db), run_id="ing", out_dir=out)
    assert rc == 0
    # four artifacts now — the three canonical + the Ingestion drop-audit
    for name in ("ing.proposal.json", "ing.trace.jsonl", "ing.audit.json", "ing.ingestion.json"):
        assert (out / name).is_file()

    ing = json.loads((out / "ing.ingestion.json").read_text(encoding="utf-8"))
    assert ing["corpus_n"] == 4
    assert ing["guardrail"] == "key_finding_clustering_diversity_floor"
    assert "MITIGATION ONLY" in ing["anti_confirmation"]
    assert "MITIGATES confirmation bias" in ing["honesty"]
    assert "possible_contradiction_cluster_ids" in ing
    assert all("possible_contradiction" in c and isinstance(c["count"], int) for c in ing["clusters"])

    # ID-PRESERVING: ingestion shaped the writer view, NOT the citation gate — the run is still inv-1 clean.
    audit = json.loads((out / "ing.audit.json").read_text(encoding="utf-8"))
    assert audit["grounding_report"]["all_in_source_set"] is True
    assert audit["grounding_report"]["orphan_ids"] == []


def test_run_db_ingestion_audit_is_deterministic(tmp_path):
    db = tmp_path / "mini.db"
    _build_mini_db(str(db))
    from cua.nih.run_db import run_db

    a, b = tmp_path / "a", tmp_path / "b"
    run_db(db=str(db), run_id="ing", out_dir=a)
    run_db(db=str(db), run_id="ing", out_dir=b)
    assert (a / "ing.ingestion.json").read_text() == (b / "ing.ingestion.json").read_text()
