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
from pathlib import Path

from ..capture import ContentCapture
from ..orchestrator import Orchestrator
from ..roles import BlueprintPlanner, InternalCritic, Reviser, SelectionScorer
from ..types import Status
from .adapters import task_from_db
from .grant_call import default_grant_call, load_grant_call
from .ingestion import IngestionConfig, attach_writer_view, ingest
# Reuse the dump format + RunConfig + output dir from the fixture runner (testdata-free at import). The
# orchestrator wiring is OUR OWN (`_build_orchestrator` below) so the demo runs best-of-N — see there.
from .run import OUTPUTS_DIR, RUN_CONFIG, _dump

# Ingestion Layer config (INGEST-1 v2) — the binding-side, rule-based rerank-and-bound applied to the
# assembled corpus before the orchestrator (see `run_db`). Defaults documented on `IngestionConfig`.
INGEST_CONFIG = IngestionConfig()


def _build_orchestrator(content_capture: ContentCapture | None = None) -> Orchestrator:
    """Wire the roles for this entrypoint with best-of-N re-enabled — LIVE-4 (was n=1 at LIVE-INT-A).

    A live `SelectionScorer()` (vs the LIVE-INT-A `None`) sends `generation._produce_one` down the
    best-of-N path for any stage whose §2.4 `n_samples>1` (the Synthesizer's 3): N candidates are
    produced and the Selection Scorer ranks them on the stage's reward dimension (F1), best proceeds.
    With `CUA_LIVE` set that is N real Opus writer calls per produce (the parallel test-time-compute
    axis, design §0) + the live Sonnet ranking call — materially pricier; this is the demo/final config,
    economy iteration stays n=1. Offline (surrogates deterministic) the Proposal/Audit are UNCHANGED —
    best-of-N picks among identical candidates — so this only adds sample/selection events to the Trace.

    The AimArchitect/Critic/Reviser (`n_samples=1`) stay single-shot. Same wiring as
    `cua.nih.run._build_orchestrator` now (both keep `SelectionScorer()`; the fixture byte oracle is
    untouched — that path always had it)."""
    return Orchestrator(
        conditioner=BlueprintPlanner(),
        critic=InternalCritic(),
        reviser=Reviser(),
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
) -> int:
    """Run CUA over a neurodiscover DB (read-only) and emit Proposal/Trace/Audit files. Returns an
    exit code (0 = ok). No DB write of any kind; the only writes are the artifact files.

    CONTENT-CAP: with capture ON (`--capture-content` / `CUA_CAPTURE_CONTENT`) an additional,
    observation-only `<run>.content.json` is emitted (best-of-N candidates + scores, per-round drafts,
    Reviser hedge diffs, full per-round critique). Capture is OUT of the trust path — the Proposal/Trace/
    Audit bytes are IDENTICAL whether capture is on or off; OFF (default) emits no `content.json`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    capture = ContentCapture() if _capture_enabled(capture_content) else None

    grant_call = _grant_call(foa)
    conn, label = _open_readonly(db)
    print(f"CUA run_db — db={label} run_id={run_id} foa={'(loaded)' if foa else 'default'}")
    if capture is not None:
        print(f"[capture] content capture ON → will emit {run_id}.content.json (observation-only)")
    print("-" * 70)
    try:
        # READ-ONLY: the adapter issues SELECT only; we never write the DB.
        task = task_from_db(conn, run_id, grant_call)
        # Ingestion Layer (INGEST-1 v2): rerank-and-bound the assembled corpus into a diversified top-K
        # writer VIEW BEFORE the orchestrator runs. ID-PRESERVING — `attach_writer_view` shapes the live
        # writer's view ONLY; `task.source_set.sources` stays the FULL corpus, so the Grounder's
        # cite-∈-corpus gate (inv-1) and the Proposal's references are unchanged. Deterministic + rule-based;
        # pure of the corpus (the DB has already been read into the task — no further DB access).
        ingestion = ingest(task.source_set, topic=getattr(grant_call, "title", ""), config=INGEST_CONFIG)
        attach_writer_view(task.source_set, ingestion)
        # Print the ingestion summary UP-FRONT — before the (long, live) orchestrator phase — so the
        # operator immediately sees the corpus was bounded and the LLM phase has begun (not a hang). The
        # per-role progress then streams to STDERR from `llm.complete()` (live-only). `[ok]` still lands at
        # the end. run_db is its OWN entrypoint (never the fixture oracle path), so this print is byte-safe.
        print(_ingestion_summary(ingestion), flush=True)
        artifact, trace, audit = _build_orchestrator(capture).run(task, RUN_CONFIG)
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
    args = parser.parse_args(argv)

    # Import here so the binding stays import-light; surfaces an intake refusal as a clean non-zero.
    from ..orchestrator import IntakeRefused

    try:
        return run_db(args.db, args.run_id, args.foa, Path(args.out_dir), args.capture_content)
    except IntakeRefused as e:
        print(f"[refuse] {args.run_id}: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # surface any wiring/DB error as a clean non-zero
        print(f"[ERROR] {args.run_id}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
