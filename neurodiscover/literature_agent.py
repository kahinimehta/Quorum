#!/usr/bin/env python3
"""
literature_agent.py — NeuroDiscover Literature Synthesis Agent (Person 4 slice, Ayelet)

What it does:
  1. PULL   manuscripts + clinical trials for the disease via BioMCP
            (BioMCP wraps PubMed + ClinicalTrials.gov behind one CLI).
  2. FETCH  abstract/metadata per hit (two-step; Anara-style access flags).
  3. EXTRACT each new source into structured findings via Nebius LLM.
  4. WRITE  findings into `evidence` (UNIQUE dedups re-pulls).
  5. LINK   auto-populate subgroup_evidence when subgroup name matches.
  6. TRACE  log to `agent_outputs`; update `scan_state` on incremental scans.

Modes:
  --demo            offline. Uses pre-seeded evidence; logs trace only.
  (default pull)    full backfill pull via BioMCP + Nebius.
  --incremental     scan mode: skip LLM for known source_ids (low cost).

Usage:
  python literature_agent.py --demo
  python literature_agent.py --disease "Parkinson disease" --since 2022 --max 10
  python literature_agent.py --query "GBA GCase lysosomal" --gene GBA --max 10
  python literature_agent.py --incremental --max 5
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

AGENT_NAME = "Literature Synthesis Agent"

SEED_SUBGROUP_NAMES = [
    "GBA-mutation PD",
    "LRRK2 PD",
    "Alpha-synuclein-high PD",
    "Inflammation-high PD",
    "Rapid motor progressors",
]

STUDY_TYPES = ("in vitro", "mouse", "cohort", "RCT", "Phase 2", "preclinical", "Phase 1", "Phase 3")

FINDING_FIELDS = [
    "source_type", "source_id", "title", "year", "venue", "subgroup",
    "mechanism", "treatment", "key_result", "study_type", "sample_size",
    "evidence_snippet", "url", "doi", "access_status",
]

EXTRACT_PROMPT = """You are extracting structured findings from a biomedical source for a \
Parkinson's disease subgroup-treatment discovery system.

Return ONLY a JSON object (no prose, no markdown) with these keys:
  subgroup         prefer one of these exact names when applicable, else null:
                   {subgroup_names}
  mechanism        biological mechanism, short phrase
  treatment        treatment / intervention, short phrase
  key_result       main finding in at most 2 sentences, no markdown
  study_type       one of: {study_types}
  sample_size      integer subjects/animals if stated, else null
  evidence_snippet verbatim phrase from the source, at most 15 words

Source type: {source_type}
Source text:
{source_text}
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _biomcp_executable() -> str:
    """Resolve BioMCP CLI (BIOMCP_BIN env, PATH, or repo .venv/bin/biomcp)."""
    if os.environ.get("BIOMCP_BIN"):
        return os.environ["BIOMCP_BIN"]
    found = shutil.which("biomcp")
    if found:
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    venv_bin = os.path.join(here, ".venv", "bin", "biomcp")
    if os.path.isfile(venv_bin):
        return venv_bin
    return "biomcp"


def _biomcp_cmd(*args: str) -> list[str]:
    return [_biomcp_executable(), *args]


