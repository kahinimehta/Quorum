#!/usr/bin/env python3
"""
research_agent.py — ReAct evidence-gathering agent (tool-using LLM loop).

Given a research goal, searches literature/trials, optionally fetches full text,
extracts findings, and writes to `evidence` + `subgroup_evidence`. Reuses
literature_agent / ingestion / fulltext — no duplicate search or DB logic.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

AGENT_NAME = "Evidence Research Agent"
DEFAULT_DISEASE = "Parkinson disease"
DEFAULT_SINCE_YEAR = 2020

REACT_SYSTEM = """You are an autonomous biomedical evidence research agent for \
Parkinson's disease subgroup–treatment discovery.

You must reply with ONLY a single JSON object (no markdown, no prose).

Available actions (use key "action" and "args"):
  search_literature  args: query (string), max (int, default 20)
  search_trials      args: query (string, optional), max (int, default 20)
  fetch_fulltext     args: source_id (PMID string), doi (optional string)
  query_db           args: sql (single SELECT only)
  save_evidence      args: source_id (string from a prior search)

When finished, reply with: {"done": true, "summary": "..."}

Rules:
- Only use source_id / NCT ids returned by search tools — never invent ids.
- Call save_evidence for the best sources (aim for several strong papers/trials).
- Use query_db to see what is already in the database before duplicating work.
- fetch_fulltext is expensive; use it when abstract is insufficient.
"""

REACT_USER_TEMPLATE = """Research goal:
{goal}

Scratchpad (previous steps):
{scratchpad}

What is the next JSON action?"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_action_json(text: str) -> dict | None:
    """Lenient JSON parse for model replies (one retry handled by caller)."""
    from agents.literature_agent import _parse_llm_json

    text = (text or "").strip()
    if not text:
        return None
    try:
        return _parse_llm_json(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _nebius_chat(user_content: str) -> str | None:
    api_key = os.environ.get("NEBIUS_API_KEY")
    base_url = os.environ.get("NEBIUS_BASE_URL")
    model = os.environ.get("NEBIUS_MODEL")
    if not (api_key and base_url and model):
        print("[warn] NEBIUS_* env not set; cannot plan research steps", file=sys.stderr)
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": REACT_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Nebius planner failed: {exc}", file=sys.stderr)
        return None


def _is_readonly_select(sql: str) -> bool:
    s = sql.strip().rstrip(";")
    if ";" in s:
        return False
    if not re.match(r"(?is)^\s*select\b", s):
        return False
    forbidden = re.compile(
        r"(?is)\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma)\b"
    )
    return forbidden.search(s) is None


def log_trace(conn, run_id: str, step: int, summary: str, payload: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO agent_outputs (run_id, agent_name, step_order, summary, payload) "
        "VALUES (?,?,?,?,?)",
        (run_id, AGENT_NAME, step, summary, json.dumps(payload) if payload else None),
    )


