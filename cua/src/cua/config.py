"""config.py — RoleConfig tuning surface [code].

Implements: contracts.md §1.8 (RoleConfig — the uniform knob surface on every LLM role/stage).
Generic role: the frozen tuning surface that lets a role's model/sampling/prompt change without
              changing its contract with the others (design principle 5).
NIH binding: the per-role v1 values (§2.4 table) are constructed under cua.nih — not here.
Owner: S2 (builder 1).

Leak rule: this file names no domain nouns. `reward_source` carries dimension strings (e.g. the
binding's scored axes), but those are data supplied by the binding, never named in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RoleConfig:
    """The uniform tuning surface every LLM role/stage carries (contracts.md §1.8).

    Sampling is model-dependent: `temperature` applies ONLY where the model accepts it (Sonnet 4.6,
    Haiku 4.5); it must be None on Opus 4.7/4.8 (which 400 on temperature/top_p/top_k and use
    `effort` instead). Weight-level FT (`lora_adapter`) is not available on Claude 4.x — parked None.
    """

    model_id: str
    temperature: float | None = None
    effort: str | None = None  # low|medium|high|xhigh|max — Opus 4.x reasoning depth
    system_prompt_template: str = ""
    few_shot_exemplars: list = field(default_factory=list)  # WRITER roles only; structural, ON in v1
    n_samples: int = 1  # >1 => best-of-N at inference (SelectionScorer ranks, keep best)
    reward_source: list[str] = field(default_factory=list)  # dimension(s) this stage is scored on
    lora_adapter: str | None = None  # weight-FT hook — parked (not available on Claude 4.x)
    log_pairs: bool = False  # log (chosen, rejected) best-of-N pairs as future-FT data; no run effect

    def sampling_descriptor(self) -> str:
        """A compact, deterministic sampling label for the Trace (contracts.md §1.10 TraceEvent)."""
        if self.effort is not None:
            return f"effort={self.effort}"
        if self.temperature is not None:
            return f"temp={self.temperature}"
        return "default"
