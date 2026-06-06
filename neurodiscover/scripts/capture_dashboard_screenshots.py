#!/usr/bin/env python3
"""Capture dashboard screenshots for docs (input + output pages)."""
from __future__ import annotations

import json
import os
import time
import urllib.request

from playwright.sync_api import sync_playwright

UI = os.environ.get("DASHBOARD_UI", "http://127.0.0.1:8080?api=http://127.0.0.1:5000")
API = os.environ.get("DASHBOARD_API", "http://127.0.0.1:5000")
OUT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "docs", "assets", "images", "dashboard")
)


def seed_demo_run() -> None:
    body = json.dumps({"mode": "demo", "max_papers": 10, "wait": True}).encode()
    req = urllib.request.Request(
        f"{API}/api/run-discovery",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    print(f"Demo run complete — run_id={data.get('run_id')}, recs={len(data.get('recommendations', []))}")


def wait_ready(page) -> None:
    page.goto(UI, wait_until="networkidle", timeout=120_000)
    page.wait_for_selector(".tab-nav", state="visible", timeout=60_000)
    time.sleep(2)


def shot(page, selector: str, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    loc = page.locator(selector)
    loc.wait_for(state="visible", timeout=30_000)
    loc.screenshot(path=path)
    print(f"Wrote {path}")


def main() -> int:
    seed_demo_run()
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        wait_ready(page)

        # Step 1 — configure & run (input page)
        page.locator('[data-view="input"]').click()
        page.wait_for_selector("#viewInput:not(.hidden)", timeout=30_000)
        time.sleep(0.75)
        shot(page, "#viewInput", os.path.join(OUT, "step1-configure-run.png"))

        # Step 2 — discovery results (output page; boot may already land here)
        page.locator('[data-view="results"]').click()
        page.wait_for_selector("#viewResults:not(.hidden)", timeout=30_000)
        page.wait_for_selector("#syntheticCohort .syn-card, #topRecs .rec-card", timeout=30_000)
        time.sleep(1)
        shot(page, "#viewResults", os.path.join(OUT, "step2-discovery-results.png"))
        shot(page, ".output-panel.panel-rank", os.path.join(OUT, "step2-ranked-treatments.png"))
        shot(page, ".output-panel.panel-syn", os.path.join(OUT, "step2-synthetic-cohort.png"))
        page.locator(".audit-collapse").evaluate("el => { el.open = true; }")
        time.sleep(0.5)
        shot(page, ".audit-section", os.path.join(OUT, "step2-audit-evidence.png"))

        # Step 3 — grant proposal tab (viewport; full #viewCua is very tall)
        page.locator('[data-view="cua"]').click()
        page.wait_for_selector("#viewCua:not(.hidden)", timeout=30_000)
        page.wait_for_selector("#cuaReportHost", timeout=30_000)
        page.wait_for_selector("#cuaToc:not(.hidden)", timeout=60_000)
        page.wait_for_selector("#cuaStatusRow:not(.hidden)", timeout=60_000)
        page.wait_for_function(
            """() => {
              const host = document.getElementById('cuaReportHost');
              const layout = host?.shadowRoot?.querySelector('.cua-report-layout');
              const proposal = layout?.querySelector('section.cua-sec-proposal');
              return !!proposal && layout?.firstElementChild?.classList?.contains('cua-sec-proposal');
            }""",
            timeout=90_000,
        )
        time.sleep(1.5)
        page.evaluate(
            """() => {
              const view = document.getElementById('viewCua');
              const main = document.getElementById('cuaMain');
              const top = (main || view)?.offsetTop ?? 0;
              window.scrollTo(0, Math.max(0, top - 12));
            }"""
        )
        time.sleep(1.5)
        path3 = os.path.join(OUT, "step3-grant-proposal.png")
        page.screenshot(path=path3, full_page=False)
        print(f"Wrote {path3}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
