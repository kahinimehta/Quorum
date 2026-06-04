# Dashboard mockup v2 alignment

Target reference: `neurodiscover_dashboard_mockup_v2.pdf`

To match the PDF pixel-perfect, add a copy to this repo (e.g. `frontend/mockup-v2.pdf`) and open a follow-up issue with screenshots of any gaps.

## Implemented layout (v2 structure)

| Mockup region | Implementation |
|---------------|----------------|
| Header | Quorum mark + NeuroDiscover AI + live/run badges |
| KPI strip | Papers · Trials · Grants · Subgroups · Connections |
| Pipeline | Data inputs → agents (①–⑥) → three outputs, with ▼ connectors |
| Left output | Synthetic cohort panel + green safety banner + Patient A–E cards |
| Center output | Ranked outputs + confidence bars + ranked list |
| Right output | Research hypotheses + continuous update |
| Footer audit | Agent trace + evidence library table |

## Local preview

```bash
cd neurodiscover/frontend && python3 -m http.server 8080
```

Open http://localhost:8080 → use the large **Step 1 / Step 2** tabs below the KPI strip:

- **Configure & Run Pipeline** — form and run buttons  
- **Discovery Results** — synthetic cohort, ranked outputs, hypotheses  

Drop `mockup-v2.pdf` into `frontend/` for pixel-perfect tweaks against your PDF.
