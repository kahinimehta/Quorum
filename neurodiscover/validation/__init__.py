"""Extraction QA: consistency checks, PubTator grounding, spot-check."""

from validation.consistency import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    VALID_STUDY_TYPES,
    batch_validate,
    extract_entity_hints,
    validate_extraction,
)
from validation.pubtator import batch_pubtator_verify, compare_with_pubtator
from validation.report import print_validation_report
from validation.spot_check import export_spot_check, score_spot_check

__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "VALID_STUDY_TYPES",
    "batch_validate",
    "batch_pubtator_verify",
    "compare_with_pubtator",
    "export_spot_check",
    "extract_entity_hints",
    "print_validation_report",
    "score_spot_check",
    "validate_extraction",
]