def _run_biomcp(cmd: list[str], timeout: int = 120) -> dict | list | None:
    """Run a BioMCP CLI command and parse JSON stdout."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode != 0 and not out.stdout.strip():
            print(f"[warn] BioMCP failed: {' '.join(cmd)}: {out.stderr[:200]}", file=sys.stderr)
            return None
        if not out.stdout.strip():
            return None
        return json.loads(out.stdout)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] BioMCP error: {exc}", file=sys.stderr)
        return None


def _normalize_items(data) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("results") or data.get("studies") or data.get("articles") or []
    return []


def _item_year(item: dict) -> int | None:
    for key in ("year", "publication_year", "pub_year"):
        val = item.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
    return None


def _filter_since(items: list, since_year: int) -> list:
    if not since_year:
        return items
    filtered = []
    for it in items:
        yr = _item_year(it)
        if yr is None or yr >= since_year:
            filtered.append(it)
    return filtered


def _source_id_from_item(source_type: str, item: dict) -> str | None:
    """Return a real external id; never invent one for live pulls."""
    if source_type == "literature":
        for key in ("pmid", "PMID", "id"):
            val = item.get(key)
            if val:
                return str(val).replace("PMID:", "").strip()
        doi = item.get("doi") or item.get("DOI")
        if doi:
            return str(doi)
    if source_type == "trial":
        for key in ("nct_id", "nctId", "NCTId", "id"):
            val = item.get(key)
            if val:
                return str(val).upper().replace("NCT:", "").strip()
                # normalize to NCT format below
    return None


def _normalize_nct(raw: str) -> str:
    raw = raw.upper().replace("NCT:", "").strip()
    if raw.startswith("NCT"):
        return raw
    return f"NCT{raw}" if raw.isdigit() else raw


def _infer_access_status(item: dict, source_type: str) -> str:
    """Anara-style: open vs abstract-only vs restricted."""
    if source_type == "trial":
        return "open"  # ClinicalTrials.gov summaries are always accessible

    flags = (
        item.get("pmc_id"), item.get("pmcid"), item.get("PMCID"),
        item.get("pmc"), item.get("open_access"), item.get("is_open_access"),
        item.get("full_text_available"), item.get("has_full_text"),
    )
    if any(flags):
        return "open"
    if item.get("abstract") or item.get("abstractText"):
        return "abstract_only"
    return "restricted"


def _metadata_from_item(source_type: str, item: dict) -> dict:
    source_id = _source_id_from_item(source_type, item)
    if source_type == "trial" and source_id:
        source_id = _normalize_nct(source_id)

    doi = item.get("doi") or item.get("DOI")
    url = item.get("url")
    if not url and source_type == "literature" and source_id and source_id.isdigit():
        url = f"https://pubmed.ncbi.nlm.nih.gov/{source_id}/"
    if not url and source_type == "trial" and source_id:
        url = f"https://clinicaltrials.gov/study/{source_id}"

    return {
        "source_type": source_type,
        "source_id": source_id,
        "title": item.get("title") or item.get("brief_title") or item.get("BriefTitle"),
        "year": _item_year(item),
        "venue": (
            item.get("journal")
            or item.get("journalTitle")
            or ("ClinicalTrials.gov" if source_type == "trial" else None)
        ),
        "url": url,
        "doi": str(doi) if doi else None,
        "access_status": _infer_access_status(item, source_type),
    }


# ---------- 1. PULL via BioMCP ----------------------------------------
def _article_search_cmd(disease: str, query: str | None, gene: str | None) -> list[str]:
    cmd = _biomcp_cmd("article", "search", "--disease", disease, "--json")
    if query:
        cmd.extend(["--keyword", query])
    if gene:
        cmd.extend(["--gene", gene])
    return cmd


def _trial_search_cmd(disease: str, query: str | None) -> list[str]:
    cmd = _biomcp_cmd("trial", "search", "--condition", disease, "--json")
    if query:
        cmd.extend(["--keyword", query])
    return cmd


def pull_biomcp(
    disease: str,
    since_year: int,
    max_items: int,
    *,
    query: str | None = None,
    gene: str | None = None,
) -> list[dict]:
    """Search BioMCP for articles and trials; return list of {source_type, raw}."""
    raw = []
    searches = [
        ("literature", _article_search_cmd(disease, query, gene)),
        ("trial", _trial_search_cmd(disease, query)),
    ]
    for source_type, cmd in searches:
        data = _run_biomcp(cmd)
        items = _filter_since(_normalize_items(data), since_year)
        for it in items[:max_items]:
            raw.append({"source_type": source_type, "raw": it})
    return raw


def fetch_biomcp_detail(source_type: str, source_id: str) -> dict | None:
    """Two-step fetch: get abstract/metadata for one source id."""
    if source_type == "literature":
        cmd = _biomcp_cmd("article", "get", str(source_id), "--json")
    elif source_type == "trial":
        cmd = _biomcp_cmd("trial", "get", str(source_id), "--json")
    else:
        return None

    data = _run_biomcp(cmd, timeout=60)
    if isinstance(data, dict):
        return data.get("result") or data.get("article") or data.get("study") or data
    return None


def enrich_raw_item(raw_item: dict) -> dict | None:
    """Merge search hit with detail fetch when possible."""
    source_type = raw_item["source_type"]
    item = dict(raw_item["raw"])
    meta = _metadata_from_item(source_type, item)
    if not meta["source_id"]:
        return None

    detail = fetch_biomcp_detail(source_type, meta["source_id"])
    if detail:
        item.update({k: v for k, v in detail.items() if v is not None})
        meta = _metadata_from_item(source_type, item)

    if not meta["source_id"]:
        return None
    return {"source_type": source_type, "raw": item, "meta": meta}


# ---------- 2. EXTRACT via Nebius LLM ----------------------------------
def extract_finding(raw_item: dict, use_llm: bool = True) -> dict | None:
    """Turn one enriched source into a structured finding dict."""
    source_type = raw_item["source_type"]
    item = raw_item["raw"]
    meta = raw_item.get("meta") or _metadata_from_item(source_type, item)
    if not meta.get("source_id"):
        return None

    # Prefer title + abstract for LLM context (not entire JSON blob).
    abstract = item.get("abstract") or item.get("abstractText") or item.get("summary") or ""
    source_text = json.dumps(
        {"title": meta.get("title"), "abstract": abstract, "year": meta.get("year"),
         "journal": meta.get("venue"), "access_status": meta.get("access_status")},
        ensure_ascii=False,
    )[:6000]

    finding = {f: None for f in FINDING_FIELDS}
    finding.update(meta)

    if use_llm:
        llm = _llm_extract(source_type, source_text)
        if llm:
            for k in ("subgroup", "mechanism", "treatment", "key_result",
                      "study_type", "sample_size", "evidence_snippet"):
                if llm.get(k) is not None:
                    finding[k] = llm[k]

    return finding


def _resolve_extract_backend() -> str:
    explicit = os.environ.get("EXTRACT_BACKEND", "").lower().strip()
    if explicit in ("nebius", "ollama", "none"):
        return explicit
    if os.environ.get("NEBIUS_API_KEY") and os.environ.get("NEBIUS_BASE_URL"):
        return "nebius"
    if os.environ.get("OLLAMA_HOST") or os.environ.get("OLLAMA_MODEL"):
        return "ollama"
    return "none"


def _format_extract_prompt(source_type: str, source_text: str) -> str:
    return EXTRACT_PROMPT.format(
        source_type=source_type,
        source_text=source_text,
        subgroup_names=", ".join(SEED_SUBGROUP_NAMES),
        study_types=", ".join(STUDY_TYPES),
    )


def _parse_llm_json(text: str) -> dict | None:
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def _nebius_extract(source_type: str, source_text: str) -> dict | None:
    """Call the Nebius (OpenAI-compatible) chat API. Returns parsed JSON or None."""
    api_key = os.environ.get("NEBIUS_API_KEY")
    base_url = os.environ.get("NEBIUS_BASE_URL")
    model = os.environ.get("NEBIUS_MODEL")
    if not (api_key and base_url and model):
        print("[warn] NEBIUS_* env not set; skipping Nebius extraction", file=sys.stderr)
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _format_extract_prompt(source_type, source_text)}],
            temperature=0,
        )
        return _parse_llm_json(resp.choices[0].message.content.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Nebius extraction failed: {exc}", file=sys.stderr)
        return None


def _ollama_extract(source_type: str, source_text: str) -> dict | None:
    """Call a local Ollama server. Returns parsed JSON or None."""
    try:
        from ollama import Client
    except ImportError:
        print("[warn] ollama package not installed; pip install ollama", file=sys.stderr)
        return None

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "mistral")
    try:
        client = Client(host=host)
        resp = client.chat(
            model=model,
            messages=[{"role": "user", "content": _format_extract_prompt(source_type, source_text)}],
            options={"temperature": 0},
        )
        content = resp.get("message", {}).get("content") or ""
        return _parse_llm_json(content.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Ollama extraction failed: {exc}", file=sys.stderr)
        return None


def _llm_extract(source_type: str, source_text: str) -> dict | None:
    backend = _resolve_extract_backend()
    if backend == "none":
        print("[warn] EXTRACT_BACKEND=none; skipping LLM extraction", file=sys.stderr)
        return None
    if backend == "ollama":
        return _ollama_extract(source_type, source_text)
    return _nebius_extract(source_type, source_text)


# ---------- 3. WRITE to DB ---------------------------------------------
def evidence_exists(conn, source_type: str, source_id: str) -> bool:
    conn.execute(
        "SELECT 1 AS ok FROM evidence WHERE source_type = ? AND source_id = ?",
        (source_type, source_id),
    )
    return conn.fetchone() is not None


def touch_evidence_scan(conn, source_type: str, source_id: str) -> None:
    conn.execute(
        "UPDATE evidence SET last_scanned_at = ? WHERE source_type = ? AND source_id = ?",
        (_now_iso(), source_type, source_id),
    )


def upsert_evidence(conn, finding: dict) -> bool:
    """Insert one finding. UNIQUE(source_type, source_id) dedups. Returns True if new."""
    from db import is_postgres

    cols = ", ".join(FINDING_FIELDS)
    qs = ", ".join("?" for _ in FINDING_FIELDS)
    vals = tuple(finding.get(k) for k in FINDING_FIELDS) + (_now_iso(),)
    if is_postgres():
        conn.execute(
            f"INSERT INTO evidence ({cols}, last_scanned_at) VALUES ({qs}, ?) "
            f"ON CONFLICT (source_type, source_id) DO NOTHING RETURNING evidence_id",
            vals,
        )
        return conn.fetchone() is not None
    conn.execute(
        f"INSERT OR IGNORE INTO evidence ({cols}, last_scanned_at) VALUES ({qs}, ?)",
        vals,
    )
    return conn.rowcount > 0


def link_subgroup_evidence(conn, finding: dict) -> None:
    """Auto-link evidence to subgroups when subgroup name matches."""
    from db import insert_ignore_sql

    sg = finding.get("subgroup")
    if not sg:
        return
    conn.execute(
        "SELECT evidence_id FROM evidence WHERE source_type = ? AND source_id = ?",
        (finding["source_type"], finding["source_id"]),
    )
    row = conn.fetchone()
    conn.execute("SELECT subgroup_id FROM subgroups WHERE name = ?", (sg,))
    sg_row = conn.fetchone()
    if row and sg_row:
        conn.execute(
            insert_ignore_sql(
                "subgroup_evidence", ["subgroup_id", "evidence_id"],
                ["subgroup_id", "evidence_id"],
            ),
            (sg_row["subgroup_id"], row["evidence_id"]),
        )


def get_scan_state(conn) -> dict:
    conn.execute(
        "SELECT disease, last_scan_at, last_run_id FROM scan_state WHERE id = 1"
    )
    row = conn.fetchone()
    if not row:
        return {"disease": "Parkinson disease", "last_scan_at": None, "last_run_id": None}
    last = row.get("last_scan_at")
    return {
        "disease": row["disease"],
        "last_scan_at": str(last) if last is not None else None,
        "last_run_id": row.get("last_run_id"),
    }


def update_scan_state(conn, disease: str, run_id: str) -> None:
    conn.execute(
        "UPDATE scan_state SET disease = ?, last_scan_at = ?, last_run_id = ? WHERE id = 1",
        (disease, _now_iso(), run_id),
    )


# ---------- 4. TRACE ----------------------------------------------------
def log_trace(conn, run_id, step, summary, payload=None):
    conn.execute(
        "INSERT INTO agent_outputs (run_id, agent_name, step_order, summary, payload) "
        "VALUES (?,?,?,?,?)",
        (run_id, AGENT_NAME, step, summary, json.dumps(payload) if payload else None),
    )


# ---------- orchestration ----------------------------------------------
def run(
    db_path,
    disease,
    since_year,
    max_items,
    demo,
    incremental=False,
    *,
    query=None,
    gene=None,
):
    from db import backend_label, connect

    run_id = str(uuid.uuid4())[:8]

    with connect(db_path) as conn:
        if demo:
            conn.execute("SELECT COUNT(*) AS n FROM evidence")
            n = conn.fetchone()["n"]
            log_trace(conn, run_id, 1,
                      f"Demo mode: synthesized {n} pre-seeded evidence rows for {disease}.")
            conn.commit()
            print(f"[demo] {backend_label()} — {n} evidence rows. run_id={run_id}")
            return

        scan = get_scan_state(conn)
        effective_since = since_year
        if incremental and scan.get("last_scan_at"):
            last_at = scan["last_scan_at"]
            try:
                if hasattr(last_at, "year"):
                    effective_since = max(since_year, last_at.year)
                else:
                    last = datetime.fromisoformat(str(last_at).replace(" ", "T")[:19])
                    effective_since = max(since_year, last.year)
            except (ValueError, TypeError):
                pass

        raw_hits = pull_biomcp(
            disease, effective_since, max_items, query=query, gene=gene,
        )
        log_trace(
            conn, run_id, 1,
            f"Pulled {len(raw_hits)} raw sources via BioMCP for {disease}.",
            {
                "since_year": effective_since,
                "incremental": incremental,
                "query": query,
                "gene": gene,
            },
        )

        new = 0
        skipped = 0
        touched = 0
        rejected = 0

        for hit in raw_hits:
            enriched = enrich_raw_item(hit)
            if not enriched:
                rejected += 1
                continue

            meta = enriched["meta"]
            st, sid = meta["source_type"], meta["source_id"]

            if evidence_exists(conn, st, sid):
                touch_evidence_scan(conn, st, sid)
                skipped += 1
                touched += 1
                continue

            finding = extract_finding(enriched, use_llm=True)
            if not finding:
                rejected += 1
                continue

            if upsert_evidence(conn, finding):
                link_subgroup_evidence(conn, finding)
                new += 1

        update_scan_state(conn, disease, run_id)
        payload = {
            "new_evidence": new,
            "skipped_duplicates": skipped,
            "touched_existing": touched,
            "rejected_no_id": rejected,
            "since_year": effective_since,
            "incremental": incremental,
            "query": query,
            "gene": gene,
            "extract_backend": _resolve_extract_backend(),
        }
        log_trace(conn, run_id, 2,
                  f"Stored {new} new evidence rows ({skipped} existing skipped, {rejected} rejected).",
                  payload)
        conn.commit()
        mode = "scan" if incremental else "pull"
        print(f"[{mode}] {backend_label()} — stored {new} new, skipped {skipped}. run_id={run_id}")


if __name__ == "__main__":
    from paths import default_db_path

    p = argparse.ArgumentParser()
    p.add_argument("--db", default=default_db_path())
    p.add_argument("--disease", default="Parkinson disease")
    p.add_argument("--query", default=None,
                   help="refine BioMCP search (mechanism, phenotype, treatment)")
    p.add_argument("--prompt", default=None, dest="query",
                   help="alias for --query")
    p.add_argument("--gene", default=None, help="optional gene filter for article search")
    p.add_argument("--since", type=int, default=2020)
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--demo", action="store_true", help="offline: use seeded evidence")
    p.add_argument("--incremental", action="store_true",
                   help="incremental scan: skip LLM for known source_ids")
    a = p.parse_args()
    run(a.db, a.disease, a.since, a.max, a.demo, a.incremental,
        query=a.query, gene=a.gene)
