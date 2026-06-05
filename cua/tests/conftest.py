"""conftest.py — pytest path setup for the tester [tester].

Implements: test_review_contract.md part A/B/C run harness — the offline suite runs under a bare
            `pytest` (pyproject `testpaths=["tests"]`) with NO install step, no LLM, no network.
Owner: S3 (builder 3); extended at S8 (part C review needs `cua` + the eval modules suite-wide).

Puts on `sys.path`: the repo root (so `import testdata` — the S1 fixtures — resolves), `src/` (so
`import cua` — the agent — resolves install-free; S6 CR-4), `tests/` (so `import invariants` and
`import review` resolve), and `tests/eval/` (so the flat eval modules — `eval_report`,
`critic_calibration`, `blinded_judge`, … — resolve for `tests/review.py` and the part-C suite).
Nothing here touches the network.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_ROOT = _TESTS.parent
_SRC = _ROOT / "src"
_EVAL = _TESTS / "eval"
for _p in (_ROOT, _SRC, _TESTS, _EVAL):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
