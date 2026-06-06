#!/usr/bin/env python3
"""Generate docs/cua-f1-innovation-check.pdf."""
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent / "cua-f1-innovation-check.pdf"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_I = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"


class Doc(FPDF):
    def setup_fonts(self):
        self.add_font("U", "", FONT)
        self.add_font("U", "B", FONT_B)
        self.add_font("U", "I", FONT_I)

    def header(self):
        if self.page_no() > 1:
            self.set_font("U", "", 8)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, "CUA — How Innovation Is Checked in F1", align="R", new_x="LMARGIN", new_y="NEXT")

    def footer(self):
        self.set_y(-12)
        self.set_font("U", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"NeuroDiscover / Quorum  ·  Page {self.page_no()}", align="C")

    def h1(self, text: str):
        self.ln(3)
        self.set_font("U", "B", 17)
        self.set_text_color(15, 32, 68)
        self.multi_cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def h2(self, text: str):
        self.ln(2)
        self.set_font("U", "B", 12)
        self.set_text_color(30, 64, 120)
        self.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")

    def h3(self, text: str):
        self.ln(1)
        self.set_font("U", "B", 10.5)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")

    def para(self, text: str):
        self.set_font("U", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)

    def bullet(self, text: str):
        self.set_font("U", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, f"  •  {text}", new_x="LMARGIN", new_y="NEXT")

    def callout(self, text: str):
        self.set_fill_color(238, 242, 255)
        self.set_font("U", "I", 10)
        self.set_text_color(49, 46, 129)
        self.multi_cell(0, 5, text, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def kv_table(self, rows: list[tuple[str, str]]):
        self.set_font("U", "", 9.5)
        col1 = 42
        for k, v in rows:
            self.set_font("U", "B", 9.5)
            self.set_text_color(60, 60, 60)
            self.cell(col1, 5.5, k, new_x="RIGHT", new_y="TOP")
            self.set_font("U", "", 9.5)
            self.set_text_color(30, 30, 30)
            self.multi_cell(0, 5.5, v, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)


def build():
    pdf = Doc()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    pdf.setup_fonts()

    pdf.h1("How CUA Checks Innovation in F1")
    pdf.para(
        "NeuroDiscover / Quorum — Grant Proposal Tab (Step 3). Explains how the Conclusion Update "
        "Agent (CUA) verifies Innovation as part of NIH Factor 1 (F1). Demo reference: bundled graded6 report."
    )

    pdf.h2("Overview")
    pdf.para(
        "Tab 3 (Grant Proposal) shows output from the CUA package — a multi-agent pipeline "
        "that writes an NIH R01 proposal from the evidence corpus. Factor 1 (F1) asks: Should this "
        "project be done? F1 combines Significance, Innovation, and the central hypothesis."
    )
    pdf.callout(
        "Innovation is not a separate dashboard KPI. It is enforced through obligation F1-3 in the "
        "contract and contributes to the aggregate Critic F1 score (1–9) shown in Tab 3."
    )

    pdf.h2("NIH framing: F1 vs F2 vs F3")
    pdf.kv_table([
        ("F1", "Should it be done? Innovation (F1-3) names what is new vs current practice."),
        ("F2", "Can it be done rigorously? Aim methods, pitfalls, expected outcomes."),
        ("F3", "Can this team do it here? Expertise and resources surfaced per aim."),
    ])
    pdf.para("F1 and F2 are scored 1–9 by the Internal Critic. Typical stopping threshold: F1 ≥ 5 and F2 ≥ 5.")

    pdf.h2("The contract: obligation F1-3")
    pdf.para(
        "Before drafting, the Blueprint Planner compiles ~21 checkable obligations from the NIH "
        "Simplified Review Framework."
    )
    pdf.callout(
        "F1-3: Innovation names the specific departure from current concepts, methods, or practice — "
        "not a generic 'novel'."
    )
    pdf.para("Satisfied by: claim id innovation. Check type: critic (qualitative), plus structural code checks.")
    pdf.h3("Related F1 obligations")
    pdf.kv_table([
        ("F1-1", "Significance — specific barrier to progress with ≥1 corpus citation."),
        ("F1-2", "One explicit central hypothesis that follows from the named gap."),
        ("F1-3", "Innovation — specific departure, not generic novelty."),
    ])
    pdf.para("Cross-cutting X-1 and X-2 also apply: every cite must exist in corpus; claims cannot exceed evidence grade.")

    pdf.add_page()

    pdf.h2("Four layers of checking")

    pdf.h3("Layer 1 — Writer (Synthesizer)")
    pdf.para(
        "The Argument Synthesizer must emit a structured innovation field alongside gap, significance, "
        "and central hypothesis."
    )
    pdf.callout(
        "Prompt: Innovation: the specific departure from current concepts/methods/practice "
        "(not a generic 'novel')."
    )
    pdf.para("Missing innovation field → validation failure. Innovation is a framing claim with corpus citations.")

    pdf.h3("Layer 2 — Code (ledger / invariants)")
    pdf.para("mark_ledger() binds F1-3 to claim innovation:")
    pdf.kv_table([
        ("Claim present", "Pass: satisfied_by innovation. Fail: at_risk."),
        ("≥1 evidence_id", "Pass: satisfied (inv-2). Fail: downgraded to at_risk."),
        ("Corpus cites", "Pass: Grounder inv-1 PASS. Fail: orphans dropped; revise."),
        ("Overclaim", "Pass: clean inv-3. Fail: hedge directive and F1 penalty."),
    ])
    pdf.para("Code verifies existence and grounding — not whether the departure is scientifically compelling.")

    pdf.h3("Layer 3 — Best-of-N (Selection Scorer)")
    pdf.para(
        "The Synthesizer writes N independent F1 pitches (four in graded6). The Selection Scorer ranks "
        "them on F1 as a whole (significance + hypothesis + innovation). It rewards grounded specificity "
        "and penalizes vague phrasing. This is a fast picker, not the final judge."
    )

    pdf.h3("Layer 4 — Internal Critic (quality judgment)")
    pdf.bullet("Reads obligation F1-3 and the grounded innovation claim.")
    pdf.bullet("Scores F1 (1–9) for Significance and Innovation together.")
    pdf.bullet("May flag F1-3 if innovation is generic or unmet.")
    pdf.bullet("Applies code penalties for missing targets, overclaims, orphan citations.")
    pdf.para("graded6 final scores: F1 = 7, F2 = 5, F3 = 6.")

    pdf.h2("What passes vs fails")
    pdf.h3("Fails F1-3")
    pdf.bullet("'This project is novel and innovative.'")
    pdf.bullet("Restating the hypothesis without a distinct departure.")
    pdf.bullet("Innovation that duplicates significance without naming what is new.")

    pdf.h3("Passes F1-3 (graded6 pattern)")
    pdf.bullet("Specific departure: biomarker-stratified enrollment, GBA-stratified lysosome intervention.")
    pdf.bullet("Corpus-backed citations (PMIDs, grant ids from evidence store).")
    pdf.bullet("Distinct from significance (why it matters) and F2 aims (how you will do it).")

    pdf.add_page()

    pdf.h2("Dashboard Tab 3 — where to look")
    pdf.kv_table([
        ("Critic F1 KPI", "Aggregate F1 score (includes innovation)."),
        ("The contract", "Full F1-3 requirement text."),
        ("Explored & dropped", "Selection Scorer comparison of F1 candidates."),
        ("Revise rounds", "F1 scores per round in The loop, round by round."),
        ("Audit ledger", "F1-3 row: status, citations, notes: critic."),
    ])
    pdf.para(
        "Tab 3 is static (graded6) and not tied to Step 1/2 run_id. Live runs: python -m cua.nih.run_db."
    )

    pdf.h2("Pipeline summary")
    pdf.para(
        "Blueprint Planner → F1-3 in contract → Synthesizer (innovation claim) → Selection Scorer "
        "(rank F1) → Aim Architect → Grounder (inv-1) → Internal Critic (F1 score, flag F1-3) → "
        "Reviser / Booster → Audit → Tab 3 report."
    )

    pdf.h2("Key takeaway")
    pdf.callout(
        "Innovation in F1 is checked by obligation F1-3: produce a cited innovation claim naming a "
        "specific departure; code ensures it exists and is grounded; the Internal Critic judges "
        "specificity; the result rolls into Critic F1 — not a separate innovation score."
    )

    pdf.ln(2)
    pdf.set_font("U", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(
        0,
        4,
        "Sources: cua/files/conclusion_update_agent_nih_obligations.md, cua/src/cua/nih/obligations.py, "
        "cua/src/cua/roles/synthesizer.py, cua/src/cua/roles/critic.py, docs/dashboard.md",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.output(str(OUT))
    print(OUT)


if __name__ == "__main__":
    build()
