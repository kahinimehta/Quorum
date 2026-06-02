"""
PubTator3 entity grounding for literature extractions (PMID only).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from validation.consistency import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    extract_entity_hints,
)

PUBTATOR_EXPORT = (
    "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson"
)
ENTITY_TYPES = ("Gene", "Disease", "Chemical", "Species")


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    a_norm = {x.lower() for x in a}
    b_norm = {x.lower() for x in b}
    return len(a_norm & b_norm) / len(a_norm | b_norm)


def fetch_pubtator_entities(pmid: str, timeout: int = 30) -> dict[str, set[str]]:
    """Return genes, diseases, chemicals from PubTator3 biocjson."""
    url = f"{PUBTATOR_EXPORT}?pmids={pmid}"
    req = urllib.request.Request(url, headers={"User-Agent": "NeuroDiscover/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())

    entities: dict[str, set[str]] = {"genes": set(), "diseases": set(), "chemicals": set()}
    docs = data.get("PubTator3") or data.get("documents") or []
    if isinstance(docs, dict):
        docs = [docs]
    for doc in docs:
        for passage in doc.get("passages") or []:
            for ann in passage.get("annotations") or []:
                infons = ann.get("infons") or {}
                etype = infons.get("type") or infons.get("identifier")
                text = (ann.get("text") or "").strip()
                if not text:
                    continue
                if etype == "Gene":
                    entities["genes"].add(text)
                elif etype == "Disease":
                    entities["diseases"].add(text)
                elif etype == "Chemical":
                    entities["chemicals"].add(text)
    return entities


def compare_with_pubtator(
    pmid: str,
    llm_entities: dict[str, list[str]],
) -> tuple[float, dict[str, Any], str]:
    """
    Compare LLM/heuristic entities to PubTator3.

    Returns (overlap_score, detail_dict, confidence_label).
    """
    try:
        pub = fetch_pubtator_entities(str(pmid).replace("PMID:", "").strip())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        return 0.0, {"error": str(exc)}, CONFIDENCE_LOW

    scores = {}
    for key in ("genes", "diseases", "chemicals"):
        llm_set = set(llm_entities.get(key) or [])
        pub_set = pub.get(key) or set()
        scores[key] = _jaccard(llm_set, pub_set)

    weights = {"genes": 0.4, "diseases": 0.4, "chemicals": 0.2}
    if not any(llm_entities.get(k) for k in weights):
        overlap = sum(scores.values()) / len(scores) if scores else 0.0
    else:
        overlap = sum(scores[k] * weights[k] for k in weights)

    detail = {
        "pmid": pmid,
        "llm": llm_entities,
        "pubtator": {k: sorted(v) for k, v in pub.items()},
        "scores": scores,
        "overlap": overlap,
    }
    if overlap > 0.7:
        label = CONFIDENCE_HIGH
    elif overlap >= 0.3:
        label = CONFIDENCE_MEDIUM
    else:
        label = CONFIDENCE_LOW
    return overlap, detail, label


def batch_pubtator_verify(
    findings: list[dict],
    sample_size: int = 50,
    delay_s: float = 0.35,
) -> dict:
    """Verify a sample of literature PMIDs against PubTator3."""
    literature = [
        f for f in findings
        if f.get("source_type") == "literature"
        and str(f.get("source_id", "")).replace("DEMO-", "").isdigit()
    ]
    if sample_size and len(literature) > sample_size:
        import random
        literature = random.sample(literature, sample_size)

    results = []
    overlaps = []
    for finding in literature:
        pmid = str(finding["source_id"]).replace("PMID:", "").strip()
        llm_ent = extract_entity_hints(finding)
        overlap, detail, label = compare_with_pubtator(pmid, llm_ent)
        overlaps.append(overlap)
        results.append({"source_id": pmid, "overlap": overlap, "confidence": label, "detail": detail})
        time.sleep(delay_s)

    gene_scores = [r["detail"].get("scores", {}).get("genes", 0) for r in results if "scores" in r.get("detail", {})]
    dis_scores = [r["detail"].get("scores", {}).get("diseases", 0) for r in results if "scores" in r.get("detail", {})]
    chem_scores = [r["detail"].get("scores", {}).get("chemicals", 0) for r in results if "scores" in r.get("detail", {})]

    avg = sum(overlaps) / len(overlaps) if overlaps else 0.0
    if avg > 0.7:
        overall = CONFIDENCE_HIGH
    elif avg >= 0.3:
        overall = CONFIDENCE_MEDIUM
    else:
        overall = CONFIDENCE_LOW

    return {
        "sampled": len(results),
        "average_overlap": avg,
        "confidence": overall,
        "genes_avg": sum(gene_scores) / len(gene_scores) if gene_scores else 0.0,
        "diseases_avg": sum(dis_scores) / len(dis_scores) if dis_scores else 0.0,
        "chemicals_avg": sum(chem_scores) / len(chem_scores) if chem_scores else 0.0,
        "results": results,
    }
