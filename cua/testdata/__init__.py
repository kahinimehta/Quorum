"""testdata — stand-in upstream fixtures for the Conclusion Update Agent [test-data].

Governing contract: files/conclusion_update_agent_test_data_contract.md. Types populated from the
main contract (contracts.md §1.1, §2.1, §2.3). Owner: S1 (builder 2). Brief: build/briefs/S1_fixtures.md.

Public API (consumed by S2 to drive the Orchestrator skeleton and by S3's oracle assertions):
    from testdata import all_fixtures, validate, Fixture, Expectations, ...

Fixtures, not agents — no live literature search, no real GRADE assessment, no commercial modeling.
"""

from __future__ import annotations

from .scenarios import (
    DEFAULT_SEEDS,
    SCENARIO_BUILDERS,
    all_fixtures,
    clean_high_grade,
    fabrication_bait,
    intentionally_broken,
    low_grade_bait,
    thin_corpus,
    unscored_claim,
)
from .types import (
    GRADE_RANK,
    GRADE_VALUES,
    CommercialLandscape,
    EvidenceAssessment,
    EvidenceEntry,
    Expectations,
    ExternalCritique,
    Fixture,
    Grade,
    GrantCall,
    Paper,
    SourceSet,
    Subgroup,
    Treatment,
    canonical_json,
    digest,
)
from .validate import FixtureValidationError, validate, validation_errors

__all__ = [
    # builders / registry
    "all_fixtures",
    "clean_high_grade",
    "thin_corpus",
    "low_grade_bait",
    "fabrication_bait",
    "unscored_claim",
    "intentionally_broken",
    "SCENARIO_BUILDERS",
    "DEFAULT_SEEDS",
    # validation
    "validate",
    "validation_errors",
    "FixtureValidationError",
    # determinism
    "canonical_json",
    "digest",
    # types
    "Fixture",
    "Expectations",
    "Grade",
    "GRADE_RANK",
    "GRADE_VALUES",
    "Paper",
    "SourceSet",
    "EvidenceEntry",
    "EvidenceAssessment",
    "GrantCall",
    "Subgroup",
    "Treatment",
    "CommercialLandscape",
    "ExternalCritique",
]
