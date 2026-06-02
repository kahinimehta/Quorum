"""
Consistency checks for LLM-extracted evidence rows.
"""
from __future__ import annotations

import re
from typing import Any

# Literature agent types + plan extras
VALID_STUDY_TYPES = frozenset({
    "in vitro", "mouse", "cohort", "RCT", "preclinical",
    "Phase 1", "Phase 2", "Phase 3",
    "case report", "review", "unknown",
})

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"


def _text(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _valid_source_id(source_type: str, source_id: str) -> bool:
    sid = _text(source_id)
    if not sid:
        return False
    if sid.startswith("DEMO-"):
        return True
    if source_type == "literature":
        digits = sid.replace("PMID:", "").strip()
        if digits.isdigit():
            return True
        # DOI or bioRxiv-style id from BioMCP when PMID missing
        return "/" in sid or sid.startswith("10.")
    if source_type == "trial":
        s = sid.upper().replace("NCT:", "")
        return s.startswith("NCT") and len(s) > 3
    if source_type == "grant":
        return len(sid) >= 3
    return False


def _study_type_ok(study_type: str) -> bool:
    if not study_type:
        return True
    if study_type in VALID_STUDY_TYPES:
        return True
    lowered = study_type.lower()
    for token in re.split(r"[\s+/,&]+", lowered):
        if token in VALID_STUDY_TYPES:
            return True
    return False


VALID_ACCESS_TYPES = frozenset({
    "published_oa", "published_paywalled", "preprint", "error", "unknown",
    # legacy values accepted during transition
    "open", "restricted",
})


def _access_type_ok(access_type: str) -> bool:
    if not access_type:
        return True
    return access_type in VALID_ACCESS_TYPES


def validate_extraction(evidence_row: dict) -> tuple[bool, str, list[str]]:
    """
    Return (is_valid, confidence, issues).

    Grants use lighter checks; literature/trials get full extraction QA.
    """
    issues: list[str] = []
    source_type = _text(evidence_row.get("source_type"))
    source_id = _text(evidence_row.get("source_id"))

    if not _valid_source_id(source_type, source_id):
        issues.append(f"invalid source_id for {source_type}: {source_id!r}")

    study_type = _text(evidence_row.get("study_type"))
    if study_type and source_type != "literature" and not _study_type_ok(study_type):
        issues.append(f"study_type not in allowed set: {study_type!r}")

    access_type = _text(evidence_row.get("access_type"))
    if access_type and not _access_type_ok(access_type):
        issues.append(f"access_type not in allowed set: {access_type!r}")

    sample_size = evidence_row.get("sample_size")
    if sample_size is not None:
        try:
            n = int(sample_size)
            if n <= 0 or n >= 1_000_000:
                issues.append(f"sample_size out of range: {n}")
        except (TypeError, ValueError):
            issues.append(f"sample_size not an integer: {sample_size!r}")

    if source_type in ("literature", "trial"):
        mechanism = _text(evidence_row.get("mechanism"))
        treatment = _text(evidence_row.get("treatment"))
        key_result = _text(evidence_row.get("key_result"))
        snippet = _text(evidence_row.get("evidence_snippet"))

        has_llm_fields = mechanism or treatment or key_result
        # Light literature agent: study_type/sample_size may be null (Agent 4 fills later).
        if source_type == "literature" and not study_type and sample_size is None:
            if not has_llm_fields:
                issues.append("missing core discovery fields (mechanism/treatment/key_result)")
        if has_llm_fields:
            if len(mechanism) < 5:
                issues.append("mechanism missing or too short (<5 chars)")
            if len(treatment) < 3:
                issues.append("treatment missing or too short (<3 chars)")
            if not key_result:
                issues.append("key_result empty")
            if snippet and len(snippet) < 10:
                issues.append("evidence_snippet too short (<10 chars)")
            elif source_type == "literature" and not snippet:
                issues.append("evidence_snippet empty for literature")

    elif source_type == "grant":
        if not _text(evidence_row.get("title")):
            issues.append("grant title empty")

    is_valid = len(issues) == 0
    if is_valid:
        confidence = CONFIDENCE_HIGH
    elif len(issues) <= 2:
        confidence = CONFIDENCE_MEDIUM
    else:
        confidence = CONFIDENCE_LOW
    return is_valid, confidence, issues


def batch_validate(rows: list[dict]) -> dict:
    """Summarize validation over a list of evidence dicts."""
    passed = []
    failed = []
    for row in rows:
        ok, conf, issues = validate_extraction(row)
        entry = {
            "source_type": row.get("source_type"),
            "source_id": row.get("source_id"),
            "confidence": conf,
            "issues": issues,
        }
        if ok:
            passed.append(entry)
        else:
            failed.append(entry)
    total = len(rows)
    pass_n = len(passed)
    return {
        "total": total,
        "passed": pass_n,
        "failed": len(failed),
        "pass_rate": (pass_n / total) if total else 0.0,
        "passed_rows": passed,
        "failed_rows": failed,
    }


def extract_entity_hints(finding: dict) -> dict[str, list[str]]:
    """Heuristic gene/disease/chemical tokens from extracted text for PubTator compare."""
    blob = " ".join(
        _text(finding.get(k))
        for k in ("subgroup", "mechanism", "treatment", "key_result", "title")
    )
    genes = set(re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", blob))
    genes -= {"RCT", "PD", "NIH", "DNA", "RNA", "CSF", "OR", "AND"}
    diseases: set[str] = set()
    low = blob.lower()
    if "parkinson" in low:
        diseases.add("Parkinson disease")
    if "alzheimer" in low:
        diseases.add("Alzheimer disease")
    chemicals: set[str] = set()
    for chem in ("dopamine", "levodopa", "carbidopa", "ambroxol", "gcase"):
        if chem in low:
            chemicals.add(chem)
    return {
        "genes": sorted(genes),
        "diseases": sorted(diseases),
        "chemicals": sorted(chemicals),
    }
