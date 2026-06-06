"""
Manual spot-check sampling for extraction quality.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

from db import connect
from agents.literature_agent import fetch_biomcp_detail


DEFAULT_CSV = Path("spot_check_results.csv")

COLUMNS = [
    "source_id",
    "title",
    "extracted_mechanism",
    "correct_mechanism",
    "extracted_treatment",
    "correct_treatment",
    "extracted_study_type",
    "correct_study_type",
    "extracted_sample_size",
    "correct_sample_size",
    "precision",
    "notes",
]


def _fetch_abstract(source_id: str) -> str:
    detail = fetch_biomcp_detail("literature", source_id)
    if not detail:
        return ""
    return detail.get("abstract") or detail.get("abstractText") or ""


def sample_evidence_rows(
    conn,
    count: int = 15,
    mode: str = "random",
    low_confidence_ids: list[str] | None = None,
) -> list[dict]:
    conn.execute(
        "SELECT source_id, title, mechanism, treatment, study_type, sample_size, key_result "
        "FROM evidence WHERE source_type = 'literature' AND source_id NOT LIKE 'DEMO-%' "
        "ORDER BY evidence_id DESC"
    )
    rows = conn.fetchall()
    if not rows:
        conn.execute(
            "SELECT source_id, title, mechanism, treatment, study_type, sample_size, key_result "
            "FROM evidence WHERE source_type = 'literature' ORDER BY evidence_id DESC LIMIT 100"
        )
        rows = conn.fetchall()

    if mode == "low-confidence" and low_confidence_ids:
        id_set = set(low_confidence_ids)
        rows = [r for r in rows if r["source_id"] in id_set]

    if len(rows) <= count:
        return rows
    return random.sample(rows, count)


def export_spot_check(
    db_path,
    count: int = 15,
    mode: str = "random",
    output: Path | None = None,
    low_confidence_ids: list[str] | None = None,
) -> Path:
    out = output or DEFAULT_CSV
    with connect(db_path) as conn:
        rows = sample_evidence_rows(conn, count, mode, low_confidence_ids)

    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            sid = row["source_id"]
            abstract = _fetch_abstract(sid)
            print(f"\n--- [{i}/{len(rows)}] PMID {sid} ---")
            print(row.get("title") or "")
            if abstract:
                print(f"\nAbstract: {abstract[:1200]}{'...' if len(abstract) > 1200 else ''}")
            print(
                f"\nExtracted: mechanism={row.get('mechanism')!r} | "
                f"treatment={row.get('treatment')!r} | study_type={row.get('study_type')!r} | "
                f"n={row.get('sample_size')}"
            )
            print("Fill correct_* columns in CSV after reading the abstract.\n")

            writer.writerow({
                "source_id": sid,
                "title": row.get("title") or "",
                "extracted_mechanism": row.get("mechanism") or "",
                "correct_mechanism": "",
                "extracted_treatment": row.get("treatment") or "",
                "correct_treatment": "",
                "extracted_study_type": row.get("study_type") or "",
                "correct_study_type": "",
                "extracted_sample_size": row.get("sample_size") or "",
                "correct_sample_size": "",
                "precision": "",
                "notes": "",
            })

    print(f"Wrote template: {out}")
    return out


def score_spot_check(csv_path: Path | None = None) -> dict:
    """Score filled spot-check CSV (precision per row where correct_* filled)."""
    path = csv_path or DEFAULT_CSV
    if not path.exists():
        raise FileNotFoundError(f"No spot-check file: {path}")

    scored = 0
    correct = 0.0
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prec = row.get("precision", "").strip()
            if prec:
                try:
                    p = float(prec)
                    scored += 1
                    correct += p
                    continue
                except ValueError:
                    pass
            # Auto-score if correct_mechanism filled
            cm = row.get("correct_mechanism", "").strip()
            if not cm:
                continue
            em = row.get("extracted_mechanism", "").strip().lower()
            scored += 1
            if cm.lower() == em or em in cm.lower() or cm.lower() in em:
                correct += 1.0
            elif cm.lower() and em:
                correct += 0.5

    avg = correct / scored if scored else 0.0
    print("\n=== Spot-check precision ===")
    print(f"Rows scored: {scored}")
    print(f"Average precision: {avg:.2f} ({correct:.1f}/{scored})")
    return {"scored": scored, "precision": avg}
