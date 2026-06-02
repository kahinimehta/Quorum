"""Print extraction validation summaries after pull."""
from __future__ import annotations

from validation.consistency import batch_validate


def print_validation_report(
    new_findings: list[dict],
    *,
    batch_result: dict | None = None,
    pubtator_result: dict | None = None,
    dropped: int = 0,
) -> dict:
    """Print human-readable report; return combined stats dict."""
    print("\n=== Evidence Extraction Validation Report ===")
    print(f"New rows processed: {len(new_findings) + dropped}")

    if batch_result is None:
        batch_result = batch_validate(new_findings)

    total = batch_result["total"]
    passed = batch_result["passed"]
    failed = batch_result["failed"]
    rate = batch_result["pass_rate"]
    print("\n=== Consistency Validation ===")
    if total:
        print(f"✓ {passed} rows pass all checks ({rate:.0%})")
        print(f"✗ {failed} rows fail")
        if dropped:
            print(f"→ Dropped {dropped} row(s) (--strict-pull)")
        if failed and batch_result["failed_rows"][:3]:
            for row in batch_result["failed_rows"][:3]:
                print(f"  - {row['source_id']}: {', '.join(row['issues'][:2])}")
    else:
        print("(no new rows to validate)")

    if pubtator_result and pubtator_result.get("sampled"):
        print(f"\n=== PubTator Grounding (sample n={pubtator_result['sampled']}) ===")
        print(
            f"Entity overlap: genes={pubtator_result['genes_avg']:.2f}, "
            f"diseases={pubtator_result['diseases_avg']:.2f}, "
            f"chemicals={pubtator_result['chemicals_avg']:.2f}"
        )
        print(
            f"Average: {pubtator_result['average_overlap']:.2f} — "
            f"{pubtator_result['confidence']} confidence"
        )
    elif pubtator_result is not None:
        print("\n=== PubTator Grounding ===")
        print("(skipped — no literature PMIDs in sample)")

    print("\n=== Spot-check Recommendation ===")
    print("Run: python3 cli.py spot-check --count 15")
    print("Fill in spot_check_results.csv, then: python3 cli.py spot-check --score")

    ready = rate >= 0.7 if total else True
    if pubtator_result and pubtator_result.get("sampled"):
        ready = ready and pubtator_result["average_overlap"] >= 0.5
    print("\n" + ("→ Ready for Saturday demo ✓" if ready else "→ Review failed rows / run spot-check before demo"))

    return {
        "consistency": batch_result,
        "pubtator": pubtator_result,
        "dropped": dropped,
        "demo_ready_estimate": ready,
    }
