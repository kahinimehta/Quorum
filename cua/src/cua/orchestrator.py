"""orchestrator.py — Orchestrator [code].

Implements: contracts.md §1.5 (Orchestrator signature), §1.11 (round loop + stopping rule), §1.10
            (drives Trace events + Audit assembly), §2.5 (intake / degradation gate).
Generic role: the deterministic spine — invokes each role, writes one Trace event per role call, owns
              the decide (stopping rule), compiles the Audit at exit. It is not a pipeline stage.
NIH binding: bound to one Task at run time (design §2); names no domain nouns.
Owner: S2 (builder 1).

Trust-critical (design principle 3): the loop, the stopping rule, and the intake gate are
deterministic code — a model never owns the decide or the precondition checks. Roles are injected
(the engine duck-types the §1.5 signatures); the binding supplies the concrete stub/real roles.
"""

from __future__ import annotations

from .generation import run_generator
from .grounding import Grounder, GroundingReport, build_overclaim_check
from .trace import TraceRecorder, UnitTestRow, assemble_audit
from .types import (
    Artifact,
    Critic,
    CritiqueReport,
    EvidenceScores,
    RunConfig,
    Task,
    public_view,
)

# Heuristic floor for the degradation path (§2.5). The contract's hard trigger is 'source_set
# non-empty with stable ids'; S2 extends it to a coverage-thinness heuristic so a few-papers corpus
# takes the narrow + risk-flag path. The operator tunes the real bar at S6.
DEFAULT_MIN_SOURCES = 3


class IntakeRefused(RuntimeError):
    """Raised when the Task cannot start — mechanism/limits not KNOWN (contracts.md §2.5)."""


def _role_meta(role) -> tuple[str | None, str | None]:
    """Pull (model, sampling) off a role's RoleConfig for the Trace, if it carries one."""
    config = getattr(role, "config", None)
    if config is None:
        return None, None
    model = getattr(config, "model_id", None)
    sampling = config.sampling_descriptor() if hasattr(config, "sampling_descriptor") else None
    return model, sampling


