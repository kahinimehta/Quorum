"""
Stage 2: bioRxiv preprint pull with title deduplication against published set.

Preprints always get access_type='preprint', is_preprint=true, and JATS full text when available.
"""
from __future__ import annotations

import re
from typing import Any

from ingestion.biorxiv_mcp import search_biorxiv


def normalize_title(title: str | None) -> str:
    """Lowercase, strip punctuation, collapse whitespace for dedupe."""
    if not title:
        return ""
    t = title.lower()
    t = re.sub(r"[-–—]", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def title_is_duplicate(title: str | None, published_titles: set[str]) -> bool:
    """Return True if normalized title matches any published title."""
    norm = normalize_title(title)
    if not norm:
        return False
    return norm in published_titles


def pull_preprints(
    disease: str,
    since_year: int,
    max_items: int,
    published_titles: set[str],
    *,
    query: str | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """
    Search bioRxiv and return enriched items not duplicating published titles.

    Returns (enriched_items, stats).
    """
    from agents.fulltext import fetch_preprint_sections

    articles, source = search_biorxiv(disease, since_year, max_items * 3, query=query)
    stats: dict[str, Any] = {
        "search_source": source,
        "search_hits": len(articles),
        "deduped": 0,
        "enriched": 0,
    }
    enriched: list[dict] = []

    for article in articles:
        if title_is_duplicate(article.get("title"), published_titles):
            stats["deduped"] += 1
            continue
        doi = article.get("doi")
        if not doi:
            continue
        year = article.get("year")
        ft = fetch_preprint_sections(article.get("jatsxml"), article.get("abstract"))
        meta = {
            "source_type": "literature",
            "source_id": doi,
            "title": article.get("title"),
            "year": year,
            "publication_year": year,
            "venue": "bioRxiv",
            "url": article.get("url"),
            "doi": doi,
            "access_status": "abstract_only",
            "is_preprint": True,
        }
        enriched.append({
            "source_type": "literature",
            "raw": {
                "doi": doi,
                "title": article.get("title"),
                "abstract": article.get("abstract"),
                "year": year,
                "journal": "bioRxiv",
                "url": article.get("url"),
            },
            "meta": meta,
            "ft": ft,
        })
        published_titles.add(normalize_title(article.get("title")))
        if len(enriched) >= max_items:
            break

    stats["enriched"] = len(enriched)
    return enriched, stats
