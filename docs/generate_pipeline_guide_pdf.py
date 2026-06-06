#!/usr/bin/env python3
"""Generate NeuroDiscover pipeline guide PDF (plain-language + technical)."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "neurodiscover-pipeline-guide.pdf"


class GuidePDF(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "NeuroDiscover Pipeline Guide", align="R")
        self.ln(12)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def title_page(self) -> None:
        self.add_page()
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(20, 60, 100)
        self.multi_cell(0, 12, "NeuroDiscover (Quorum)\nPipeline & Infrastructure Guide")
        self.ln(8)
        self.set_font("Helvetica", "", 12)
        self.set_text_color(60, 60, 60)
        self.multi_cell(
            0,
            7,
            "Part I: Plain-language overview (no coding background required)\n"
            "Part II: Technical summary for developers\n"
            "Part III: Demo-only vs generalizable (with justifications)\n"
            "Part IV: Hackathon judging rubric alignment",
        )
        self.ln(6)
        self.set_font("Helvetica", "I", 10)
        self.multi_cell(0, 6, "Generated from project docs: docs/workflow/, agent-io.md, design.md")

    def h1(self, text: str) -> None:
        self.ln(4)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(20, 60, 100)
        self.multi_cell(0, 9, text)
        self.ln(2)

    def h2(self, text: str) -> None:
        self.ln(3)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(30, 80, 120)
        self.multi_cell(0, 8, text)
        self.ln(1)

    def h3(self, text: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 7, text)
        self.ln(1)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def bullet(self, text: str) -> None:
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        x = self.get_x()
        self.cell(6, 5.5, "-")
        self.multi_cell(0, 5.5, text)
        self.set_x(x)
        self.ln(0.5)

    def code_line(self, text: str) -> None:
        self.set_font("Courier", "", 9)
        self.set_text_color(50, 50, 50)
        self.set_fill_color(245, 245, 245)
        self.multi_cell(0, 5, f"  {text}", fill=True)
        self.ln(1)

    def table_row(self, cols: list[str], widths: list[int], bold: bool = False) -> None:
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 9)
        for col, w in zip(cols, widths):
            self.cell(w, 7, col, border=1)
        self.ln()

    def part_divider(self, part_num: int, title: str, subtitle: str) -> None:
        self.add_page()
        self.set_font("Helvetica", "B", 20)
        self.set_text_color(20, 60, 100)
        self.multi_cell(0, 10, f"Part {part_num}")
        self.ln(2)
        self.set_font("Helvetica", "B", 16)
        self.multi_cell(0, 9, title)
        self.ln(4)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 6, subtitle)


def build_plain_language(pdf: GuidePDF) -> None:
    pdf.part_divider(
        1,
        "Plain-Language Overview",
        "For readers with no coding experience. Uses analogies instead of implementation detail.",
    )

    pdf.h1("What NeuroDiscover Does")
    pdf.body(
        "NeuroDiscover automates commercial drug-discovery research. Instead of experts "
        "spending months manually reading papers and debating opportunities, six specialized "
        "AI assistants (agents) run in sequence. Each agent reads what previous agents wrote "
        "in a shared database (the blackboard) and adds its own findings."
    )
    pdf.body(
        "The goal: find hidden patient subgroups inside a disease, connect them to biological "
        "mechanisms and treatments, score scientific and commercial strength, and output ranked "
        "recommendations (Prioritize / Monitor / Reject)."
    )

    pdf.h2("The Problem It Solves")
    pdf.bullet("Subgroup inside a heterogeneous disease - portfolio tools often aggregate at indication level.")
    pdf.bullet("Cross-condition mechanism links - therapeutic areas are reviewed in silos.")
    pdf.bullet("Emerging evidence after the last review cycle - manual synthesis does not scale.")

    pdf.h2("The Blackboard (Shared Database)")
    pdf.body("Agents do not call each other directly. They read and write SQL tables:")
    widths = [52, 128]
    pdf.table_row(["Table", "Plain meaning"], widths, bold=True)
    pdf.table_row(["evidence", "One card per paper, trial, or grant"], widths)
    pdf.table_row(["subgroups", "Official patient segment definitions"], widths)
    pdf.table_row(["treatment_connections", "Subgroup -> mechanism -> treatment links"], widths)
    pdf.table_row(["connection_evidence", "Which sources support each link"], widths)
    pdf.table_row(["recommendations", "Final ranked advice"], widths)
    pdf.table_row(["agent_outputs", "Audit log per pipeline run"], widths)

    pdf.h2("The Six Agents")
    pdf.h3("Agent 1 - Literature Synthesis (The Research Librarian)")
    pdf.body(
        "Searches PubMed, bioRxiv (optional), ClinicalTrials.gov, and NIH grants. "
        "Extracts structured fields: subgroup, mechanism, treatment, key_result. "
        "Writes evidence rows and links them to seed subgroups when names match exactly."
    )
    pdf.bullet("Input: external scientific APIs (BioMCP, RePORTER)")
    pdf.bullet("Output: evidence, subgroup_evidence, scan_state, agent_outputs")

    pdf.h3("Agent 2 - Patient Subgroup (The Patient Classifier)")
    pdf.body(
        "Groups evidence by subgroup label and writes canonical definitions to subgroups. "
        "Example demo names: GBA-mutation PD, LRRK2 PD, Alpha-synuclein-high PD."
    )
    pdf.bullet("Input: evidence rows with subgroup populated")
    pdf.bullet("Output: subgroups, agent_outputs")

    pdf.h3("Agent 3 - Treatment Connection (The Matchmaker)")
    pdf.body(
        "Builds triples: patient subgroup + biological mechanism + treatment. "
        "Counts supporting sources and records which papers/trials back each link."
    )
    pdf.bullet("Input: subgroups + evidence with mechanism and treatment")
    pdf.bullet("Output: treatment_connections, connection_evidence, agent_outputs")

    pdf.h3("Agent 4 - Evidence Scoring (The Skeptic)")
    pdf.body(
        "Scores how convincing each connection is (0-100). Considers evidence count and "
        "source types: literature, trials (stronger), grants. Scores update when new papers land."
    )
    pdf.bullet("Input: connections from Agent 3 + linked evidence")
    pdf.bullet("Output: treatment_connections.evidence_strength, agent_outputs")

    pdf.h3("Agent 5 - Commercial Discovery (The Business Analyst)")
    pdf.body(
        "Estimates commercial potential (0-100) using heuristics: evidence volume, "
        "subgroup keywords (GBA, LRRK2), mechanism class, treatment presence."
    )
    pdf.bullet("Input: scored connections from Agent 4")
    pdf.bullet("Output: treatment_connections.commercial_potential, agent_outputs")

    pdf.h3("Agent 6 - Conclusion Update (The Decision Maker)")
    pdf.body(
        "Combines scores into confidence and tiers. Formula: "
        "confidence = evidence_strength x 0.55 + commercial_potential x 0.45."
    )
    pdf.bullet("Prioritize: confidence >= 80")
    pdf.bullet("Monitor: 65 <= confidence < 80")
    pdf.bullet("Reject: confidence < 65")
    pdf.bullet("Output: recommendations, agent_outputs")
    pdf.body(
        "Optional CUA package (cua/): separate, heavier Agent 6 that writes an NIH grant "
        "proposal to local files. Read-only on DB; not part of dashboard pipeline."
    )

    pdf.h2("Infrastructure (Four Layers)")
    pdf.bullet("Database - SQLite locally or Supabase Postgres (team shared, ~307 evidence rows live).")
    pdf.bullet("Orchestrator - Runs agents 1-6 in order; shared run_id; commits after each agent.")
    pdf.bullet("API server - FastAPI reads tables; serves dashboard JSON.")
    pdf.bullet("Dashboard - Single-page UI at http://127.0.0.1:8080; polls agent_outputs for live progress.")

    pdf.h2("Run Modes")
    widths2 = [40, 55, 85]
    pdf.table_row(["Mode", "Behavior", "When"], widths2, bold=True)
    pdf.table_row(["demo", "Offline/sample data; caps papers for agents 2-6", "Safe presentations"], widths2)
    pdf.table_row(["agents-only", "Skip literature; rescore existing DB", "Team Supabase dashboard"], widths2)
    pdf.table_row(["scan", "Incremental pull; skip known source_ids", "Cheap updates"], widths2)
    pdf.table_row(["full", "Live PubMed + trials + optional grants", "Fresh research"], widths2)

    pdf.h2("End-to-End Example")
    pdf.body(
        "Agent 3 finds: GBA-mutation PD -> lysosomal dysfunction -> GCase activation "
        "(8 papers, 1 trial). Agent 4: evidence_strength = 78. Agent 5: commercial_potential = 85. "
        "Agent 6: confidence = (78 x 0.55) + (85 x 0.45) = 81.15 -> Prioritize."
    )

    pdf.h2("Trust & Safety")
    pdf.bullet("No invented PMIDs/NCT ids - real source_id or DEMO-* placeholders only.")
    pdf.bullet("Append-only agent_outputs trace per run_id.")
    pdf.bullet("cli.py build blocked on live Supabase (truncates tables).")
    pdf.bullet("Synthetic cohort in UI is generated, not stored PHI.")


def build_technical(pdf: GuidePDF) -> None:
    pdf.part_divider(
        2,
        "Technical Summary",
        "For developers familiar with Python, SQL, and REST APIs. Module paths and contracts.",
    )

    pdf.h1("Architecture")
    pdf.body(
        "Blackboard pattern: agents in neurodiscover/agents/ are decoupled modules. "
        "orchestrator.py routes pipeline modes, assigns run_id, persists agent return dicts to SQL, "
        "and logs agent_outputs after each step. Agents 2-6 do not import each other."
    )
    pdf.body("Layer map:")
    pdf.code_line("ingestion/     - published_pull, biorxiv_pull, grants_pull (no scoring)")
    pdf.code_line("agents/        - literature_agent, patient_subgroup_agent, ...")
    pdf.code_line("orchestrator.py - demo | scan | full | agents-only")
    pdf.code_line("api_server.py  - FastAPI; read-only queries for dashboard")
    pdf.code_line("frontend/index.html - vanilla JS; polls /api/run-status")
    pdf.code_line("db.py          - SQLite or Postgres via SUPABASE_DATABASE_URL")

    pdf.h2("Pipeline Sequence")
    pdf.code_line("A1 Literature -> A2 Subgroups -> A3 Connections -> A4 Evidence -> A5 Commercial -> A6 Conclusions")
    pdf.body(
        "Agent 1 may run as subprocess (demo/scan via cli.py) or in-process (full mode). "
        "Agents 2-6 always in-process. Orchestrator commits after each agent for live stepper polling."
    )

    pdf.h2("Agent I/O Contract")
    widths = [22, 38, 60, 60]
    pdf.table_row(["#", "Module", "Reads", "Writes"], widths, bold=True)
    pdf.table_row(
        ["1", "literature_agent.py", "BioMCP, RePORTER", "evidence, subgroup_evidence, scan_state"],
        widths,
    )
    pdf.table_row(["2", "patient_subgroup_agent.py", "evidence (subgroup NOT NULL)", "subgroups"], widths)
    pdf.table_row(
        ["3", "treatment_connection_agent.py", "evidence + subgroups (in-memory)", "treatment_connections, connection_evidence"],
        widths,
    )
    pdf.table_row(
        ["4", "evidence_scoring_agent.py", "connections + matching evidence", "UPDATE evidence_strength"],
        widths,
    )
    pdf.table_row(
        ["5", "commercial_discovery_agent.py", "scored_connections in-memory", "UPDATE commercial_potential"],
        widths,
    )
    pdf.table_row(
        ["6", "orchestrator.py (ranking)", "scored treatment_connections", "recommendations"],
        widths,
    )

    pdf.h3("Agent 1 - Literature")
    pdf.body("CLI entrypoints:")
    pdf.code_line("python3 cli.py pull --disease 'Parkinson disease' --max 150")
    pdf.code_line("python3 cli.py pull --include-preprints 20 --with-fulltext")
    pdf.code_line("python3 cli.py pull-grants --limit 30")
    pdf.code_line("python3 cli.py scan --max 5   # incremental; skips LLM for known source_ids")
    pdf.body("EXTRACT_BACKEND=nebius|ollama|none for structured extraction. UNIQUE(source_type, source_id) dedups.")
    pdf.body("Key evidence columns: source_type, source_id, subgroup, mechanism, treatment, key_result, access_type.")

    pdf.h3("Agent 4 - Evidence Scoring Heuristics")
    pdf.body("Pre-scale 0-10 in Python; orchestrator _scale_score() x10 -> DB 0-100:")
    pdf.code_line("base = 4.0 + min(4.5, evidence_count * 0.22)")
    pdf.code_line("+0.6 if literature present; +0.8 if trial; +0.4 if grant; cap 10.0")

    pdf.h3("Agent 5 - Commercial Heuristics")
    pdf.code_line("base = 5.5 + min(2.5, evidence_count * 0.12)")
    pdf.code_line("+0.9 GBA/LRRK2 subgroup; +0.6 alpha-synuclein; +0.7 lysosomal/kinase; +0.6 if treatment set")

    pdf.h3("Agent 6 - Ranking")
    pdf.code_line("confidence = evidence_strength * 0.55 + commercial_potential * 0.45")
    pdf.code_line("INSERT INTO recommendations (run_id, connection_id, subgroup, treatment, confidence, tier, rationale)")
    pdf.body("CUA optional path: python -m cua.nih.run_db --db <url|path> -> cua/outputs/*.json|html (SELECT-only).")

    pdf.h2("Database")
    pdf.body("Schema source of truth: neurodiscover/schema.sql (SQLite), schema.pg.sql (Postgres).")
    pdf.body("Local: neurodiscover/neurodiscover.db (gitignored). Team: SUPABASE_DATABASE_URL session pooler.")
    pdf.body("Never run cli.py build on Supabase - truncates all tables. Use scan/pull to add evidence.")
    pdf.body("Validate after schema changes: python3 cli.py validate")

    pdf.h2("Orchestrator & API")
    pdf.body("Entry: POST /api/run-discovery (or make dashboard -> cli.py dashboard).")
    pdf.body("Run status (run_status.py): Complete = 6 agents in trace + >=1 recommendation.")
    pdf.body("Dashboard launcher: FastAPI :5000, static UI :8080. Supabase path uses agents-only on startup.")

    pdf.h2("Key Files")
    pdf.code_line("neurodiscover/orchestrator.py")
    pdf.code_line("neurodiscover/pipeline_mode.py")
    pdf.code_line("neurodiscover/api_server.py")
    pdf.code_line("neurodiscover/cli.py")
    pdf.code_line("docs/developer-reference/agent-io.md")
    pdf.code_line("docs/developer-reference/database.md")
    pdf.code_line("docs/workflow/index.md")

    pdf.h2("Quick Start (Developer)")
    pdf.code_line("cd neurodiscover && pip install -r requirements.txt")
    pdf.code_line("cp .env.example .env   # SUPABASE_DATABASE_URL optional")
    pdf.code_line("make dashboard         # local demo or Supabase agents-only")
    pdf.code_line("python3 cli.py pull --max 10   # add evidence locally")
    pdf.code_line("python3 cli.py query \"SELECT COUNT(*) FROM evidence\"")

    pdf.h2("Scoring Data Flow")
    pdf.body(
        "Agent 3 returns connection dicts -> orchestrator upserts treatment_connections + connection_evidence. "
        "Agent 4 updates evidence_strength per connection_id. Agent 5 updates commercial_potential. "
        "Agent 6 reads both scores, computes confidence, writes recommendations with shared run_id. "
        "Dashboard reads recommendations + agent_outputs WHERE run_id = latest."
    )


def build_demo_vs_generalizable(pdf: GuidePDF) -> None:
    pdf.part_divider(
        3,
        "Demo vs Generalizable",
        "What is hackathon-demo scaffolding vs production-ready core, and what to change to run any indication.",
    )

    pdf.h1("Summary")
    pdf.body(
        "NeuroDiscover ships two experiences: (A) a safe offline demo for judges with seeded "
        "DEMO-* placeholders, and (B) a live pipeline on team Supabase with 307 real evidence "
        "rows (228 papers, 39 trials, 40 grants). The six-agent blackboard architecture, "
        "BioMCP ingestion, and SQL schema are indication-agnostic. Parkinson's-specific "
        "tuning exists mainly in seed data, scoring heuristics, and one static UI tab."
    )

    pdf.h2("Demo-Only (Hackathon Showcase)")
    widths = [48, 62, 70]
    pdf.table_row(["Item", "What it is", "Why demo-only"], widths, bold=True)
    pdf.table_row(
        ["demo run mode", "cli.py demo / API mode=demo", "No live PubMed calls; safe on stage"],
        widths,
    )
    pdf.table_row(
        ["DEMO-* source IDs", "seed_data.json placeholders", "Offline judging without network"],
        widths,
    )
    pdf.table_row(
        ["Five seed subgroups", "GBA-mutation PD, LRRK2 PD, etc.", "Illustrative PD taxonomy for empty DB"],
        widths,
    )
    pdf.table_row(
        ["max_papers cap", "Default 10 in dashboard demo", "Fast startup on judge laptops"],
        widths,
    )
    pdf.table_row(
        ["Synthetic cohort UI", "Generated profiles, not stored", "Visual storytelling; no PHI/HIPAA risk"],
        widths,
    )
    pdf.table_row(
        ["Step 3 CUA tab", "Static graded6.html bundle", "Heavy LLM grant run too slow for live demo"],
        widths,
    )
    pdf.table_row(
        ["Local SQLite build", "make dashboard seeds neurodiscover.db", "One-command laptop demo"],
        widths,
    )
    pdf.table_row(
        ["Default disease label", "Parkinson's in UI defaults", "Pfizer track framing; not a code lock"],
        widths,
    )

    pdf.h2("Production-Ready Today (Already Generalizable)")
    pdf.bullet(
        "Literature pull: --disease and --query on any BioMCP-supported condition "
        "(full and scan modes)."
    )
    pdf.bullet(
        "Real evidence on team Supabase: 307 rows with real PMIDs, NCT ids, grant numbers."
    )
    pdf.bullet(
        "Subgroup discovery from extraction: Agent 2 creates subgroups from evidence labels, "
        "not only seed names."
    )
    pdf.bullet(
        "Incremental scan: skip LLM re-extraction for known source_ids (cost control at scale)."
    )
    pdf.bullet(
        "Dual database: same agents on SQLite (local) or Postgres (Supabase) via db.py."
    )
    pdf.bullet(
        "Audit trail: every run logs agent_outputs with shared run_id; recommendations cite source_id."
    )
    pdf.bullet(
        "CUA package (optional): python -m cua.nih.run_db reads any populated DB (read-only)."
    )

    pdf.h2("Needs Change for Full Generalizability")
    widths2 = [52, 58, 70]
    pdf.table_row(["Gap", "Change required", "Justification"], widths2, bold=True)
    pdf.table_row(
        [
            "Agent 5 PD keywords",
            "Config or LLM market signals per TA",
            "Heuristics hardcode GBA/LRRK2/alpha-synuclein bonuses",
        ],
        widths2,
    )
    pdf.table_row(
        [
            "Grant title inference",
            "Parameterize evidence_tags.py",
            "Grant rows infer PD subgroups from title keywords today",
        ],
        widths2,
    )
    pdf.table_row(
        [
            "Extraction prompt vocab",
            "Indication-specific subgroup ontology file",
            "Improves consistency when seed subgroups absent",
        ],
        widths2,
    )
    pdf.table_row(
        [
            "Commercial external data",
            "Integrate market/pipeline APIs (e.g. Tavily)",
            "Agent 5 has no live web search in current code",
        ],
        widths2,
    )
    pdf.table_row(
        [
            "Legacy API path",
            "Rename /api/discover/parkinsons",
            "Route is already indication-agnostic; name is cosmetic",
        ],
        widths2,
    )
    pdf.table_row(
        [
            "CUA dashboard tab",
            "Run-scoped CUA per run_id",
            "Today static graded6; pipeline rankings are run-scoped",
        ],
        widths2,
    )
    pdf.table_row(
        [
            "Study quality weighting",
            "Use study_type, sample_size in Agent 4",
            "Columns exist; skeptic uses count + source_type only today",
        ],
        widths2,
    )

    pdf.h2("How to Run Another Indication (Minimal Path)")
    pdf.code_line("POST /api/run-discovery  { mode: full, disease: ALS, query: C9orf72 }")
    pdf.code_line("python3 cli.py pull --disease ALS --query C9orf72 --max 150")
    pdf.body(
        "No schema migration required. Rankings will reflect extracted subgroups and evidence. "
        "For best commercial scores, add indication-specific keyword rules in "
        "commercial_discovery_agent.py or replace heuristics with external market data."
    )

    pdf.h2("Honest Scope Boundaries")
    pdf.bullet("No FHIR or EHR integration - literature/trials/grants only (appropriate for Track 02).")
    pdf.bullet("No genomics APIs - subgroups come from publication text, not variant calls.")
    pdf.bullet(
        "Agent 6 dashboard ranking is formula-based (no LLM) - fast and auditable; CUA is the deep LLM path."
    )


def build_hackathon_rubric(pdf: GuidePDF) -> None:
    pdf.part_divider(
        4,
        "Hackathon Judging Rubric Alignment",
        "Track 02 - Autonomous Research. Team Quorum. Final Showcase June 6, 2025.",
    )

    pdf.h1("Challenge Framing")
    pdf.body(
        "NeuroDiscover addresses Pfizer Commercial Development Discovery: finding hidden patient "
        "subgroups, connecting them to mechanisms and treatments, and ranking portfolio opportunities "
        "with auditable evidence - compressing months of expert review toward hours/days."
    )

    pdf.h2("Criterion 1: Problem Identification & Significance (20%)")
    pdf.body("Target level: Accomplished to Exceptional (4-5/5)")
    pdf.bullet(
        "Clearly defined unmet need: portfolio tools miss subgroups inside heterogeneous diseases, "
        "cross-mechanism links, and post-review-cycle evidence."
    )
    pdf.bullet(
        "Biomedical grounding: 307 real PubMed/trial/grant rows on Supabase; recommendations trace "
        "to verifiable source_id values."
    )
    pdf.bullet(
        "Real-world impact: discovery efficiency, portfolio ROI, continuous update as evidence grows."
    )
    pdf.bullet(
        "Literature alignment: blackboard multi-agent pattern matches Nature 2026 and agentic-science surveys."
    )

    pdf.h2("Criterion 2: Technical Implementation (25%)")
    pdf.body("Target level: Accomplished to Exceptional (4-5/5)")
    pdf.bullet(
        "Working six-agent pipeline: literature -> subgroups -> connections -> evidence score -> "
        "commercial -> recommendations."
    )
    pdf.bullet(
        "Real biomedical data: BioMCP (PubMed + ClinicalTrials.gov), NIH RePORTER grants, "
        "optional bioRxiv and OA full text."
    )
    pdf.bullet(
        "AI integration: Nebius/Ollama structured extraction; optional CUA multi-role LLM grant engine."
    )
    pdf.bullet(
        "Architecture: contract-first SQL blackboard, dual SQLite/Postgres, FastAPI + live progress polling."
    )
    pdf.bullet(
        "Extensibility: new indication via disease/query parameter; new agent = new module + orchestrator step."
    )
    pdf.body(
        "Gap to note honestly: no FHIR/genomics APIs yet; Agent 5 commercial scoring is heuristic "
        "(documented in Part III)."
    )

    pdf.h2("Criterion 3: Creativity & Innovation (20%)")
    pdf.body("Target level: Accomplished to Exceptional (4-5/5)")
    pdf.bullet(
        "Novel application: skeptic + commercial dual scoring with explicit confidence formula "
        "(55% evidence / 45% commercial)."
    )
    pdf.bullet(
        "Continuous discovery: incremental scan skips known sources; rankings shift when corpus grows."
    )
    pdf.bullet(
        "Two-tier Agent 6: fast auditable dashboard rankings + optional deep CUA NIH proposal path."
    )
    pdf.bullet(
        "Synthetic cohort generator: communicates patient-segment story without storing PHI."
    )

    pdf.h2("Criterion 4: Team Composition & Collaboration (10%)")
    pdf.body("Target level: Exceptional (5/5)")
    pdf.bullet("Alia Merchant - strategy, agents 2-5, CUA grant engine.")
    pdf.bullet("Amy He - agent infrastructure, orchestrator, commercial signals.")
    pdf.bullet("Ayelet Peres - literature agent, ingestion, schema, Supabase, validation.")
    pdf.bullet("Kahini Mehta - orchestrator, API, dashboard, docs site, integration.")
    pdf.bullet("William Yakah - workflow design, demo narrative, cross-agent usability.")
    pdf.body(
        "Blackboard contract (agent-io.md, schema.sql) enabled parallel agent development without "
        "merge conflicts - each member owned a distinct layer."
    )

    pdf.h2("Criterion 5: Presentation Skills (15%)")
    pdf.body("Target level: Accomplished (4/5)")
    pdf.bullet(
        "One-command demo: make dashboard -> live stepper, evidence browser, ranked treatments."
    )
    pdf.bullet(
        "Public docs site: neurodiscover.github.io with workflow, API, and screenshots."
    )
    pdf.bullet(
        "This guide: plain-language + technical + demo/generalizable + rubric in one PDF."
    )
    pdf.bullet(
        "Judge-verifiable outputs: click through to real PMIDs/NCT ids on team DB; DEMO-* clearly labeled."
    )

    pdf.h2("Criterion 6: Execution & Professionalism (10%)")
    pdf.body("Target level: Accomplished to Exceptional (4-5/5)")
    pdf.bullet("Safety: cli.py build blocked on live Supabase; no invented citation IDs.")
    pdf.bullet("Validation: cli.py validate after schema changes; extraction QA hooks.")
    pdf.bullet("Documentation: AGENTS.md, developer-reference/, GitHub Pages, CONTRIBUTING.")
    pdf.bullet("Reproducibility: append-only agent_outputs per run_id; mode labels in run history.")

    pdf.h2("Suggested Judge Talking Points")
    pdf.bullet(
        "Show team Supabase run (agents-only or full) for real PMIDs - then explain demo mode for offline safety."
    )
    pdf.bullet(
        "Walk one recommendation: subgroup -> mechanism -> treatment -> supporting papers -> confidence tier."
    )
    pdf.bullet(
        "Emphasize generalizability: change disease/query, same pipeline; Part III lists honest gaps."
    )
    pdf.bullet(
        "Optional deep dive: Step 3 CUA graded6 as proof-of-concept for grant-scale Agent 6 output."
    )

    pdf.h2("Estimated Rubric Strength by Criterion")
    widths = [95, 35, 50]
    pdf.table_row(["Criterion", "Weight", "Team confidence"], widths, bold=True)
    pdf.table_row(["Problem Identification & Significance", "20%", "High (4-5)"], widths)
    pdf.table_row(["Technical Implementation", "25%", "High (4-5)"], widths)
    pdf.table_row(["Creativity & Innovation", "20%", "High (4-5)"], widths)
    pdf.table_row(["Team Composition & Collaboration", "10%", "Very high (5)"], widths)
    pdf.table_row(["Presentation Skills", "15%", "Strong (4)"], widths)
    pdf.table_row(["Execution & Professionalism", "10%", "High (4-5)"], widths)


def main() -> None:
    pdf = GuidePDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.title_page()
    build_plain_language(pdf)
    build_technical(pdf)
    build_demo_vs_generalizable(pdf)
    build_hackathon_rubric(pdf)
    pdf.output(str(OUT))
    print(OUT)


if __name__ == "__main__":
    main()