class ResearchTools:
    """Thin tool layer over ingestion, literature_agent, and fulltext."""

    def __init__(
        self,
        conn,
        *,
        disease: str = DEFAULT_DISEASE,
        since_year: int = DEFAULT_SINCE_YEAR,
    ) -> None:
        self.conn = conn
        self.disease = disease
        self.since_year = since_year
        self._cache: dict[tuple[str, str], dict] = {}

    def _put_hit(self, source_type: str, item: dict) -> dict | None:
        from agents.literature_agent import _metadata_from_item, _normalize_trial_item

        if source_type == "trial":
            item = _normalize_trial_item(item)
        meta = _metadata_from_item(source_type, item)
        sid = meta.get("source_id")
        if not sid:
            return None
        key = (source_type, str(sid))
        self._cache[key] = {"source_type": source_type, "raw": item, "meta": meta}
        abstract = item.get("abstract") or item.get("abstractText") or item.get("summary") or ""
        access_type = meta.get("access_status") or "abstract_only"
        return {
            "source_type": source_type,
            "source_id": sid,
            "title": meta.get("title"),
            "year": meta.get("year"),
            "abstract": (abstract[:500] + "…") if len(abstract) > 500 else abstract,
            "access_type": access_type,
        }

    def _lookup(self, source_id: str) -> dict | None:
        sid = str(source_id).strip()
        for key, val in self._cache.items():
            if key[1] == sid or key[1].replace("PMID:", "") == sid.replace("PMID:", ""):
                return val
        return None

    def search_literature(self, query: str, max: int = 20) -> list[dict]:  # noqa: A002
        from ingestion.pubmed_mcp import article_to_raw_item, search_pubmed

        out: list[dict] = []
        articles, _src = search_pubmed(
            self.disease, self.since_year, max, query=query,
        )
        for article in articles:
            raw_item = article_to_raw_item(article)
            row = self._put_hit("literature", raw_item["raw"])
            if row:
                out.append(row)
        if len(out) < max:
            try:
                from ingestion.biorxiv_mcp import search_biorxiv

                preprints, _ = search_biorxiv(
                    self.disease, self.since_year, max - len(out), query=query,
                )
                for article in preprints:
                    raw = {
                        "doi": article.get("doi"),
                        "title": article.get("title"),
                        "abstract": article.get("abstract"),
                        "year": article.get("year"),
                        "is_preprint": True,
                    }
                    row = self._put_hit("literature", raw)
                    if row:
                        out.append(row)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] bioRxiv search skipped: {exc}", file=sys.stderr)
        return out[:max]

    def search_trials(self, query: str | None = None, max: int = 20) -> list[dict]:  # noqa: A002
        from agents.literature_agent import pull_biomcp

        hits = pull_biomcp(self.disease, self.since_year, max, query=query)
        out: list[dict] = []
        for hit in hits:
            if hit.get("source_type") != "trial":
                continue
            row = self._put_hit("trial", hit["raw"])
            if row:
                out.append(row)
        return out[:max]

    def fetch_fulltext(self, source_id: str, doi: str | None = None) -> dict:
        pmid = str(source_id).replace("PMID:", "").strip()
        if not pmid.isdigit():
            return {"error": "fetch_fulltext requires a numeric PMID from search_literature"}
        from agents.fulltext import resolve_published_access

        ft = resolve_published_access(pmid, doi=doi, with_fulltext=True)
        cached = self._lookup(source_id)
        if cached:
            cached["ft"] = ft
        return {
            "source_id": pmid,
            "access_type": ft.get("access_type"),
            "methods_text": (ft.get("methods_text") or "")[:400] or None,
            "results_text": (ft.get("results_text") or "")[:400] or None,
            "discussion_text": (ft.get("discussion_text") or "")[:400] or None,
        }

    def query_db(self, sql: str) -> list[dict]:
        if not _is_readonly_select(sql):
            return [{"error": "Only a single read-only SELECT is allowed"}]
        from db import is_postgres

        # psycopg treats a literal '%' (e.g. LIKE '%GBA%') as a placeholder, so
        # escape it to '%%' for Postgres. The LLM writes raw literal SQL (no params).
        q = sql.replace("%", "%%") if is_postgres() else sql
        self.conn.execute(q)
        return [dict(r) for r in self.conn.fetchall()]

    def save_evidence(self, source_id: str) -> dict:
        from agents.literature_agent import (
            enrich_raw_item,
            evidence_exists,
            extract_finding,
            link_subgroup_evidence,
            upsert_evidence,
        )

        cached = self._lookup(source_id)
        if not cached:
            return {"ok": False, "error": f"unknown source_id {source_id!r}; search first"}

        st = cached["source_type"]
        sid = cached["meta"]["source_id"]
        if evidence_exists(self.conn, st, sid):
            return {"ok": True, "duplicate": True, "source_id": sid}

        enriched = enrich_raw_item(cached) or cached
        if cached.get("ft"):
            enriched["ft"] = cached["ft"]
        finding = extract_finding(enriched, use_llm=True, with_fulltext=bool(cached.get("ft")))
        if not finding:
            return {"ok": False, "error": "extraction produced no finding"}
        is_new = upsert_evidence(self.conn, finding)
        link_subgroup_evidence(self.conn, finding)
        self.conn.commit()
        return {
            "ok": True,
            "new": is_new,
            "duplicate": not is_new,
            "source_id": sid,
            "title": finding.get("title"),
            "subgroup": finding.get("subgroup"),
        }


def _execute_tool(tools: ResearchTools, action: str, args: dict) -> Any:
    args = args or {}
    if action == "search_literature":
        return tools.search_literature(args.get("query", ""), int(args.get("max", 20)))
    if action == "search_trials":
        return tools.search_trials(args.get("query"), int(args.get("max", 20)))
    if action == "fetch_fulltext":
        return tools.fetch_fulltext(args.get("source_id", ""), args.get("doi"))
    if action == "query_db":
        return tools.query_db(args.get("sql", "SELECT 1"))
    if action == "save_evidence":
        return tools.save_evidence(args.get("source_id", ""))
    return {"error": f"unknown action {action!r}"}


