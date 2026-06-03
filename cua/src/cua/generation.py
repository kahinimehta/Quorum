"""generation.py — Generator driver [code+LLM].

Implements: contracts.md §1.6 (staged pipeline: stages in order, fan-out on map_over, merge each
            DraftFragment into the Draft) + best-of-N driver shell (n_samples>1 → produce N, keep the
            SelectionScorer's top pick, pre-grounding). §1.5 Generator signature.
Generic role: the deterministic code driver around the (LLM, stubbed in S2) produce() calls.
NIH binding: the stage instances + their reward dimensions are supplied by the bound Task (design §2).
Owner: S2 (builder 1, driver) → S4 (real stages replace the stubs).

Only produce() is a model call; everything here — ordering, fan-out, merge, best-of-N selection — is
deterministic code (design principle 3). A stage's `map_over` is a string ref the driver resolves
against the named item collections fragments `provide`; the ref name is binding data, not a noun here.
"""

from __future__ import annotations

from .trace import TraceRecorder
from .types import (
    Draft,
    DraftFragment,
    GenerationStage,
    Obligation,
    SelectionScorer,
)


def _estimate_tokens(text: str) -> int:
    """Deterministic stand-in token count for the Trace (no real model call in S2)."""
    return max(1, len(text) // 4)


def _merge(draft: Draft, registry: dict[str, list], fragment: DraftFragment) -> None:
    """Merge a DraftFragment into the Draft and register any item collections it provides for a
    downstream stage's map_over (contracts.md §1.6 'merges each DraftFragment into the Draft')."""
    draft.fragments.append(fragment)
    for ref, items in fragment.provides.items():
        registry.setdefault(ref, []).extend(items)


def _produce_one(
    stage: GenerationStage,
    obligations: list[Obligation],
    inputs: dict,
    draft_so_far: Draft,
    item,
    selection_scorer: SelectionScorer | None,
    recorder: TraceRecorder,
    round: int,
    label: str,
    content_capture=None,
) -> DraftFragment:
    """Run a single stage position, applying best-of-N when configured (contracts.md §1.6).

    n_samples>1: call produce() N times and keep the candidate the SelectionScorer ranks highest on
    the stage's reward dimension — pre-grounding, cheap. Each produce() is one role call → one
    TraceEvent; the selection is its own event. Ties keep the first candidate (stable)."""

    config = stage.config
    model = getattr(config, "model_id", None)
    sampling = config.sampling_descriptor() if hasattr(config, "sampling_descriptor") else None
    n = max(1, getattr(config, "n_samples", 1))

    if n == 1 or selection_scorer is None:
        # Trace-guard (decisions/2026-06-02-trace-recording-ownership.md): a live body calls
        # complete() and records its OWN event; a surrogate body records nothing → the spine records
        # the fallback. Guard on the event count so exactly ONE event lands per call, both paths.
        pre = len(recorder.trace)
        fragment = stage.produce(obligations, inputs, draft_so_far, item)
        if len(recorder.trace) == pre:
            recorder.record(
                round=round,
                role=stage.name,
                model=model,
                sampling=sampling,
                input_refs=("obligations", "inputs"),
                output_ref=f"fragment:{label}",
                tokens=_estimate_tokens(fragment.text),
                decision="single-shot",
            )
        return fragment

    # Best-of-N: sample N candidates, rank with the separate SelectionScorer, keep the best.
    candidates: list[DraftFragment] = []
    for i in range(n):
        pre = len(recorder.trace)  # trace-guard (see single-shot path): one event per sample, both paths
        cand = stage.produce(obligations, inputs, draft_so_far, item)
        candidates.append(cand)
        if len(recorder.trace) == pre:
            recorder.record(
                round=round,
                role=stage.name,
                model=model,
                sampling=sampling,
                input_refs=("obligations", "inputs"),
                output_ref=f"fragment:{label}#sample{i + 1}",
                tokens=_estimate_tokens(cand.text),
                decision=f"sample {i + 1}/{n}",
            )

    dimension = config.reward_source[0] if getattr(config, "reward_source", None) else ""
    # Trace-guard (decisions/2026-06-02-trace-recording-ownership.md §3): a LIVE score() calls complete()
    # and records its OWN "selection_scorer:live" event; the surrogate records nothing → the spine records
    # the selection event. recorder/round reach the live body via keyword args (the §1.5 score() domain
    # signature is unchanged). Guard on the event count so exactly ONE selection event lands, both paths.
    pre = len(recorder.trace)
    ranked = selection_scorer.score(candidates, dimension, recorder=recorder, round=round)
    best = max(ranked, key=lambda sf: sf.score).fragment if ranked else candidates[0]
    if len(recorder.trace) == pre:
        recorder.record(
            round=round,
            role="selection_scorer",
            model=None,  # set by the binding's stub config; recorded generically here
            sampling=f"reward={dimension}" if dimension else None,
            input_refs=tuple(f"fragment:{label}#sample{i + 1}" for i in range(n)),
            output_ref=f"fragment:{label}",
            tokens=None,
            decision=f"best-of-{n}",
        )

    # log_pairs (contracts.md §1.8; design §5): record the (chosen, rejected) best-of-N pair as
    # future-FT data, keyed by the reward dimension. Observability ONLY — it never changes the
    # selected fragment or the control flow.
    if getattr(config, "log_pairs", False):
        chosen_idx = candidates.index(best)
        rejected = [i + 1 for i in range(n) if i != chosen_idx]
        recorder.record(
            round=round,
            role="selection_pairs",
            sampling=f"reward={dimension}" if dimension else None,
            input_refs=tuple(f"fragment:{label}#sample{i}" for i in rejected),
            output_ref=f"fragment:{label}#sample{chosen_idx + 1}",
            decision=(
                f"log_pairs reward={dimension or 'n/a'}: chosen sample{chosen_idx + 1}, "
                f"rejected {len(rejected)} (future-FT data; no run effect)"
            ),
        )

    # Content capture (CONTENT-CAP; observation-only, gated): persist the N candidate contents + their
    # reward scores + the chosen one for `<run>.content.json`. Write-only — `best` is already chosen
    # above; this never changes the selected fragment or the control flow (the sink is None when off).
    if content_capture is not None:
        content_capture.record_best_of_n(round, label, dimension, candidates, ranked, best)
    return best


def run_generator(
    task,
    obligations: list[Obligation],
    inputs: dict,
    selection_scorer: SelectionScorer | None,
    recorder: TraceRecorder,
    round: int = 0,
    content_capture=None,
) -> Draft:
    """Drive task.generator: run stages in order, fan out where map_over is set, merge each fragment
    (contracts.md §1.5/§1.6). Returns the assembled pre-grounding Draft."""

    draft = Draft()
    registry: dict[str, list] = {}
    # Provide the recorder + round to any LIVE role body via generic transport keys, so a live
    # produce() can call cua.llm.complete(recorder=…, round=…) and record its OWN TraceEvent. The
    # trace-guard in _produce_one then suppresses the spine's fallback record for that call → exactly
    # one event per call (decisions/2026-06-02-trace-recording-ownership.md). Surrogate bodies (which
    # record nothing) ignore these keys; the shallow copy leaves the caller's inputs untouched.
    inputs = {**inputs, "_recorder": recorder, "_round": round}
    for stage in task.generator:
        if stage.map_over is None:
            fragment = _produce_one(
                stage, obligations, inputs, draft, None, selection_scorer, recorder, round, stage.name,
                content_capture,
            )
            _merge(draft, registry, fragment)
        else:
            items = registry.get(stage.map_over, [])
            for idx, item in enumerate(items):
                fragment = _produce_one(
                    stage,
                    obligations,
                    inputs,
                    draft,
                    item,
                    selection_scorer,
                    recorder,
                    round,
                    f"{stage.name}[{idx}]",
                    content_capture,
                )
                _merge(draft, registry, fragment)
    return draft
