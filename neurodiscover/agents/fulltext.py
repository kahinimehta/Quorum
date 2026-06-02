"""
Full-text resolution for published papers and preprints.

Chain for published PMIDs:
  NCBI PMC XML → Europe PMC fullTextXML → Unpaywall (if UNPAYWALL_EMAIL) → published_paywalled
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from agents.access_types import normalize_access_type

EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
USER_AGENT = "NeuroDiscover/1.0 (hackathon; mailto:team@example.com)"
SECTION_LIMITS = {"methods": 2000, "results": 2000, "discussion": 1000}

# Headings tolerate leading markdown #'s and section numbering ("## Methods", "2. Methods")
# so the same patterns work on XML-stripped text AND Docling markdown output.
_H = r"\n[#>\s]*(?:\d+(?:\.\d+)*\.?\s+)?"
SECTION_PATTERNS = {
    "methods": re.compile(
        _H + r"(?:methods|materials\s+and\s+methods|patients\s+and\s+methods|"
        r"subjects\s+and\s+methods|experimental\s+(?:procedures|section|methods))"
        r"\s*[:\.]?\s*\n",
        re.IGNORECASE,
    ),
    "results": re.compile(
        _H + r"(?:results|findings|results\s+and\s+discussion)\s*[:\.]?\s*\n",
        re.IGNORECASE,
    ),
    "discussion": re.compile(
        _H + r"(?:discussion|conclusions?|concluding\s+remarks)\s*[:\.]?\s*\n",
        re.IGNORECASE,
    ),
    "next_section": re.compile(
        _H + r"(?:introduction|background|results|discussion|conclusions?|references|"
        r"acknowledg|methods|materials|funding|author\s+contributions|data\s+availability|"
        r"supplementary|abbreviations)",
        re.IGNORECASE,
    ),
}


def _pmid_digits(pmid: str) -> str | None:
    raw = str(pmid).replace("PMID:", "").strip()
    return raw if raw.isdigit() else None


def _http_get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _pick_open_text_url(hit: dict) -> str | None:
    for entry in hit.get("fullTextUrlList", {}).get("fullTextUrl") or []:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("availabilityCode", "")).upper()
        avail = str(entry.get("availability", "")).lower()
        if code == "OA" or "open access" in avail:
            return entry.get("url")
    pmcid = hit.get("pmcid")
    if pmcid:
        return f"https://europepmc.org/articles/{pmcid}"
    return None


def check_access_status(pmid: str) -> tuple[bool, str | None, str | None, str | None]:
    """
    Query Europe PMC for open-access status.

    Returns (is_open_access, full_text_url, pmcid, error_message).
    """
    digits = _pmid_digits(pmid)
    if not digits:
        return False, None, None, "not a numeric PMID"

    query = urllib.parse.urlencode({
        "query": f"EXT_ID:{digits}",
        "format": "json",
        "resultType": "core",
    })
    url = f"{EPMC_SEARCH}?{query}"
    try:
        data = json.loads(_http_get(url, timeout=20))
        results = (data.get("resultList") or {}).get("result") or []
        if not results:
            return False, None, None, "no Europe PMC hit"
        hit = results[0]
        is_oa = str(hit.get("isOpenAccess", "")).upper() == "Y"
        pmcid = hit.get("pmcid")
        ft_url = _pick_open_text_url(hit) if is_oa else None
        return is_oa, ft_url, pmcid, None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, None, None, str(exc)


def _slice_section(text: str, start_pat: re.Pattern, max_chars: int) -> str | None:
    m = start_pat.search(text)
    if not m:
        return None
    start = m.end()
    tail = text[start:]
    end_m = SECTION_PATTERNS["next_section"].search(tail)
    chunk = tail[: end_m.start()] if end_m else tail
    chunk = re.sub(r"\s+", " ", chunk).strip()
    if not chunk:
        return None
    return chunk[:max_chars]


def _normalize_fulltext(full_text: str) -> str:
    if "<" in full_text and ">" in full_text:
        full_text = re.sub(r"<[^>]+>", "\n", full_text)
    return "\n" + full_text.replace("\r", "\n")


def _parse_sections_from_text(full_text: str) -> dict[str, str | None]:
    normalized = _normalize_fulltext(full_text)
    return {
        "methods_text": _slice_section(normalized, SECTION_PATTERNS["methods"], SECTION_LIMITS["methods"]),
        "results_text": _slice_section(normalized, SECTION_PATTERNS["results"], SECTION_LIMITS["results"]),
        "discussion_text": _slice_section(
            normalized, SECTION_PATTERNS["discussion"], SECTION_LIMITS["discussion"]
        ),
    }


def extract_sections_from_fulltext(full_text: str) -> dict[str, str | None]:
    """Public alias for section regex extraction from raw/XML full text."""
    return _parse_sections_from_text(full_text)


def _fetch_ncbi_pmc_xml(pmcid: str) -> str | None:
    pid = pmcid.replace("PMC", "").strip()
    params = urllib.parse.urlencode({
        "db": "pmc",
        "id": f"PMC{pid}",
        "retmode": "xml",
    })
    try:
        return _http_get(f"{NCBI_EFETCH}?{params}", timeout=45)
    except Exception:  # noqa: BLE001
        return None


def unpaywall_lookup(doi: str) -> tuple[str | None, str | None]:
    """
    Return (best_oa_url, error) via Unpaywall when UNPAYWALL_EMAIL is set.
    """
    email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
    if not email or not doi:
        return None, "UNPAYWALL_EMAIL or doi missing"
    encoded = urllib.parse.quote(doi, safe="")
    url = f"{UNPAYWALL_API}/{encoded}?email={urllib.parse.quote(email)}"
    try:
        data = json.loads(_http_get(url, timeout=20))
        if not data.get("is_oa"):
            return None, "not open access per Unpaywall"
        loc = data.get("best_oa_location") or {}
        oa_url = loc.get("url_for_pdf") or loc.get("url")
        return oa_url, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _looks_like_pdf_url(url: str) -> bool:
    u = url.lower()
    return u.endswith(".pdf") or "/pdf" in u or "type=printable" in u


_DOCLING_CONVERTER = None


def _docling_pdf_to_markdown(url: str) -> str | None:
    """Parse a scientific PDF into section-headed markdown via Docling.

    INGESTION-ONLY and OPTIONAL: docling is imported lazily so the demo/MVP (which
    only reads Supabase) never needs it. If docling isn't installed, we skip PDF
    parsing gracefully (the row keeps its abstract). Install via requirements-ingest.txt.
    """
    global _DOCLING_CONVERTER
    try:
        if _DOCLING_CONVERTER is None:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            # Digital scientific PDFs are text-based: skip OCR + table structure.
            # This drops the heavy OCR/vision models (much lower memory + faster) and
            # is plenty for extracting Methods/Results/Discussion text.
            opts = PdfPipelineOptions()
            opts.do_ocr = False
            opts.do_table_structure = False
            _DOCLING_CONVERTER = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
            )
    except ImportError:
        print("[warn] docling not installed; skipping PDF parse "
              "(pip install -r requirements-ingest.txt)", file=sys.stderr)
        return None
    try:
        result = _DOCLING_CONVERTER.convert(url)
        return result.document.export_to_markdown()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] docling parse failed for {url}: {exc}", file=sys.stderr)
        return None


def _fetch_source_text(url: str) -> str | None:
    """Return full-text (XML/HTML as text, or PDF→markdown via Docling). Non-http
    inputs are treated as already-fetched text."""
    if not url.startswith("http"):
        return url
    if _looks_like_pdf_url(url):
        return _docling_pdf_to_markdown(url)
    body = _http_get(url, timeout=45)
    if body[:5] == "%PDF-":  # PDF served without a .pdf URL
        return _docling_pdf_to_markdown(url)
    return body


def fetch_and_parse_sections(
    pmid: str,
    full_text_url: str | None = None,
    pmcid: str | None = None,
    doi: str | None = None,
) -> tuple[str | None, str | None, str | None, str, str | None]:
    """
    Download full text and extract Methods / Results / Discussion excerpts.

    Chain: NCBI PMC XML → Europe PMC fullTextXML → Unpaywall PDF/HTML.

    Returns (methods_text, results_text, discussion_text, access_type, error).
    """
    digits = _pmid_digits(pmid) if pmid else None

    sources: list[tuple[str, str]] = []
    if pmcid:
        pid = pmcid.replace("PMC", "").strip()
        ncbi = _fetch_ncbi_pmc_xml(pid)
        if ncbi:
            sources.append(("ncbi_pmc", ncbi))
        sources.append((
            "epmc_pmc",
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{pid}/fullTextXML",
        ))
    if digits:
        sources.append((
            "epmc_med",
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/MED/{digits}/fullTextXML",
        ))
    if full_text_url:
        sources.append(("epmc_url", full_text_url))

    oa_url, _ = unpaywall_lookup(doi) if doi else (None, None)
    if oa_url:
        sources.append(("unpaywall", oa_url))

    last_err = None
    for _label, url in sources:
        try:
            body = _fetch_source_text(url)
            if not body:
                last_err = "no body fetched"
                continue
            sections = _parse_sections_from_text(body)
            if any(sections.values()):
                return (
                    sections["methods_text"],
                    sections["results_text"],
                    sections["discussion_text"],
                    "published_oa",
                    None,
                )
            last_err = "no sections parsed from full text"
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
    return None, None, None, "error", last_err


def fetch_preprint_sections(
    jatsxml_url: str | None,
    abstract: str | None = None,
    pdf_url: str | None = None,
) -> dict[str, Any]:
    """Extract preprint sections: try JATS XML, then the PDF via Docling (bioRxiv
    often 403s the JATS endpoint but serves the PDF), else fall back to abstract."""
    out: dict[str, Any] = {
        "methods_text": None,
        "results_text": None,
        "discussion_text": None,
        "access_type": "preprint",
        "full_text_url": jatsxml_url or pdf_url,
    }
    if jatsxml_url:
        try:
            body = _http_get(jatsxml_url, timeout=45)
            sections = _parse_sections_from_text(body)
            out.update(sections)
            if any(sections.values()):
                return out
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] preprint JATS fetch: {exc}", file=sys.stderr)
    if pdf_url:  # bioRxiv PDF via Docling (works when JATS is blocked)
        md = _docling_pdf_to_markdown(pdf_url)
        if md:
            sections = _parse_sections_from_text(md)
            if any(sections.values()):
                out.update(sections)
                out["full_text_url"] = pdf_url
                return out
    if abstract:
        out["results_text"] = abstract[:2000]
    return out


def access_type_from_epmc(
    pmid: str, retries: int = 1,
) -> tuple[str, str | None, str | None, str | None]:
    """
    Return (access_type, full_text_url, pmcid, error).

    access_type: published_oa | published_paywalled | error | unknown
    """
    last_err = None
    for attempt in range(retries + 1):
        is_oa, ft_url, pmcid, err = check_access_status(pmid)
        if err:
            last_err = err
            if attempt < retries:
                time.sleep(0.5)
                continue
            return "error", None, None, err
        if is_oa:
            return "published_oa", ft_url, pmcid, None
        return "published_paywalled", None, pmcid, None
    return "error", None, None, last_err


def resolve_published_access(
    pmid: str,
    doi: str | None = None,
    with_fulltext: bool = False,
) -> dict[str, Any]:
    """
    Full fallback chain for published papers.

    Europe PMC OA check → section download → Unpaywall → published_paywalled.
    """
    access_type, ft_url, pmcid, err = access_type_from_epmc(pmid, retries=1)
    out: dict[str, Any] = {
        "access_type": normalize_access_type(access_type),
        "full_text_url": ft_url,
        "methods_text": None,
        "results_text": None,
        "discussion_text": None,
    }
    if err:
        print(f"[warn] Europe PMC {pmid}: {err}", file=sys.stderr)

    if with_fulltext:
        m, r, d, ft_at, perr = fetch_and_parse_sections(
            pmid, full_text_url=ft_url, pmcid=pmcid, doi=doi,
        )
        if any((m, r, d)):
            out["methods_text"] = m
            out["results_text"] = r
            out["discussion_text"] = d
            out["access_type"] = normalize_access_type(ft_at)
        elif out["access_type"] == "published_paywalled":
            oa_url, uerr = unpaywall_lookup(doi) if doi else (None, None)
            if oa_url:
                out["full_text_url"] = oa_url
                m2, r2, d2, ft_at2, perr2 = fetch_and_parse_sections(
                    pmid, full_text_url=oa_url, pmcid=pmcid, doi=doi,
                )
                if any((m2, r2, d2)):
                    out["methods_text"] = m2
                    out["results_text"] = r2
                    out["discussion_text"] = d2
                    out["access_type"] = "published_oa"
                elif perr2 and uerr:
                    print(f"[warn] Unpaywall sections {pmid}: {perr2}", file=sys.stderr)
        if perr and not any((out.get("methods_text"), out.get("results_text"))):
            print(f"[warn] section parse {pmid}: {perr}", file=sys.stderr)

    return out


def resolve_access_and_sections(pmid: str, with_fulltext: bool = False, doi: str | None = None) -> dict[str, Any]:
    """Backward-compatible wrapper for published PMID resolution."""
    return resolve_published_access(pmid, doi=doi, with_fulltext=with_fulltext)
