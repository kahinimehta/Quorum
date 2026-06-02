#!/usr/bin/env python3
"""Write gitignored personal/team-keys-for-sharing.txt from .env (for Discord/1Password)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
OUT = ROOT / "personal" / "team-keys-for-sharing.txt"

SECTIONS = [
    (
        "Everyone — Python agents, cli.py, Express/Flask with SQL",
        [
            "SUPABASE_DATABASE_URL",
        ],
    ),
    (
        "Literature agent only (Person 3 / pull & scan)",
        [
            "NEBIUS_API_KEY",
            "NEBIUS_BASE_URL",
            "NEBIUS_MODEL",
            "EXTRACT_BACKEND",
        ],
    ),
    (
        "Next.js dashboard (Person 5)",
        [
            "NEXT_PUBLIC_SUPABASE_URL",
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        ],
    ),
    (
        "Server-only — Person 5 API routes if needed (never in browser)",
        [
            "SUPABASE_SERVICE_ROLE_KEY",
        ],
    ),
    (
        "Optional — local Ollama extraction (not for most teammates)",
        [
            "EXTRACT_BACKEND",
            "OLLAMA_HOST",
            "OLLAMA_MODEL",
        ],
    ),
]


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        out[key.strip()] = val
    return out


def main() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV)
    except Exception:
        pass

    env = load_env(ENV)
    for k, v in os.environ.items():
        if k.startswith(("SUPABASE_", "NEBIUS_", "NEXT_PUBLIC_", "EXTRACT_", "OLLAMA_")):
            env.setdefault(k, v)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# NeuroDiscover — team keys (PRIVATE — do not commit)",
        f"# Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "# Share via 1Password / Discord DM. Delete after teammates save copies.",
        "",
    ]

    seen: set[str] = set()
    for title, keys in SECTIONS:
        lines.append(f"## {title}")
        lines.append("")
        for key in keys:
            seen.add(key)
            val = env.get(key, "").strip()
            if val:
                lines.append(f"{key}={val}")
            else:
                lines.append(f"# {key}=  ← MISSING — fill from Supabase/Nebius dashboard")
        lines.append("")

    extra = sorted(k for k in env if k not in seen and not k.startswith("_"))
    if extra:
        lines.append("## Other keys in .env")
        lines.append("")
        for key in extra:
            lines.append(f"{key}={env[key]}")
        lines.append("")

    lines.extend([
        "## Who needs what",
        "- Person 2 (backend SQL): SUPABASE_DATABASE_URL only",
        "- Person 4 agents (Python): SUPABASE_DATABASE_URL + read AGENT_IO.md",
        "- Person 5 (Next.js): NEXT_PUBLIC_* ; optional service role for server routes",
        "- Literature pull: add NEBIUS_* (team default); optional EXTRACT_BACKEND=ollama for local runs",
        "",
        "Never run: python3 cli.py build  on shared Supabase after live data exists.",
    ])

    OUT.write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")
    print("Open that file and copy sections to teammates. File is gitignored under personal/")


if __name__ == "__main__":
    main()
