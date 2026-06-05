"""conftest.py — pytest path setup for the eval harness [tester, builder 3].

Implements: test_review_contract.md part B run harness — the eval modules import the running agent
            (`cua`), the fixtures (`testdata`), and each other (flat modules in this dir), under bare
            `pytest` (pyproject `testpaths=["tests"]`). Offline + deterministic: no network, no LLM —
            the blinded judge + RePORTER reference set are deterministic v1 surrogates
            (build/decisions/2026-06-02-eval-methodology.md §B). Owner: S7 (builder 3).

Puts the repo root (so `import cua` / `import testdata` resolve), `tests/` (so `import invariants`
resolves — part A is reused by the review), and `tests/eval/` (so the sibling eval modules
`reporter_reference` / `blinded_judge` / `critic_calibration` / `eval_report` / `competitiveness`
resolve flat) on `sys.path`. Nothing here touches the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EVAL = Path(__file__).resolve().parent
_TESTS = _EVAL.parent
_ROOT = _TESTS.parent
_SRC = _ROOT / "src"
for _p in (_ROOT, _SRC, _TESTS, _EVAL):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
