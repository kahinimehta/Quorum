"""
Stage 1: published literature pull (PubMed → full-text fallback chain).

Uses ingestion/pubmed_mcp.py (MCP or E-utilities), agents/fulltext.py for access.
Falls back to BioMCP when E-utilities returns nothing and BioMCP is available.
"""
from __future__ import annotations

import sys
from typing import Any

from ingestion.pubmed_mcp import article_to_raw_item, search_pubmed


def _metadata_from_raw(source_type: str, item: dict) -> dict:
    """Minimal metadata compatible with literature_agent._metadata_from_item."""
    pmid = str(item.get("pmid") or item.get("PMID") or "").replace("PMID:", "").strip()
    source_id = pmid or item.get("doi")
    year = item.get("year") or item.get("publication_year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None
    url = item.get("url")
    if not url and pmid and pmid.isdigit():
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    return {
        "source_type": source_type,
        "source_id": source_id,
        "title": item.get("title"),
        "year": year,
        "publication_year": year,
        "venue": item.get("journal") or item.get("venue"),
        "url": url,
        "doi": item.get("doi"),
        "access_status": "abstract_only",
        "is_preprint": False,
    }


def pull_published(
    disease: str,
    since_year: int,
    max_items: int,
    *,
    query: str | None = None,
    gene: str | None = None,
    with_fulltext: bool = False,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Search PubMed and enrich each hit with access/sections metadata.

    Returns (enriched_items, stats) where each item has source_type, raw, meta,
    and optional ft_* fields from fulltext resolution.
    """
    from agents.fulltext import resolve_published_access

    articles, source = search_pubmed(
        disease, since_year, max_items, query=query, gene=gene,
    )
    stats: dict[str, Any] = {
        "search_source": source,
        "search_hits": len(articles),
        "enriched": 0,
    }

    if not articles:
        # Fallback to BioMCP if direct search empty
        try:
            from agents.literature_agent import enrich_raw_item, pull_biomcp

            biomcp_hits = pull_biomcp(disease, since_year, max_items, query=query, gene=gene)
            lit_hits = [h for h in biomcp_hits if h["source_type"] == "literature"]
            if lit_hits:
                stats["search_source"] = "biomcp_fallback"
                enriched = []
                for hit in lit_hits:
                    e = enrich_raw_item(hit)
                    if e:
                        enriched.append(e)
                stats["enriched"] = len(enriched)
                return enriched[:max_items], stats
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] BioMCP fallback failed: {exc}", file=sys.stderr)
        return [], stats

    enriched: list[dict] = []
    for article in articles:
        raw_item = article_to_raw_item(article)
        item = raw_item["raw"]
        meta = _metadata_from_raw("literature", item)
        if not meta.get("source_id"):
            continue
        pmid = str(meta["source_id"]).replace("PMID:", "").strip()
        ft: dict[str, Any] = {}
        if pmid.isdigit():
            ft = resolve_published_access(
                pmid,
                doi=meta.get("doi"),
                with_fulltext=with_fulltext,
            )
        enriched.append({
            "source_type": "literature",
            "raw": item,
            "meta": meta,
            "ft": ft,
        })
    stats["enriched"] = len(enriched)
    return enriched[:max_items], stats