def _format_scratchpad(steps: list[dict]) -> str:
    if not steps:
        return "(none yet)"
    lines = []
    for i, s in enumerate(steps, 1):
        obs = s.get("observation")
        obs_txt = json.dumps(obs, ensure_ascii=False)[:2500]
        lines.append(
            f"Step {i}: action={s.get('action')!r} args={json.dumps(s.get('args', {}))}\n"
            f"  observation: {obs_txt}"
        )
    return "\n".join(lines)


def run(
    db_path,
    goal: str,
    *,
    max_steps: int = 8,
    disease: str = DEFAULT_DISEASE,
    since_year: int = DEFAULT_SINCE_YEAR,
) -> str:
    """Run the ReAct loop; return final summary text."""
    from db import backend_label, connect

    run_id = str(uuid.uuid4())[:8]
    steps: list[dict] = []
    final_summary = ""

    with connect(db_path) as conn:
        tools = ResearchTools(conn, disease=disease, since_year=since_year)
        print(f"[research] {backend_label()} run_id={run_id} goal={goal!r}", file=sys.stderr)

        for step_idx in range(1, max_steps + 1):
            user_msg = REACT_USER_TEMPLATE.format(
                goal=goal,
                scratchpad=_format_scratchpad(steps),
            )
            raw = _nebius_chat(user_msg)
            if not raw:
                final_summary = "Planner unavailable (set NEBIUS_* / EXTRACT_BACKEND=nebius)."
                break

            parsed = _parse_action_json(raw)
            if parsed is None:
                raw_retry = _nebius_chat(user_msg + "\n\nYour last reply was invalid JSON. Reply with ONLY valid JSON.")
                parsed = _parse_action_json(raw_retry or "")

            if not parsed:
                obs = {"error": "invalid JSON from planner", "raw": raw[:500]}
                steps.append({"action": "parse_error", "args": {}, "observation": obs})
                log_trace(conn, run_id, step_idx, "invalid planner JSON", obs)
                conn.commit()
                continue

            if parsed.get("done"):
                final_summary = str(parsed.get("summary") or "Done.")
                log_trace(
                    conn, run_id, step_idx, final_summary,
                    {"done": True, "steps": len(steps)},
                )
                conn.commit()
                break

            action = parsed.get("action")
            args = parsed.get("args") or {}
            if not action:
                obs = {"error": "missing action", "parsed": parsed}
            else:
                try:
                    obs = _execute_tool(tools, action, args)
                except Exception as exc:  # noqa: BLE001
                    obs = {"error": str(exc)}

            steps.append({"action": action, "args": args, "observation": obs})
            log_trace(
                conn, run_id, step_idx,
                f"{action}({json.dumps(args, ensure_ascii=False)[:120]})",
                {"action": action, "args": args, "observation": obs},
            )
            conn.commit()
            print(f"[research] step {step_idx}: {action}", file=sys.stderr)

        if not final_summary:
            saved = sum(
                1 for s in steps
                if s.get("action") == "save_evidence"
                and isinstance(s.get("observation"), dict)
                and s["observation"].get("ok")
            )
            final_summary = (
                f"Stopped after {max_steps} steps without done flag. "
                f"save_evidence calls with ok: {saved}."
            )
            log_trace(conn, run_id, max_steps + 1, final_summary, {"done": False, "steps": len(steps)})
            conn.commit()

    print(f"\n[research] summary: {final_summary}")
    return final_summary


def main() -> None:
    import argparse
    from paths import default_db_path

    p = argparse.ArgumentParser(description="Evidence Research Agent (ReAct)")
    p.add_argument("--goal", required=True)
    p.add_argument("--max-steps", type=int, default=8)
    p.add_argument("--disease", default=DEFAULT_DISEASE)
    p.add_argument("--since", type=int, default=DEFAULT_SINCE_YEAR)
    a = p.parse_args()
    run(
        default_db_path(),
        a.goal,
        max_steps=a.max_steps,
        disease=a.disease,
        since_year=a.since,
    )


if __name__ == "__main__":
    main()
