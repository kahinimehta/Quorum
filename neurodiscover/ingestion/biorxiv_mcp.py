"""
bioRxiv search: optional MCP command (BIORXIV_MCP_COMMAND) or REST API fallback.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from ingestion.mcp_clients import try_mcp_search

BIORXIV_API = "https://api.biorxiv.org/details/biorxiv"
USER_AGENT = "NeuroDiscover/1.0 (hackathon; mailto:team@example.com)"


def _http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _matches_query(text: str, query: str, disease: str) -> bool:
    blob = (text or "").lower()
    if disease.lower() in blob:
        return True
    for token in re.split(r"\s+", query.lower()):
        if len(token) >= 3 and token in blob:
            return True
    return False


def search_biorxiv_api(
    *,
    query: str,
    max_items: int,
    since_year: int,
    disease: str = "Parkinson disease",
) -> list[dict]:
    """
    Fetch bioRxiv preprints in date windows and filter by keyword.

    API returns batches; we scan recent intervals client-side.
    """
    start = f"{since_year}-01-01"
    end = datetime.utcnow().strftime("%Y-%m-%d")
    cursor = 0
    collected: list[dict] = []
    keywords = query or disease

    while len(collected) < max_items and cursor < 3000:
        url = f"{BIORXIV_API}/{start}/{end}/{cursor}"
        try:
            data = json.loads(_http_get(url))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            break
        messages = data.get("messages") or []
        if messages and messages[0].get("status") == "no posts found":
            break
        collection = data.get("collection") or []
        if not collection:
            break
        for item in collection:
            title = item.get("title") or ""
            abstract = item.get("abstract") or ""
            if not _matches_query(f"{title} {abstract}", keywords, disease):
                continue
            doi = item.get("doi")
            version = item.get("version", "1")
            year = None
            date_str = item.get("date")
            if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
                year = int(date_str[:4])
            collected.append({
                "doi": doi,
                "source_id": doi,
                "title": title,
                "abstract": abstract,
                "year": year,
                "venue": "bioRxiv",
                "version": version,
                "jatsxml": item.get("jatsxml"),
                "url": f"https://www.biorxiv.org/content/{doi}v{version}" if doi else None,
                "server": item.get("server", "biorxiv"),
            })
            if len(collected) >= max_items:
                break
        cursor += len(collection)
        if len(collection) < 100:
            break
    return collected[:max_items]


def search_biorxiv(
    disease: str,
    since_year: int,
    max_items: int,
    *,
    query: str | None = None,
) -> tuple[list[dict], str]:
    """Search bioRxiv via MCP or API fallback."""
    effective_query = query or disease
    return try_mcp_search(
        "BIORXIV_MCP_COMMAND",
        query=effective_query,
        max_items=max_items,
        since_year=since_year,
        fallback=search_biorxiv_api,
        disease=disease,
    )
