# Mockup v2 notes (archived)

The dashboard UI is implemented in `index.html` on `main`.

**Canonical doc:** [`../../docs/dashboard.md`](../../docs/dashboard.md) · [`../../docs/developer-reference/dashboard-api.md`](../../docs/developer-reference/dashboard-api.md)

**Quickstart:** [`quickstart.md`](quickstart.md)

Design reference: `neurodiscover_dashboard_mockup_v2.pdf` (add to `frontend/` if you want pixel-perfect comparison in-repo).

Implemented highlights: **three tabs** (Configure & Run · Discovery Results · Grant Proposal), minimal header (DB LIVE + optional run chip), run status strip, Step 2 KPI strip, full-width layout on all tabs (minimal `--page-pad`), Step 2 results (KPI strip above title · profiles · ranked outputs match hypotheses height, scroll when longer · hypotheses, then pipeline diagram, audit & provenance collapsed), recent runs table, Step 3 static grant proposal (corpus/verified-papers KPIs, expanded **proposal**, collapsed **Grant pipeline** + **Pipeline trace & audit**, **`x/y obligations satisfied`**, Jump to nav).
