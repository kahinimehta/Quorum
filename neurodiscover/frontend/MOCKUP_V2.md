# Dashboard mockup v2 alignment

Target reference: `neurodiscover_dashboard_mockup_v2.pdf`

To match the PDF pixel-perfect, add a copy to this repo (e.g. `frontend/mockup-v2.pdf`) and open a follow-up issue with screenshots of any gaps.

## Implemented layout (v2 structure)

| Mockup region | Implementation |
|---------------|----------------|
| Header pills | DB LIVE · evidence row count · Synthetic Cohort Layer · DB type |
| KPI strip | Papers · Trials · Grants · Subgroups · Connections |
| Step 1 sidebar | DB tiles + last scan · subgroups with colored dots · agent stepper Done/Ready/Idle |
| Step 1 main | Primary disease field · DB source counts · segmented run/extract · banners · run buttons |
| Recent runs | Run ID · Date · Mode · Evidence · Subgroups · Synthetic · Status (click → Step 2) |
| Step 2 pills | Pipeline complete · synthetic count · subgroups/treatments |
| Pipeline diagram | Data inputs → agents (①–⑥) → three outputs |
| Synthetic panel | Profile line · onset · confidence mini-bar · No PHI pills |
| Ranked panel | Prioritize/Monitor on bars · rec cards with quotes + patient links |
| Hypotheses | H1–H4 · PMID/NCT pills · Conf score · Monitor warning |
| Audit | Agent trace timestamps + synthetic generator step · evidence + synthetic link column |
| Footer | Demo data notice (DEMO-* / cli.py pull) |

## Local preview

```bash
cd neurodiscover/frontend && python3 -m http.server 8080
```

Open http://localhost:8080 → use the large **Step 1 / Step 2** tabs below the KPI strip:

- **Configure & Run Pipeline** — form and run buttons  
- **Discovery Results** — synthetic cohort, ranked outputs, hypotheses  

Drop `mockup-v2.pdf` into `frontend/` for pixel-perfect tweaks against your PDF.
