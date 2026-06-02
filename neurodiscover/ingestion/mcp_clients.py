"""
Optional MCP subprocess wrappers with JSON stdout fallback.

Set PUBMED_MCP_COMMAND or BIORXIV_MCP_COMMAND to a shell command that accepts:
  search --json '<payload>'

Payload is JSON: {"query": "...", "max": N, "since_year": YYYY}
Expected stdout: JSON list of article dicts, or {"results": [...]}.

If the command is missing or fails, callers use direct API fallbacks.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Callable


def _normalize_mcp_results(data: Any) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("results", "articles", "papers", "items"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def try_mcp_search(
    env_var: str,
    *,
    query: str,
    max_items: int,
    since_year: int,
    fallback: Callable[..., list[dict]],
    **fallback_kwargs: Any,
) -> tuple[list[dict], str]:
    """
    Try MCP command from env_var; on failure call fallback().

    Returns (results, source) where source is 'mcp' or 'api'.
    """
    command = os.environ.get(env_var, "").strip()
    if not command:
        return fallback(query=query, max_items=max_items, since_year=since_year, **fallback_kwargs), "api"

    payload = json.dumps({
        "query": query,
        "max": max_items,
        "since_year": since_year,
        **fallback_kwargs,
    })
    try:
        proc = subprocess.run(
            f'{command} search --json {json.dumps(payload)}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            print(
                f"[warn] {env_var} failed (rc={proc.returncode}): {proc.stderr[:200]}",
                file=sys.stderr,
            )
            return fallback(query=query, max_items=max_items, since_year=since_year, **fallback_kwargs), "api"
        data = json.loads(proc.stdout)
        results = _normalize_mcp_results(data)
        if not results:
            return fallback(query=query, max_items=max_items, since_year=since_year, **fallback_kwargs), "api"
        return results[:max_items], "mcp"
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] {env_var} error: {exc}", file=sys.stderr)
        return fallback(query=query, max_items=max_items, since_year=since_year, **fallback_kwargs), "api"
