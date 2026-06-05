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

from .llm import LiveStructuredOutputError
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


def _attempt_cap(target: int) -> int:
    """BON-RESILIENCE bounded top-up budget: `target` successes + ~50% headroom (ceil(target/2)). A
    fresh sample usually succeeds (a retry-exhausted structured-output failure is a stochastic bad roll,
    not deterministic), so the cap is rarely reached — it just stops a pathological failure rate from
    running away. target=1 → 2, 3 → 5, 5 → 8, 10 → 15, 20 → 30."""
    return target + (target + 1) // 2  # target + ceil(target/2)


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
        # Single-shot, with BON-RESILIENCE bounded top-up: target 1 success. A retry-exhausted live
        # structured-output failure (LiveStructuredOutputError) drops that attempt and re-rolls a FRESH
        # sample up to the cap; hard-fail only if none succeed (strictly more robust than today, never
        # less). DEAD offline — the surrogate never raises, so attempt 1 succeeds → exactly one produce →
        # the same single-shot TraceEvent → byte-identical. We catch ONLY LiveStructuredOutputError.
        cap = _attempt_cap(1)
        last_error: LiveStructuredOutputError | None = None
        for attempt in range(1, cap + 1):
            # Trace-guard (decisions/2026-06-02-trace-recording-ownership.md): a live body calls
            # complete() and records its OWN event; a surrogate body records nothing → the spine records
            # the fallback. Guard on the event count so exactly ONE event lands per call, both paths.
            pre = len(recorder.trace)
            try:
                fragment = stage.produce(obligations, inputs, draft_so_far, item)
            except LiveStructuredOutputError as exc:
                last_error = exc  # complete() already recorded its FAILED event; add a transparent marker
                recorder.record(
                    round=round, role=f"{stage.name}:dropped", model=model, sampling=sampling,
                    input_refs=("obligations", "inputs"), output_ref=f"fragment:{label}#attempt{attempt}",
                    decision=f"dropped attempt {attempt}/{cap} (target 1): LiveStructuredOutputError (retry-exhausted); topping up",
                )
                continue
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
            if attempt > 1:  # a top-up happened → log it (DEAD offline; attempt is always 1 there)
                recorder.record(
                    round=round, role=f"{stage.name}:resilience", model=model, sampling=sampling,
                    input_refs=("obligations", "inputs"), output_ref=f"fragment:{label}",
                    decision=f"single-shot top-up: requested 1, attempts {attempt}, succeeded 1, dropped {attempt - 1}",
                )
            return fragment
        raise last_error  # cap reached with zero successes → hard-fail (re-raise the last error)

    # Best-of-N: target N SUCCESSFUL candidates, rank with the separate SelectionScorer, keep the best.
    # BON-RESILIENCE (TOP-UP): a candidate's retry-exhausted live structured-output failure
    # (LiveStructuredOutputError) must NOT abort the run AND must NOT silently shrink N (which would
    # distort the scaling x-axis) — drop the failed attempt and re-roll a REPLACEMENT until there are N
    # successes, bounded at `cap = N + ceil(N/2)`. If the cap is hit with M (1 ≤ M < N) successes, proceed
    # with the best of those M (logged "got M of N"); hard-fail only if ZERO succeed. We catch ONLY that
    # legible case (never bare Exception → real bugs/contract violations still surface). The surrogate
    # never raises it, so offline this is exactly N produces → the drop/top-up path is DEAD → byte-identical.
    cap = _attempt_cap(n)
    candidates: list[DraftFragment] = []  # successes, in success order
    drops: list[dict] = []  # {attempt, error} per dropped (topped-up) attempt — surfaced in trace + content.json
    last_error: LiveStructuredOutputError | None = None
    attempt = 0
    while len(candidates) < n and attempt < cap:
        attempt += 1
        pre = len(recorder.trace)  # trace-guard (see single-shot path): one event per sample, both paths
        try:
            cand = stage.produce(obligations, inputs, draft_so_far, item)
        except LiveStructuredOutputError as exc:
            # complete() already recorded its one (FAILED) TraceEvent before raising; add a transparent
            # `:dropped` marker, then top up with a fresh sample (the loop continues).
            last_error = exc
            drops.append({"attempt": attempt, "error": str(exc)})
            recorder.record(
                round=round,
                role=f"{stage.name}:dropped",
                model=model,
                sampling=sampling,
                input_refs=("obligations", "inputs"),
                output_ref=f"fragment:{label}#attempt{attempt}",
                decision=f"dropped attempt {attempt}/{cap} (target {n}): LiveStructuredOutputError (retry-exhausted); topping up",
            )
            continue
        candidates.append(cand)
        k = len(candidates)  # success ordinal (1-based); offline k == attempt → byte-identical sample event
        if len(recorder.trace) == pre:
            recorder.record(
                round=round,
                role=stage.name,
                model=model,
                sampling=sampling,
                input_refs=("obligations", "inputs"),
                output_ref=f"fragment:{label}#sample{k}",
                tokens=_estimate_tokens(cand.text),
                decision=f"sample {k}/{n}",
            )

    # Fail ONLY if ZERO candidates succeeded — re-raise the last structured-output error so an all-fail
    # run (and the n==1 path above, which never enters this loop) hard-fails exactly as today.
    if not candidates:
        raise last_error  # last_error is set iff we got here via the except (candidates is empty)
    succeeded = len(candidates)
    if drops:
        # A summary event (DEAD offline — drops is always empty there): the operator/diagram reads
        # "requested N, attempts, succeeded, dropped" off this one line (+ "got M of N" if the cap was
        # hit). Live-only; never changes the selected fragment.
        shortfall = "" if succeeded == n else f" — got {succeeded} of {n} requested (cap {cap} reached)"
        recorder.record(
            round=round,
            role=f"{stage.name}:resilience",
            model=model,
            sampling=sampling,
            input_refs=("obligations", "inputs"),
            output_ref=f"fragment:{label}",
            decision=(
                f"best-of-N top-up: requested {n}, attempts {attempt}, succeeded {succeeded}, "
                f"dropped {len(drops)}{shortfall}"
            ),
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
            # reference the SUCCESS slots 1..M (offline: M == n → identical to today's range(n))
            input_refs=tuple(f"fragment:{label}#sample{k}" for k in range(1, succeeded + 1)),
            output_ref=f"fragment:{label}",
            tokens=None,
            decision=f"best-of-{n}",  # n = requested (offline M==n → byte-identical)
        )

    # log_pairs (contracts.md §1.8; design §5): record the (chosen, rejected) best-of-N pair as
    # future-FT data, keyed by the reward dimension. Observability ONLY — it never changes the
    # selected fragment or the control flow. Keyed by the success sample numbers 1..M (offline == 1..n).
    if getattr(config, "log_pairs", False):
        chosen_sample = candidates.index(best) + 1
        rejected = [k for k in range(1, succeeded + 1) if k != chosen_sample]
        recorder.record(
            round=round,
            role="selection_pairs",
            sampling=f"reward={dimension}" if dimension else None,
            input_refs=tuple(f"fragment:{label}#sample{s}" for s in rejected),
            output_ref=f"fragment:{label}#sample{chosen_sample}",
            decision=(
                f"log_pairs reward={dimension or 'n/a'}: chosen sample{chosen_sample}, "
                f"rejected {len(rejected)} (future-FT data; no run effect)"
            ),
        )

    # Content capture (CONTENT-CAP; observation-only, gated): persist the M successful candidate contents
    # + their reward scores + the chosen one for `<run>.content.json`, plus the top-up accounting
    # (BON-RESILIENCE: requested/attempts/succeeded/dropped + the dropped attempts). Write-only — `best`
    # is already chosen above; this never changes the selected fragment or the control flow.
    if content_capture is not None:
        content_capture.record_best_of_n(
            round, label, dimension, candidates, ranked, best, drops=drops, requested=n, attempts=attempt
        )
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
