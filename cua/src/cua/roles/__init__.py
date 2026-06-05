"""roles — the LLM role implementations (engine signatures, configured per contracts.md §2.4).

The NIH bindings of the generic engine roles (design §2 map): Conditioner = Blueprint Planner,
Generator stages = Argument Synthesizer + Aim Architect, the best-of-N Selection Scorer, and the
judgment lineage — the Internal Critic + Reviser (S5, closing the revise loop). These are the NIH
instantiation of the engine's frozen §1.5 signatures, so they legitimately reference the binding types
(CONVENTIONS rule 1 header on each); the generic spine (`src/cua/*.py`) stays domain-noun-free.

Owner: S4 (builder 1) — Blueprint, Synthesizer, Aim Architect, Selection Scorer. S5 (builder 1) —
       Internal Critic, Reviser.
"""

from __future__ import annotations

from .aim_architect import AimArchitect
from .blueprint import BlueprintPlanner
from .critic import InternalCritic
from .reviser import Reviser
from .selection_scorer import SelectionScorer
from .synthesizer import ArgumentSynthesizer

__all__ = [
    "BlueprintPlanner",
    "ArgumentSynthesizer",
    "AimArchitect",
    "SelectionScorer",
    "InternalCritic",
    "Reviser",
]
