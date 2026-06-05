---
layout: default
title: Problem & significance
nav_order: 2
description: "Unmet need, Pfizer commercial discovery framing, and why agentic research"
---

# Problem & significance

**Track 02 — Autonomous Research:** literature synthesis, hypothesis generation, and evidence tracking.

---

## The gap (Pfizer Commercial Development Discovery)

Current commercial development can only evaluate a **handful of opportunities over months**. Investments rely on **static, point-in-time** expert review at high cost.

The opportunities that most change patient care are often the ones the **existing taxonomy is least equipped to find**:

| Hidden signal | Why experts miss it |
|---------------|---------------------|
| **Subgroup inside a heterogeneous indication** | Portfolio tools aggregate at indication level |
| **Cross-condition mechanism links** | Siloed therapeutic-area review |
| **Emerging evidence after the last review cycle** | Manual synthesis does not scale with publication velocity |

Expert review surfaces what experts **already know to look for**. NeuroDiscover tests whether an **AI-native, continuously updating** pipeline reveals structurally hidden connections.

## Our approach

NeuroDiscover deploys **six sequential agents** on a shared evidence database:

1. **Ingest** — literature, trials, grants (BioMCP, RePORTER, optional web search)  
2. **Subgroup** — distill patient segments from evidence  
3. **Connect** — map subgroup → mechanism → treatment  
4. **Score evidence** — skeptic agent down-weights weak sources  
5. **Score commercial potential** — market and funding signals  
6. **Recommend** — ranked Prioritize / Monitor / Reject with rationale  

Conclusions **update as new rows land** in `evidence` — compressing background research from months toward **hours/days** for a configured query.

## Scientific & commercial significance

- **Discovery efficiency** — Reduce time and cost to identify and triage opportunities  
- **Portfolio ROI** — Surface ranked connections before expensive expert panels  
- **Auditability** — Every recommendation traces to `source_id` rows judges can verify  
- **Generalizable** — Same pipeline for any BioMCP-supported disease via `--disease` / API `query`

{: .highlight }
**Demo note:** The hackathon dashboard ships with **seed subgroup labels and demo source ids** (`DEMO-*`) for offline judging. Live runs use real PMIDs/NCT ids from PubMed and ClinicalTrials.gov.

## Alignment with agentic science literature

Our design follows patterns surveyed in recent work on **agentic scientific discovery**:

- Unified literature + trial retrieval (cf. unified PubMed / trials access)  
- Structured extraction into a **distilled schema** (not raw JSON blobs)  
- **Incremental scan** — skip re-extraction for known sources  
- Append-only **agent trace** (`agent_outputs`) for reproducibility  

### Relevant literature

- Ghareeb, A. E., Chang, B., Mitchener, L., Yiu, A., Szostkiewicz, C. J., Shved, D., Gyimesi, G. J., Laurent, J. M., Wright, S. M., Razzak, M. T., White, A. D., Finnemann, S. C., Hinks, M. M., & Rodriques, S. G. (2026). A multi-agent system for automating scientific discovery. *Nature*, 1–3. [https://doi.org/10.1038/s41586-026-10652-y](https://doi.org/10.1038/s41586-026-10652-y)

- Hartung, T. AI, agentic models and lab automation for scientific discovery — the beginning of scAInce. *Frontiers in AI*. [https://doi.org/10.3389/frai.2025.1649155](https://doi.org/10.3389/frai.2025.1649155)

- Wei, J., Yang, Y., Zhang, X., Chen, Y., Zhuang, X., Gao, Z., Zhou, D., Wang, G., Gao, Z., Cao, J., Qiu, Z., Hu, M., Ma, C., Tang, S., He, J., Song, C., He, X., Zhang, Q., You, C., … Zhou, B. (2025). From AI for Science to Agentic Science: A survey on autonomous scientific discovery. *arXiv*. [https://doi.org/10.48550/arXiv.2508.14111](https://doi.org/10.48550/arXiv.2508.14111)

## Related docs

- [Workflow](workflow/) — per-agent detail  
- [Output examples](output) — JSON and dashboard panels  
