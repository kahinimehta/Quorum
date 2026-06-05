"""grant_call.py — NIH binding: the authoritative GrantCall + its boundary value/loader.

Implements: contracts.md §2.3 (NIHGrantTask.input_contract — the required `GrantCall` slot) and
            §2.5 (intake preconditions: mechanism + page limits KNOWN, else the agent refuses).
Governing: build/integration/adaption.md #11 (GrantCall has no upstream producer → supplied at OUR
           boundary, never from the DB), #12/#17 (our own entrypoint reads a DB URL).
Generic role: none — GrantCall is a domain input slot the engine consumes duck-typed
              (`task.py` reads `.mechanism`/`.title`/`.*_page_limit`); it never enters the spine.
NIH binding: the NIH funding-opportunity / grant-call metadata (mechanism, FOA, page limits, due
             date, review framework). Domain nouns are legal here (binding layer, CONVENTIONS rule 1).
Owner: INT-1 (builder 1).

Why this file exists (adaption.md #11): `GrantCall` previously lived ONLY in `testdata` (a stand-in),
and the production path must not import `testdata`. This is the authoritative type — field-identical
to the stand-in (testdata/types.py) so the engine's duck-typed reads are unchanged — plus a default
boundary value and a file loader. It is metadata only — NOT evidence, and it invents no science.

Offline + deterministic: pure literals and stdlib `json` only; no network, no DB, no clock. The
default `due_date` is a fixed ISO literal (NOT `datetime.now()`) so two runs are byte-identical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Placeholder FOA id — UNMISTAKABLY not a real announcement (adaption.md #11: "never present a
# placeholder FOA as real"). INT-3's entrypoint / a loaded config sets the real FOA before any
# submission-facing use. `foa_id` is not an intake precondition (§2.5 gates mechanism + limits), so a
# placeholder here still satisfies `intake_refusal() is None`.
PLACEHOLDER_FOA_ID = "PLACEHOLDER-SET-REAL-FOA"

# Default NIH review framework (RPG due dates ≥ 2025-01-25 use the Simplified Review Framework).
DEFAULT_REVIEW_FRAMEWORK = "NIH Simplified Review Framework (2025)"


@dataclass
class GrantCall:
    """NIH grant-call metadata the `NIHGrantTask` needs to NOT refuse intake (contracts.md §2.5:
    mechanism + page limits must be KNOWN). Field-identical to the `testdata` stand-in so the
    engine's duck-typed reads (`.mechanism`/`.title`/`.*_page_limit`) are unchanged — this is the
    AUTHORITATIVE definition; the stand-in is a fixture mirror (adaption.md #11)."""

    mechanism: str  # NIH activity code, e.g. "R01" — gates intake (§2.5) + aim count (obligations.py)
    title: str  # the proposal topic the writers condition on
    foa_id: str  # funding-opportunity announcement id (e.g. "PAR-25-123"); placeholder until set real
    specific_aims_page_limit: int  # NIH: Specific Aims = 1 page
    research_strategy_page_limit: int  # mechanism-dependent (R01 ≈ 12)
    due_date: str  # ISO date; RPG due dates ≥ 2025-01-25 use the Simplified Review Framework
    review_framework: str = DEFAULT_REVIEW_FRAMEWORK


def default_grant_call() -> GrantCall:
    """The boundary default for the Parkinson's pipeline (adaption.md #11) — an R01 with NIH-standard
    page limits and an ISO due date on a real R01 cycle (≥ 2025-01-25 → Simplified Review Framework).

    Metadata only — NOT evidence; invents no science. `foa_id` is a clearly-marked PLACEHOLDER to be
    set to the real FOA by the entrypoint/config (INT-3). Satisfies `NIHGrantTask.intake_refusal() is
    None` (mechanism + both page limits are truthy). Pure literals → deterministic."""

    return GrantCall(
        mechanism="R01",
        title="Parkinson's disease pipeline — NIH R01 research proposal",
        foa_id=PLACEHOLDER_FOA_ID,
        specific_aims_page_limit=1,
        research_strategy_page_limit=12,
        due_date="2026-10-05",  # fixed literal (NOT a clock) — a real R01 standard cycle date
        review_framework=DEFAULT_REVIEW_FRAMEWORK,
    )


def load_grant_call(path: str | Path) -> GrantCall:
    """Load a GrantCall from a local JSON file (offline; stdlib only). The file supplies the real FOA
    + topic at our boundary; missing `review_framework` falls back to the default. Unknown keys raise
    (TypeError) so a malformed config fails loudly rather than silently dropping a required slot.

    The caller is responsible for ensuring mechanism + page limits are present — an incomplete
    GrantCall will (correctly) make `NIHGrantTask.intake_refusal()` return a refusal reason (§2.5)."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"grant-call config must be a JSON object, got {type(data).__name__}")
    return GrantCall(**data)
