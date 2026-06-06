"""
PubMed search: optional MCP command (PUBMED_MCP_COMMAND) or NCBI E-utilities fallback.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ingestion.mcp_clients import try_mcp_search

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "NeuroDiscover/1.0 (hackathon; mailto:team@example.com)"


def _http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _build_term(disease: str, query: str | None, gene: str | None, since_year: int) -> str:
    parts = [f'("{disease}"[Title/Abstract])']
    if query:
        parts.append(f"({query}[Title/Abstract])")
    if gene:
        parts.append(f"({gene}[Title/Abstract])")
    if since_year:
        parts.append(f'("{since_year}"[Date - Publication] : "3000"[Date - Publication])')
    return " AND ".join(parts)


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    articles: list[dict] = []
    for article in root.findall(".//PubmedArticle"):
        medline = article.find("MedlineCitation")
        if medline is None:
            continue
        pmid_el = medline.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else None
        art = medline.find("Article")
        if art is None:
            continue
        title_el = art.find("ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else None
        abstract_parts = []
        for ab in art.findall("Abstract/AbstractText"):
            label = ab.get("Label")
            text = "".join(ab.itertext()).strip()
            if label:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        abstract = "\n".join(abstract_parts) if abstract_parts else None
        journal_el = art.find("Journal/Title")
        venue = journal_el.text if journal_el is not None else None
        year = None
        pub_date = art.find("Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year_el = pub_date.find("Year")
            if year_el is not None and year_el.text and year_el.text.isdigit():
                year = int(year_el.text)
        doi = None
        for id_el in article.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi" and id_el.text:
                doi = id_el.text
                break
        if pmid:
            articles.append({
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "journal": venue,
                "year": year,
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })
    return articles


def search_pubmed_eutils(
    *,
    query: str,
    max_items: int,
    since_year: int,
    disease: str = "Parkinson disease",
    gene: str | None = None,
) -> list[dict]:
    """NCBI esearch + efetch for PubMed articles."""
    term = _build_term(disease, query or None, gene, since_year)
    esearch_params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": term,
        "retmax": max_items,
        "retmode": "json",
        "sort": "relevance",
    })
    try:
        es_data = json.loads(_http_get(f"{ESEARCH}?{esearch_params}"))
        idlist = es_data.get("esearchresult", {}).get("idlist") or []
        if not idlist:
            return []
        efetch_params = urllib.parse.urlencode({
            "db": "pubmed",
            "id": ",".join(idlist[:max_items]),
            "retmode": "xml",
        })
        xml_text = _http_get(f"{EFETCH}?{efetch_params}", timeout=60)
        return _parse_pubmed_xml(xml_text)[:max_items]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ET.ParseError):
        return []


def search_pubmed(
    disease: str,
    since_year: int,
    max_items: int,
    *,
    query: str | None = None,
    gene: str | None = None,
) -> tuple[list[dict], str]:
    """
    Search PubMed via MCP (if configured) or E-utilities.

    Returns (articles, source) where source is 'mcp' or 'api'.
    """
    effective_query = query or disease
    return try_mcp_search(
        "PUBMED_MCP_COMMAND",
        query=effective_query,
        max_items=max_items,
        since_year=since_year,
        fallback=search_pubmed_eutils,
        disease=disease,
        gene=gene,
    )


def article_to_raw_item(article: dict) -> dict:
    """Normalize PubMed hit to literature_agent raw item shape."""
    pmid = str(article.get("pmid") or article.get("PMID") or "").strip()
    year = article.get("year") or article.get("publication_year")
    if year is not None:
        try:
            year = int(year)
        except (TypeError, ValueError):
            year = None
    return {
        "source_type": "literature",
        "raw": {
            "pmid": pmid,
            "title": article.get("title"),
            "abstract": article.get("abstract") or article.get("abstractText"),
            "journal": article.get("journal") or article.get("venue"),
            "year": year,
            "doi": article.get("doi"),
            "url": article.get("url") or (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None),
        },
    }