class Orchestrator:
    """[code] (Task, RunConfig) -> (Artifact, Trace, Audit) — contracts.md §1.5/§1.11.

    Roles are injected at construction (the §1.5 collaborators). The Grounder defaults to the code
    Grounder; the SelectionScorer is optional (only best-of-N stages use it)."""

    def __init__(
        self,
        conditioner,
        critic: Critic,
        reviser,
        grounder: Grounder | None = None,
        selection_scorer=None,
        min_sources: int = DEFAULT_MIN_SOURCES,
        content_capture=None,
    ) -> None:
        self.conditioner = conditioner
        self.critic = critic
        self.reviser = reviser
        self.grounder = grounder or Grounder()
        self.selection_scorer = selection_scorer
        self.min_sources = min_sources
        # CONTENT-CAP: an optional, observation-only content sink (None = off → zero overhead, zero
        # behavior change, BYTE-IDENTICAL outputs). Threaded to the Generator + written per round below;
        # it never feeds back into any decide/ground/critic path — it is purely out of the trust path.
        self.content_capture = content_capture

    # --- §2.5 intake / degradation -------------------------------------------------------------

    def _degraded(self, task: Task) -> bool:
        """Thin/empty source_set → narrow claims + coverage-risk flag (contracts.md §2.5). The
        binding maps the generic coverage-risk to its own dimension (e.g. F1) at assembly time."""
        return len(task.source_set.sources) < self.min_sources

    # --- §1.11 stopping rule -------------------------------------------------------------------

    def _decide(self, report: GroundingReport, critique: CritiqueReport, run_config: RunConfig) -> bool:
        """pass IFF all_in_source_set AND every gated dimension ≥ its threshold (contracts.md §1.11).
        Unset thresholds (gap 8) mean a dimension is not gated. The reference-integrity gate is the
        non-negotiable precondition: any orphan → revise, never pass."""
        if not report.all_in_source_set:
            return False
        for dimension, threshold in run_config.dimension_thresholds.items():
            ds = critique.dimension_scores.get(dimension)
            if ds is None or ds.score < threshold:
                return False
        return True

    # --- §1.5 run ------------------------------------------------------------------------------

    def run(self, task: Task, run_config: RunConfig) -> tuple[Artifact, "object", "object"]:
        recorder = TraceRecorder()

        # Intake gate (§2.5): refuse to start if the Task isn't ready; else flag degradation.
        refusal = task.intake_refusal()
        if refusal is not None:
            recorder.record(0, "orchestrator", decision=f"refuse: {refusal}")
            raise IntakeRefused(refusal)
        degraded = self._degraded(task)
        if degraded:
            recorder.record(
                0, "orchestrator", output_ref="intake", decision="degrade: thin source_set → narrow + coverage_risk"
            )
        else:
            recorder.record(0, "orchestrator", output_ref="intake", decision="intake ok")

        # Conditioner (once): compile the Condition into obligations + a Budget (§1.5/§1.11).
        # Trace-guard (trace-recording-ownership §3 — same as the critic/reviser sites): a LIVE Blueprint
        # body calls complete() and records its own "blueprint:live" event; the surrogate records nothing
        # → the spine records the fallback "conditioner" event. recorder/round reach the live body via
        # keyword args (the §1.5 compile() domain signature is unchanged). One event per call, both paths.
        pre = len(recorder.trace)
        obligations, _budget = self.conditioner.compile(task, recorder=recorder, round=0)
        if len(recorder.trace) == pre:
            c_model, c_sampling = _role_meta(self.conditioner)
            recorder.record(
                0, "conditioner", model=c_model, sampling=c_sampling,
                input_refs=("task",), output_ref="obligations", decision=f"{len(obligations)} obligations",
            )
        public_obligations = [public_view(o) for o in obligations]
        # CONTENT-CAP-ALL (B, observation-only): the obligation contract the proposal is built against.
        # None-guarded → off unless capture is enabled; never read back into any decide/ground/critic path.
        if self.content_capture is not None:
            self.content_capture.record_conditioner(obligations, _budget)

        inputs = task.inputs()
        evidence_scores: EvidenceScores = inputs.get("evidence_scores", EvidenceScores())
        external_critiques: list = inputs.get("external_critiques", []) or []

        # Generate (round 0): the staged Generator produces the pre-grounding Draft (§1.6). The
        # content_capture sink (None unless capture is on) rides alongside the recorder — the Generator
        # writes the best-of-N candidates + scores to it (observation-only; no behavior change).
        draft = run_generator(
            task, obligations, inputs, self.selection_scorer, recorder, round=0,
            content_capture=self.content_capture,
        )

        # Round loop: Grounder -> Critic -> decide; revise while round < max_rounds (§1.11).
        round = 0
        grounded = None
        critique = CritiqueReport()
        report = GroundingReport(n_references=0, all_in_source_set=False)
        while True:
            grounded, report = self.grounder.ground(draft, task.source_set)
            recorder.record(
                round, "grounder", input_refs=(f"draft@r{round}",), output_ref=f"grounded@r{round}",
                decision=f"all_in_source_set={report.all_in_source_set}; orphans={len(report.orphan_ids)}",
            )
            # CONTENT-CAP (observation-only): snapshot the draft state at this round (round 0 =
            # generated; round n = after the nth revise). Eagerly serialized — no aliasing. CONTENT-CAP-ALL
            # (C): also snapshot the GroundingReport (per-round inv-1 enforcement). Both None-guarded.
            if self.content_capture is not None:
                self.content_capture.record_round(round, draft)
                self.content_capture.record_grounding(round, report)
            # Trace-guard (decisions/2026-06-02-trace-recording-ownership.md §3 — "applies at … the
            # orchestrator's … critic … site"): a LIVE Critic body calls complete() and records its OWN
            # event (real tokens, output_ref="critic:live"); the surrogate Critic records nothing → the
            # spine records the fallback. The recorder + round reach the live body via these generic
            # keyword args (the §1.5 critique() domain signature is unchanged — the surrogate/calibration
            # callers omit them). Guard on the event count so exactly ONE event lands per call, both paths.
            pre = len(recorder.trace)
            critique = self.critic.critique(
                grounded, public_obligations, evidence_scores, external_critiques,
                recorder=recorder, round=round,
            )
            if len(recorder.trace) == pre:
                cr_model, cr_sampling = _role_meta(self.critic)
                recorder.record(
                    round, "critic", model=cr_model, sampling=cr_sampling,
                    input_refs=(f"grounded@r{round}",), output_ref=f"critique@r{round}", decision=critique.decision,
                )
            # CONTENT-CAP (observation-only): persist the full per-round critique (per-dimension scores +
            # justification + repair spans, per-aim segment scores, decision, flagged ids). Read-only — the
            # §1.11 decide below reads the same `critique`, never the sink.
            if self.content_capture is not None:
                self.content_capture.record_critique(round, critique)

            passed = self._decide(report, critique, run_config)
            # §1.11 stopping rule. Default (force_rounds is None): stop on pass OR the max_rounds cap —
            # UNCHANGED, so the byte oracle is untouched. force_rounds set: an exact loop depth that
            # IGNORES the pass (it overrides max_rounds), running precisely `force_rounds` revise rounds.
            # The decide above + every trust gate still run each round — forcing only ADDS revisions; it
            # never skips a gate (inv-1/2/3 untouched, the Reviser still hedges) → it cannot bypass trust.
            if run_config.force_rounds is not None:
                stop = round >= run_config.force_rounds
            else:
                stop = passed or round >= run_config.max_rounds - 1
            # Honesty (FORCE-ROUNDS §4): a forced run must not read as natural convergence. If the Critic
            # PASSED but the loop continues only because force_rounds demands more depth, mark the decision
            # `pass (forced-continue)` (never a bare `pass`) so a Trace reader sees the count was forced.
            # When force_rounds is None this is impossible (passed ⇒ stop) → the string is byte-identical.
            decision = "pass" if passed else "revise"
            if passed and not stop:
                decision = "pass (forced-continue)"
            recorder.record(
                round, "orchestrator", output_ref=f"decision@r{round}", decision=decision,
            )
            if stop:
                break

            # Trace-guard (trace-recording-ownership §3 — same as the critic site): a LIVE Reviser body
            # calls complete() and records its OWN "reviser:live" event; the surrogate records nothing →
            # the spine records the fallback. recorder/round reach the live body via keyword args (the
            # §1.5 revise() domain signature is unchanged). One event per call, both paths.
            # CONTENT-CAP (observation-only): hold the pre-revise draft to diff the Reviser's hedges
            # below. A plain alias when off-by-None-guarded; the Reviser deep-copies, so it is untouched.
            prior_draft = draft if self.content_capture is not None else None
            pre = len(recorder.trace)
            draft = self.reviser.revise(
                draft, critique, external_critiques, critique.flagged_obligations,
                recorder=recorder, round=round,
            )
            if len(recorder.trace) == pre:
                rv_model, rv_sampling = _role_meta(self.reviser)
                recorder.record(
                    round, "reviser", model=rv_model, sampling=rv_sampling,
                    input_refs=(f"grounded@r{round}", f"critique@r{round}"), output_ref=f"draft@r{round + 1}",
                    decision="revised",
                )
            # CONTENT-CAP (observation-only): the exact claim-text changes the Reviser made this round,
            # diffed prior-vs-new (the Reviser itself is untouched).
            if self.content_capture is not None:
                self.content_capture.record_reviser_hedges(round, prior_draft, draft)
            round += 1

        # Exit: assemble the Artifact (binding) + the Audit (deterministic) (§1.4/§1.10).
        artifact = task.assemble_artifact(grounded, obligations, round, degraded)
        overclaim_check = build_overclaim_check(grounded.draft.claims(), evidence_scores)
        unit_tests = [
            UnitTestRow(
                name="inv-1 reference integrity",
                passed=report.all_in_source_set,
                detail=f"orphan_ids={report.orphan_ids}",
            )
        ]
        audit = assemble_audit(report, obligations, critique, overclaim_check, unit_tests)
        return artifact, recorder.trace, audit
