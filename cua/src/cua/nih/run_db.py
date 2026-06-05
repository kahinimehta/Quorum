"""run_db.py — NIH binding: OUR entrypoint to run CUA over a neurodiscover DB → file artifacts.

Implements the integration entrypoint (adaption.md #12 — our OWN entrypoint; upstream `cli.py` is NOT
edited). Reads the upstream DB READ-ONLY via the INT-2 adapter, reranks-and-bounds the assembled corpus
through the binding-side **Ingestion Layer** (INGEST-1 v2 — deterministic key_finding clustering → a
diversified top-K writer view; ID-PRESERVING, the full corpus stays the citation gate's referent), runs
the best-of-N Orchestrator (`_build_orchestrator`), and writes Proposal/Trace/Audit + the Ingestion
drop-audit (`<run>.ingestion.json`) as files (#13). Those four LOCAL files are the ONLY output — no DB
write of any kind (#14 no `recommendations`/formula, #15 `agent_outputs` OFF, #16 no `build`/DDL).

    python -m cua.nih.run_db --db <url|path> --run-id <id> [--foa <grantcall.json>] [--out-dir <dir>]

Governing: contracts.md §1.5 (Orchestrator), §1.10 (Trace/Audit), §2.1 (Proposal). Owner: INT-3 (builder 1).

Posture: READ-ONLY consumer. The only DB access is `SELECT` (through the adapter, which is SELECT-only
by construction); we additionally open the connection read-only (defense-in-depth). The only filesystem
writes are the four artifact files under the output dir (Proposal/Trace/Audit + the Ingestion drop-audit).

Offline + deterministic: the DB connection opens only at run time (never at import); psycopg is imported
lazily and only for a Postgres URL; all roles are deterministic offline surrogates (reused from
`cua.nih.run`); no clock, no RNG. Importing this module pulls in NO `testdata` (run.py imports testdata
only lazily inside its fixture `run()`, which this module never calls).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

from ..capture import ContentCapture
from ..orchestrator import Orchestrator
from ..roles import BlueprintPlanner, InternalCritic, Reviser, SelectionScorer
from ..types import RunConfig, Status
from .adapters import task_from_db
from .grant_call import default_grant_call, load_grant_call
from .ingestion import IngestionConfig, attach_contradiction_ids, attach_writer_view, ingest
# Reuse the dump format + RunConfig + output dir from the fixture runner (testdata-free at import). The
# orchestrator wiring is OUR OWN (`_build_orchestrator` below) so the demo runs best-of-N — see there.
from .run import OUTPUTS_DIR, RUN_CONFIG, _dump

# SCALE-CFG: the compute-sweep defaults are DERIVED from the fixture runner's RUN_CONFIG so they can
# never drift from "today" — no flag ⇒ these exact values ⇒ byte-identical. `--max-rounds` is the
# sequential (revise) axis; `--bar` the uniform F1=F2 stopping threshold; `--n-samples` the Synthesizer's
# best-of-N parallel axis (overridden instance-side below, so the role class default stays untouched).
_DEFAULT_MAX_ROUNDS = RUN_CONFIG.max_rounds
_DEFAULT_BAR = next(iter(RUN_CONFIG.dimension_thresholds.values()), 5)
SYNTHESIZER_STAGE = "synthesizer"  # the best-of-N (F1) generation stage `--n-samples` scales
# FORCE-ROUNDS: the sane upper cap for `--force-rounds N` (an exact loop depth; 0 = round-0-only). A
# generic compute bound — keeps a fat-fingered N from spinning the (live, pricey) loop unboundedly.
_FORCE_ROUNDS_MAX = 10

# Ingestion Layer config (INGEST-1 v2) — the binding-side, rule-based rerank-and-bound applied to the
# assembled corpus before the orchestrator (see `run_db`). Defaults documented on `IngestionConfig`.
INGEST_CONFIG = IngestionConfig()


def _build_orchestrator(
    content_capture: ContentCapture | None = None, corpus=None, topic: str = ""
) -> Orchestrator:
    """Wire the roles for this entrypoint with best-of-N re-enabled — LIVE-4 (was n=1 at LIVE-INT-A).

    A live `SelectionScorer()` (vs the LIVE-INT-A `None`) sends `generation._produce_one` down the
    best-of-N path for any stage whose §2.4 `n_samples>1` (the Synthesizer's 3): N candidates are
    produced and the Selection Scorer ranks them on the stage's reward dimension (F1), best proceeds.
    With `CUA_LIVE` set that is N real Opus writer calls per produce (the parallel test-time-compute
    axis, design §0) + the live Sonnet ranking call — materially pricier; this is the demo/final config,
    economy iteration stays n=1. Offline (surrogates deterministic) the Proposal/Audit are UNCHANGED —
    best-of-N picks among identical candidates — so this only adds sample/selection events to the Trace.

    The AimArchitect/Critic stay single-shot. The Reviser is constructed WITH the corpus + topic so its
    live F2-booster (F2-BOOSTER) can mine the un-selected corpus on the revise path — this entrypoint is
    the ONLY one that injects a corpus, so the booster runs here and nowhere else (the fixture byte oracle
    builds a bare `Reviser()` → the booster is inert → that path is untouched). Same wiring as
    `cua.nih.run._build_orchestrator` otherwise (both keep `SelectionScorer()`)."""
    return Orchestrator(
        conditioner=BlueprintPlanner(),
        critic=InternalCritic(),
        # content_capture also reaches the Reviser so its F2-booster records provenance (CONTENT-CAP-ALL D).
        reviser=Reviser(corpus=corpus, topic=topic, content_capture=content_capture),
        selection_scorer=SelectionScorer(),
        content_capture=content_capture,  # None unless capture is on → observation-only, byte-identical
    )


def _capture_enabled(flag: bool) -> bool:
    """CONTENT-CAP gate: ON iff `--capture-content` (flag) OR `CUA_CAPTURE_CONTENT` is set truthy.
    Default OFF (env unset/empty/0/false/no/off → off) → nothing changes, no `content.json` emitted."""
    if flag:
        return True
    val = os.environ.get("CUA_CAPTURE_CONTENT", "")
    return val.strip().lower() not in ("", "0", "false", "no", "off")


def _run_config(max_rounds: int, bar: int, force_rounds: int | None = None) -> RunConfig:
    """SCALE-CFG (sequential axis): a per-run RunConfig — `max_rounds` revise passes + a uniform F1=F2
    stopping `bar`. The threshold KEYS are taken from RUN_CONFIG (not magic strings), so at the defaults
    (max_rounds=3, bar=5, force_rounds=None) this is value-identical to the fixture runner's RUN_CONFIG →
    byte-identical; higher values only WIDEN the loop (no new behavior). RunConfig is not serialized into
    any artifact.

    FORCE-ROUNDS: `force_rounds` (default None ⇒ unchanged) pins the loop to EXACTLY that many revise
    rounds regardless of pass, overriding `max_rounds` in the orchestrator's §1.11 break."""
    return RunConfig(
        max_rounds=max_rounds,
        dimension_thresholds={k: bar for k in RUN_CONFIG.dimension_thresholds},
        force_rounds=force_rounds,
    )


def _apply_n_samples(task, n_samples: int) -> int:
    """SCALE-CFG (parallel axis): override the Argument Synthesizer's best-of-N count for THIS run only.
    Sets an INSTANCE-level `config` on the synthesizer stage (via dataclasses.replace), shadowing the
    role's class-level RoleConfig — so the class default is untouched and there is no cross-run leak
    (each run_db call builds a fresh task). Returns the number of stages updated. The Selection Scorer
    ranks the N candidates on F1; n_samples=1 simply turns best-of-N off for that stage (a valid low end
    of the sweep). Only the existing §1.8 knob is widened — no new behavior."""
    updated = 0
    for stage in getattr(task, "generator", []):
        if getattr(stage, "name", None) == SYNTHESIZER_STAGE:
            stage.config = replace(stage.config, n_samples=n_samples)
            updated += 1
    return updated


def _is_postgres(db: str) -> bool:
    return db.startswith("postgresql://") or db.startswith("postgres://")


def _open_readonly(db: str):
    """Open a READ-ONLY connection from `--db` (defense-in-depth; the adapter is SELECT-only anyway).
    Returns (connection, label). The CALLER (this module) owns and closes it — the adapter, given a
    connection object, never closes it. SQLite uses a `file:<abspath>?mode=ro` URI (mode=ro can never
    create or write the file); Postgres sets the session read-only."""
    if _is_postgres(db):
        import psycopg  # lazy — importing run_db must not require/contact psycopg

        conn = psycopg.connect(db)
        try:
            conn.read_only = True  # psycopg3: subsequent transactions are read-only
        except Exception:
            pass
        return conn, "postgres (read-only session)"
    uri = db if db.startswith("file:") else f"file:{Path(db).resolve()}?mode=ro"
    return sqlite3.connect(uri, uri=True), uri


def _grant_call(foa: str | None):
    """`load_grant_call(--foa)` if a config path is given, else the INT-1 boundary default."""
    return load_grant_call(foa) if foa else default_grant_call()


def _ingestion_summary(ingestion) -> str:
    """A one-line operator projection of the Ingestion Layer drop-audit: corpus_n → top-K view, cluster
    count, and (prominently) how many clusters are flagged `possible_contradiction` (the safety net)."""
    contras = [c for c in ingestion.clusters if c.possible_contradiction]
    return (
        f"[ingest] corpus_n={ingestion.corpus_n} -> view={len(ingestion.selected_ids)} "
        f"(top_k={ingestion.config.top_k}) clusters={len(ingestion.clusters)} "
        f"possible_contradiction={len(contras)}"
        + (f" {sorted(c.cluster_id for c in contras)}" if contras else "")
    )


def _summary(run_id: str, artifact, audit) -> str:
    """Mirror `cua.nih.run`'s per-run inv-1/2/3 line (read-only projection of the Audit)."""
    gr = audit.grounding_report
    satisfied = [o for o in audit.obligation_ledger if o.status == Status.SATISFIED]
    overclaims = [r.claim for r in audit.overclaim_check if not r.ok]
    inv1 = "PASS" if gr.all_in_source_set else f"FAIL orphans={gr.orphan_ids}"
    inv2 = "PASS" if all(o.evidence_ids for o in satisfied) else "FAIL"
    inv3 = "PASS" if not overclaims else f"flags={overclaims}"
    return (
        f"[ok] {run_id} r={artifact.revision_round} refs={gr.n_references} aims={len(artifact.aims)} "
        f"sat={len(satisfied)} | inv-1={inv1} inv-2={inv2} inv-3={inv3}"
    )


def run_db(
    db: str,
    run_id: str,
    foa: str | None = None,
    out_dir: Path = OUTPUTS_DIR,
    capture_content: bool = False,
    n_samples: int | None = None,
    max_rounds: int | None = None,
    bar: int | None = None,
    no_booster: bool = False,
    force_rounds: int | None = None,
) -> int:
    """Run CUA over a neurodiscover DB (read-only) and emit Proposal/Trace/Audit files. Returns an
    exit code (0 = ok). No DB write of any kind; the only writes are the artifact files.

    BOOSTER-POLISH: `no_booster` (default False → boost, today's behavior) builds the Reviser WITHOUT a
    corpus so the live F2-booster is inert — the matched no-booster arm of an N-vs-N A/B. Nothing else
    changes (ingestion/writer_view/writers/critic/reviser-hedge run identically); only the booster on/off.

    CONTENT-CAP: with capture ON (`--capture-content` / `CUA_CAPTURE_CONTENT`) an additional,
    observation-only `<run>.content.json` is emitted (best-of-N candidates + scores, per-round drafts,
    Reviser hedge diffs, full per-round critique). Capture is OUT of the trust path — the Proposal/Trace/
    Audit bytes are IDENTICAL whether capture is on or off; OFF (default) emits no `content.json`.

    SCALE-CFG: `n_samples`/`max_rounds`/`bar` sweep the two test-time-compute axes (design §0/§5) —
    best-of-N (parallel) and revise rounds (sequential). `None` ⇒ today's defaults (3 / 3 / 5) ⇒
    byte-identical; the knobs only WIDEN the existing §1.8/§1.11 surface. Composes with capture: a scaled
    run's content.json records all N candidates + the per-round critique (quality vs compute).

    FORCE-ROUNDS: `force_rounds` (default None ⇒ today's pass-based behavior, byte-identical) pins the loop
    to EXACTLY N revise rounds regardless of pass (it overrides `max_rounds`) — a fixed depth that
    guarantees the revise leg (and the F2 booster) fires. Bounded 0 ≤ N ≤ 10; out-of-range ⇒ clean
    non-zero exit. It only ADDS revisions; every trust gate still runs each round (no bypass)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # FORCE-ROUNDS: reject an out-of-range depth up front (before any DB/orchestrator work) → clean
    # non-zero exit. None (unset) skips the check ⇒ today's pass-based path, byte-identical.
    if force_rounds is not None and not (0 <= force_rounds <= _FORCE_ROUNDS_MAX):
        print(
            f"[ERROR] {run_id}: --force-rounds must be 0..{_FORCE_ROUNDS_MAX} (got {force_rounds})",
            file=sys.stderr,
        )
        return 2

    capture = ContentCapture() if _capture_enabled(capture_content) else None
    # SCALE-CFG: resolve the compute knobs (None ⇒ the RUN_CONFIG-derived default ⇒ byte-identical).
    eff_max_rounds = _DEFAULT_MAX_ROUNDS if max_rounds is None else max_rounds
    eff_bar = _DEFAULT_BAR if bar is None else bar
    run_config = _run_config(eff_max_rounds, eff_bar, force_rounds=force_rounds)

    grant_call = _grant_call(foa)
    conn, label = _open_readonly(db)
    print(f"CUA run_db — db={label} run_id={run_id} foa={'(loaded)' if foa else 'default'}")
    if capture is not None:
        print(f"[capture] content capture ON → will emit {run_id}.content.json (observation-only)")
    if no_booster:
        print("[booster] OFF (--no-booster) — Reviser built without a corpus (matched A/B baseline)")
    if any(v is not None for v in (n_samples, max_rounds, bar, force_rounds)):
        n_label = n_samples if n_samples is not None else "default"
        # FORCE-ROUNDS honesty: when set, surface `force_rounds=N` on the scale line so a forced run is
        # never mistaken for natural convergence (the per-round forced-continue is marked in the Trace).
        fr_label = f" force_rounds={force_rounds}" if force_rounds is not None else ""
        print(f"[scale] n_samples={n_label} max_rounds={eff_max_rounds} bar={eff_bar}{fr_label}")
    print("-" * 70)
    try:
        # READ-ONLY: the adapter issues SELECT only; we never write the DB.
        task = task_from_db(conn, run_id, grant_call)
        # SCALE-CFG (parallel axis): widen the Synthesizer's best-of-N for THIS run only (instance-side;
        # the role class default is untouched). None ⇒ no override ⇒ the no-flag path is literally today's.
        if n_samples is not None:
            _apply_n_samples(task, n_samples)
        # Ingestion Layer (INGEST-1 v2): rerank-and-bound the assembled corpus into a diversified top-K
        # writer VIEW BEFORE the orchestrator runs. ID-PRESERVING — `attach_writer_view` shapes the live
        # writer's view ONLY; `task.source_set.sources` stays the FULL corpus, so the Grounder's
        # cite-∈-corpus gate (inv-1) and the Proposal's references are unchanged. Deterministic + rule-based;
        # pure of the corpus (the DB has already been read into the task — no further DB access).
        ingestion = ingest(task.source_set, topic=getattr(grant_call, "title", ""), config=INGEST_CONFIG)
        attach_writer_view(task.source_set, ingestion)
        # F2-BOOSTER: also attach the `possible_contradiction` member-ids so the booster can prioritize the
        # contrasting un-selected papers (mirrors `attach_writer_view`; binding-side instance attr only —
        # `task.source_set.sources` and inv-1 are untouched).
        attach_contradiction_ids(task.source_set, ingestion)
        # Print the ingestion summary UP-FRONT — before the (long, live) orchestrator phase — so the
        # operator immediately sees the corpus was bounded and the LLM phase has begun (not a hang). The
        # per-role progress then streams to STDERR from `llm.complete()` (live-only). `[ok]` still lands at
        # the end. run_db is its OWN entrypoint (never the fixture oracle path), so this print is byte-safe.
        print(_ingestion_summary(ingestion), flush=True)
        # The Reviser is built WITH the corpus + topic so its live F2-booster mines the un-selected corpus
        # (the booster is gated on this corpus; the fixture oracle's bare `Reviser()` keeps it inert).
        # BOOSTER-POLISH: `--no-booster` passes corpus=None → the booster is inert (the A/B baseline arm),
        # while ingestion/writer_view (attached above) + every other role still run identically.
        boost_corpus = None if no_booster else task.source_set
        artifact, trace, audit = _build_orchestrator(
            capture, corpus=boost_corpus, topic=getattr(grant_call, "title", "")
        ).run(task, run_config)
    finally:
        try:
            conn.close()  # close only what we opened (the adapter does not close a passed-in conn)
        except Exception:
            pass

    # The artifact files (adaption.md #13), mirroring run.py's dump format, PLUS the Ingestion Layer
    # drop-audit (`<run>.ingestion.json`) — the honesty mechanism (binding-side; the §1.10 Audit is
    # untouched). With grade flat, the drop-audit is what makes a swallowed contradiction (a mixed-polarity
    # cluster) or a one-sided selection VISIBLE to the operator and a judge — `possible_contradiction` kept
    # prominent. All four writes are local files; no DB write of any kind.
    (out_dir / f"{run_id}.proposal.json").write_text(_dump(artifact), encoding="utf-8")
    (out_dir / f"{run_id}.trace.jsonl").write_text(trace.to_jsonl() + "\n", encoding="utf-8")
    (out_dir / f"{run_id}.audit.json").write_text(_dump(audit), encoding="utf-8")
    (out_dir / f"{run_id}.ingestion.json").write_text(_dump(ingestion.audit()), encoding="utf-8")

    # CONTENT-CAP (gated, SEPARATE artifact): the observation-only content stream — emitted ONLY when
    # capture is on. The four core artifacts above are byte-identical whether capture is on or off; this
    # file merely ADDS the best-of-N candidates/scores, per-round drafts, hedge diffs, + full critique.
    if capture is not None:
        (out_dir / f"{run_id}.content.json").write_text(_dump(capture.to_dict()), encoding="utf-8")

    print(_summary(run_id, artifact, audit))
    print("-" * 70)
    cap_note = " + Content capture" if capture is not None else ""
    print(f"OK — emitted Proposal/Trace/Audit + Ingestion drop-audit{cap_note} for run_id={run_id} to {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cua.nih.run_db",
        description="Run CUA over a neurodiscover DB (read-only) and emit Proposal/Trace/Audit files.",
    )
    parser.add_argument("--db", required=True, help="SQLite path or Postgres URL (opened READ-ONLY)")
    parser.add_argument("--run-id", required=True, dest="run_id", help="run id (artifact filenames + provenance)")
    parser.add_argument("--foa", default=None, help="path to a GrantCall JSON config (else the INT-1 default)")
    parser.add_argument("--out-dir", default=str(OUTPUTS_DIR), dest="out_dir", help=f"output dir (default {OUTPUTS_DIR})")
    parser.add_argument(
        "--capture-content",
        action="store_true",
        dest="capture_content",
        help="also emit <run>.content.json (observation-only: best-of-N candidates/scores, per-round "
        "drafts, hedge diffs, full critique). Default OFF; or set CUA_CAPTURE_CONTENT.",
    )
    # SCALE-CFG compute knobs (default None ⇒ today's run: n=3, max_rounds=3, bar=5 → byte-identical).
    parser.add_argument(
        "--n-samples", type=int, default=None, dest="n_samples",
        help="Argument Synthesizer best-of-N count, the PARALLEL compute axis (default: 3)",
    )
    parser.add_argument(
        "--max-rounds", type=int, default=None, dest="max_rounds",
        help="max revise rounds, the SEQUENTIAL compute axis (default: 3)",
    )
    parser.add_argument(
        "--bar", type=int, default=None, dest="bar",
        help="uniform F1=F2 stopping threshold; a higher bar makes the revise loop work harder (default: 5)",
    )
    # BOOSTER-POLISH: opt-out of the live F2-booster (default OFF → boost, today's behavior) → the matched
    # no-booster arm of an N-vs-N A/B. Only the booster is affected; every other role runs identically.
    parser.add_argument(
        "--no-booster", action="store_true", dest="no_booster",
        help="build the Reviser without a corpus so the live F2-booster is inert (A/B baseline; default: boost)",
    )
    # FORCE-ROUNDS: run EXACTLY N revise rounds regardless of pass (overrides --max-rounds). Default None ⇒
    # today's pass-based behavior, byte-identical. Bounded 0..10 (validated in run_db → clean non-zero exit).
    parser.add_argument(
        "--force-rounds", type=int, default=None, dest="force_rounds",
        help=f"run exactly N revise rounds regardless of pass (0..{_FORCE_ROUNDS_MAX}; overrides --max-rounds; "
        "default: pass-based)",
    )
    args = parser.parse_args(argv)

    # Import here so the binding stays import-light; surfaces an intake refusal as a clean non-zero.
    from ..orchestrator import IntakeRefused

    try:
        return run_db(
            args.db, args.run_id, args.foa, Path(args.out_dir), args.capture_content,
            args.n_samples, args.max_rounds, args.bar, args.no_booster, args.force_rounds,
        )
    except IntakeRefused as e:
        print(f"[refuse] {args.run_id}: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # surface any wiring/DB error as a clean non-zero
        print(f"[ERROR] {args.run_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
