"""scenarios.py — the five Fixture scenarios [test-data].

Implements: test_data_contract §4 (named scenarios), §2 (synthetic corpus), §3 (evidence),
            §5 (Expectations), §6 (determinism). Brief: build/briefs/S1_fixtures.md.
Populates : contracts.md §2.3 NIHGrantTask.input_contract (required{GrantCall, corpus,
            EvidenceAssessment}; optional{subgroups, treatments, commercial}).
Generic role: stand-in upstream inputs · NIH binding: corpus / EvidenceAssessment / GrantCall.
Owner: S1 (builder 2).  Fixtures, not agents — no live search/grading/modeling (test-data preamble).

The five scenarios (test-data §4):
    clean_high_grade  — coherent gap, mostly strong/moderate, citable corpus → happy path (expect pass)
    thin_corpus       — few papers, coverage gaps → degradation (narrow claims + F1-risk; §2.5)
    low_grade_bait    — weak/minimal evidence under a tempting strong narrative → overclaim check (§1.12)
    fabrication_bait  — a claim whose only support is a paper ABSENT from corpus → inv-1 negative
    unscored_claim    — a claim with NO EvidenceAssessment entry → default minimal + flag (§2.5)

Determinism (test-data §6): every builder takes a `seed`; the only seed-derived content is each
synthetic paper's FAKE `resolvable_id` (so the seed is load-bearing yet reproducible). All other
content is fixed. `intentionally_broken()` exists only to prove `validate()` has teeth (brief
done-criterion); it is NOT one of the five and `validate()` MUST reject it.

Topics are synthetic but realistic; key_findings are stand-ins, not real literature.
"""

from __future__ import annotations

import random

from .types import (
    CommercialLandscape,
    EvidenceAssessment,
    EvidenceEntry,
    Expectations,
    ExternalCritique,
    Fixture,
    Grade,
    GrantCall,
    Paper,
    SourceSet,
    Subgroup,
    Treatment,
)

# Canonical default seed per scenario (test-data §6). Re-running a builder with the same seed
# reproduces a byte-identical Fixture (verified in selfcheck via `digest`).
DEFAULT_SEEDS: dict[str, int] = {
    "clean_high_grade": 1001,
    "thin_corpus": 1002,
    "low_grade_bait": 1003,
    "fabrication_bait": 1004,
    "unscored_claim": 1005,
}

# Real, resolvable identifiers for the resolve-path smoke-test (clean_high_grade only; flag real=True).
# Resolution is NOT asserted (test-data §2) — these exercise the Grounder's resolve ADAPTER, not
# content fidelity, so the surrounding bibliographic fields stay synthetic. (Jinek et al. 2012,
# Science — a famously real CRISPR DOI/PMID pair.)
_REAL_DOI = "10.1126/science.1225829"
_REAL_PMID = "22745249"


# --- deterministic fake-id minting -------------------------------------------------------------


def _fake_doi(rng: random.Random) -> str:
    """Plausibly-formatted but FAKE DOI (test-data §2). Won't resolve via Crossref."""
    return f"10.{rng.randint(1000, 9999)}/synth.{rng.randint(100000, 999999)}"


def _fake_pmid(rng: random.Random) -> str:
    """Plausibly-formatted but FAKE PMID (test-data §2). Won't resolve via NCBI E-utilities."""
    return str(rng.randint(10_000_000, 39_999_999))


def _assign_resolvable_ids(papers: list[Paper], rng: random.Random) -> None:
    """Mint a fake resolvable_id for every paper whose `resolvable_id` is left empty, alternating
    DOI/PMID by position (decision A — PMID vs DOI — is OPEN, so fixtures stub BOTH formats;
    OPEN.md A). Papers that already carry a (real) resolvable_id are left untouched."""
    for i, p in enumerate(papers):
        if p.resolvable_id:
            continue
        p.resolvable_id = _fake_doi(rng) if i % 2 == 0 else _fake_pmid(rng)


def _grant_call(mechanism: str, title: str, foa_id: str) -> GrantCall:
    """A complete GrantCall (mechanism + limits KNOWN, so the agent does not refuse to start; §2.5)."""
    return GrantCall(
        mechanism=mechanism,
        title=title,
        foa_id=foa_id,
        specific_aims_page_limit=1,
        research_strategy_page_limit=12,
        due_date="2025-10-05",
    )


# ================================================================================================
# 1. clean_high_grade — happy path: coherent gap, mostly strong/moderate, citable corpus.
#    expect pass, no overclaim. Carries optionals (subgroups/treatments/commercial) to raise the
#    ceiling, and two REAL resolvable ids for the resolve smoke-test (test-data §2).
# ================================================================================================


def clean_high_grade(seed: int = DEFAULT_SEEDS["clean_high_grade"]) -> Fixture:
    rng = random.Random(seed)
    papers = [
        Paper(
            id="SYNTH-UC-001",
            authors=["Okafor R", "Lindqvist M", "Haddad S"],
            year=2021,
            title="Fecal butyrate depletion in active ulcerative colitis: a meta-analysis",
            venue="Cell Host & Microbe",
            resolvable_id="",  # minted (fake)
            key_finding="Pooled meta-analysis (k=18, n=2,140) shows fecal butyrate reduced ~45% in active UC vs remission.",
        ),
        Paper(
            id="SYNTH-UC-002",
            authors=["Mbeki T", "Romero V"],
            year=2022,
            title="Topical butyrate for induction of remission in UC: a randomized trial",
            venue="Gastroenterology",
            resolvable_id="",
            key_finding="RCT (n=240): topical butyrate increased clinical remission vs placebo (OR 2.1, 95% CI 1.4-3.2).",
        ),
        Paper(
            id="SYNTH-UC-003",
            authors=["Nakamura H", "Owusu D"],
            year=2020,
            title="GPR109A is required for butyrate-induced colonic Treg expansion",
            venue="Immunity",
            resolvable_id="",
            key_finding="Gpr109a-/- mice lose butyrate-induced Treg expansion and show worsened DSS colitis.",
        ),
        Paper(
            id="SYNTH-UC-004",
            authors=["Petrov A", "Singh R", "Kone F"],
            year=2023,
            title="Low butyrate-producer abundance predicts UC relapse: a prospective cohort",
            venue="Gut",
            resolvable_id="",
            key_finding="Prospective cohort (n=312): low Faecalibacterium abundance predicts 12-mo relapse (HR 1.8, 95% CI 1.2-2.6).",
        ),
        # Resolve smoke-test papers: REAL resolvable ids, synthetic bibliographic fields (test-data §2).
        Paper(
            id="SYNTH-UC-005",
            authors=["Delacroix P"],
            year=2019,
            title="Colonic SCFA transport dynamics (resolve smoke-test record)",
            venue="J. Physiol.",
            resolvable_id=_REAL_DOI,
            key_finding="SCFA uptake kinetics in colonocytes constrain luminal butyrate bioavailability.",
            real=True,
        ),
        Paper(
            id="SYNTH-UC-006",
            authors=["Ferreira L"],
            year=2018,
            title="GPR109A expression atlas in gut mucosa (resolve smoke-test record)",
            venue="Mucosal Immunol.",
            resolvable_id=_REAL_PMID,
            key_finding="GPR109A is expressed on colonic epithelium and lamina propria macrophages.",
            real=True,
        ),
    ]
    _assign_resolvable_ids(papers, rng)

    evidence = EvidenceAssessment(
        {
            "clm-sig-burden": EvidenceEntry(
                grade=Grade.STRONG,
                evidence_features={"design": "meta-analysis", "k": 18, "n": 2140, "consistency": "high"},
                support_source_ids=["SYNTH-UC-001"],
            ),
            "clm-central-hyp": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "RCT + mechanistic", "n": 240, "effect_size": "OR 2.1"},
                support_source_ids=["SYNTH-UC-002", "SYNTH-UC-003"],
            ),
            "clm-mech-gpr109a": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "knockout mouse", "replication": "2 labs", "ROB": "low"},
                support_source_ids=["SYNTH-UC-003", "SYNTH-UC-006"],
            ),
            "clm-relapse-marker": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "prospective cohort", "n": 312, "effect_size": "HR 1.8"},
                support_source_ids=["SYNTH-UC-004"],
            ),
            "clm-aim2-rescue": EvidenceEntry(
                grade=Grade.STRONG,
                evidence_features={"design": "RCT", "n": 240, "effect_size": "OR 2.1", "ROB": "low"},
                support_source_ids=["SYNTH-UC-002"],
            ),
            "clm-innovation": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "mechanistic rationale", "novelty": "first GPR109A-targeted induction"},
                support_source_ids=["SYNTH-UC-003", "SYNTH-UC-005"],
                caveats=["innovation framing is mechanistic, not yet clinically demonstrated"],
            ),
        }
    )

    return Fixture(
        name="clean_high_grade",
        seed=seed,
        grant_call=_grant_call("R01", "Restoring GPR109A-butyrate signaling in ulcerative colitis", "PAR-25-101"),
        corpus=SourceSet(papers),
        evidence=evidence,
        expectations=Expectations(
            expect_pass=True,
            expected_overclaim_claim_ids=[],
            expected_orphan_ids=[],
            min_obligations_satisfied=8,
        ),
        subgroups=[
            Subgroup(
                name="treatment-naive UC",
                definition="newly diagnosed, no prior biologic exposure",
                rationale="butyrate axis least perturbed; cleanest test of mechanism",
            ),
            Subgroup(
                name="anti-TNF refractory UC",
                definition="loss of response to >=1 anti-TNF agent",
                rationale="highest unmet need; orthogonal mechanism",
            ),
        ],
        treatments=[
            Treatment(
                name="topical butyrate",
                modality="luminal enema",
                target="GPR109A / HDAC",
                development_stage="phase 2",
            ),
        ],
        commercial=CommercialLandscape(
            grant_contribution="De-risks a GPR109A agonist program by establishing the colonic Treg mechanism.",
            market_note="UC biologics market large; oral SCFA-mimetic is a differentiated entry.",
            competitors=["anti-TNF biosimilars", "JAK inhibitors"],
            ip_position="composition-of-matter on GPR109A agonist series (stand-in)",
        ),
    )


# ================================================================================================
# 2. thin_corpus — degradation path: few papers, coverage gaps. The agent must narrow claims and
#    raise an F1 risk flag (§2.5). Invariants still pass on a faithful narrow draft (expect_pass=True);
#    the degradation signal is behavioral (narrowing + F1-risk), not an invariant failure. No optionals.
# ================================================================================================


def thin_corpus(seed: int = DEFAULT_SEEDS["thin_corpus"]) -> Fixture:
    rng = random.Random(seed)
    papers = [
        Paper(
            id="SYNTH-RA-001",
            authors=["Adeyemi K", "Brandt H"],
            year=2022,
            title="Vagus nerve stimulation in rheumatoid arthritis: an open-label pilot",
            venue="Ann. Rheum. Dis.",
            resolvable_id="",
            key_finding="Open-label pilot (n=17): vagus nerve stimulation reduced DAS28 over 12 weeks.",
        ),
        Paper(
            id="SYNTH-RA-002",
            authors=["Costa M", "Yilmaz E"],
            year=2021,
            title="alpha7-nAChR agonism suppresses TNF and arthritis severity in mice",
            venue="J. Exp. Med.",
            resolvable_id="",
            key_finding="alpha7nAChR agonist reduced serum TNF and arthritis severity in collagen-induced arthritis mice.",
        ),
    ]
    _assign_resolvable_ids(papers, rng)

    evidence = EvidenceAssessment(
        {
            "clm-sig-gap": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "open-label pilot", "n": 17, "blinding": "none"},
                support_source_ids=["SYNTH-RA-001"],
                caveats=["small, unblinded; coverage gap on human mechanism"],
            ),
            "clm-central-hyp": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "pilot + preclinical", "human_n": 17},
                support_source_ids=["SYNTH-RA-001", "SYNTH-RA-002"],
                caveats=["human evidence thin; mechanism mostly preclinical"],
            ),
            "clm-mech-a7": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "mechanistic mouse", "effect": "TNF suppression", "ROB": "moderate"},
                support_source_ids=["SYNTH-RA-002"],
            ),
        }
    )

    return Fixture(
        name="thin_corpus",
        seed=seed,
        grant_call=_grant_call("R21", "Cholinergic anti-inflammatory modulation of RA flares", "PAR-25-102"),
        corpus=SourceSet(papers),
        evidence=evidence,
        expectations=Expectations(
            expect_pass=True,  # narrow but valid: a faithful degraded draft satisfies inv-1/2/3
            expected_overclaim_claim_ids=[],
            expected_orphan_ids=[],
            min_obligations_satisfied=4,  # coarse floor; degraded scope (F1-risk flagged behaviorally)
        ),
    )


# ================================================================================================
# 3. low_grade_bait — weak/minimal evidence dressed in a tempting strong (causal) narrative. The
#    agent MUST hedge the baited claims to L1/L2 (§1.12). At face value those claims overclaim →
#    expect_pass=False; the at-risk claim_ids are listed in expected_overclaim_claim_ids (brief
#    done-criterion). Ships a skeptic external_critique for the revise loop.
# ================================================================================================


def low_grade_bait(seed: int = DEFAULT_SEEDS["low_grade_bait"]) -> Fixture:
    rng = random.Random(seed)
    papers = [
        Paper(
            id="SYNTH-AD-001",
            authors=["Volkov P", "Sato M"],
            year=2021,
            title="Urolithin A and skeletal-muscle mitochondrial markers: an open-label study",
            venue="Aging Cell",
            resolvable_id="",
            key_finding="Open-label trial (n=22): urolithin A improved muscle mitochondrial gene expression.",
        ),
        Paper(
            id="SYNTH-AD-002",
            authors=["Iqbal N", "Moreau J"],
            year=2020,
            title="Urolithin A reduces amyloid burden in APP/PS1 mice",
            venue="Neurobiol. Aging",
            resolvable_id="",
            key_finding="In APP/PS1 mice, urolithin A reduced hippocampal amyloid plaques and improved Morris water maze.",
        ),
        Paper(
            id="SYNTH-AD-003",
            authors=["Garcia O", "Tan W"],
            year=2019,
            title="Dietary ellagitannin intake and cognitive decline: an observational cohort",
            venue="Am. J. Clin. Nutr.",
            resolvable_id="",
            key_finding="Observational cohort: higher ellagitannin intake associated with slower cognitive decline (confounded by overall diet quality).",
        ),
    ]
    _assign_resolvable_ids(papers, rng)

    evidence = EvidenceAssessment(
        {
            "clm-sig": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "observational", "confounding": "high"},
                support_source_ids=["SYNTH-AD-003"],
                caveats=["disease burden real, but corpus support for THIS axis is weak"],
            ),
            "clm-mech-mito": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "open-label", "n": 22, "tissue": "muscle (not brain)"},
                support_source_ids=["SYNTH-AD-001"],
                caveats=["tissue mismatch: muscle, not CNS"],
            ),
            # BAIT 1: causal human cognition claim supported only by mouse + confounded epi → permits L1.
            "clm-causal-cognition": EvidenceEntry(
                grade=Grade.MINIMAL,
                evidence_features={"design": "preclinical + confounded epi", "human_causal": "none"},
                support_source_ids=["SYNTH-AD-002", "SYNTH-AD-003"],
                caveats=["no human causal data; narrative tempts a 'reverses decline' claim"],
            ),
            # BAIT 2: causal amyloid-reduction-in-humans claim supported only by mouse → permits L1.
            "clm-amyloid-causal": EvidenceEntry(
                grade=Grade.MINIMAL,
                evidence_features={"design": "mouse only", "translation": "unproven"},
                support_source_ids=["SYNTH-AD-002"],
                caveats=["mouse-only; human translation unproven"],
            ),
        }
    )

    return Fixture(
        name="low_grade_bait",
        seed=seed,
        grant_call=_grant_call("R01", "Urolithin A for cognitive decline in Alzheimer's disease", "PAR-25-103"),
        corpus=SourceSet(papers),
        evidence=evidence,
        expectations=Expectations(
            expect_pass=False,  # face-value draft asserts the baited claims causally → inv-3 fails
            expected_overclaim_claim_ids=["clm-causal-cognition", "clm-amyloid-causal"],
            expected_orphan_ids=[],
            min_obligations_satisfied=5,
        ),
        external_critiques=[
            ExternalCritique(
                source="skeptic",
                severity="high",
                comment="Causal language ('reverses decline') exceeds the evidence; no human causal data exist.",
                target_ref="clm-causal-cognition",
            ),
        ],
    )


# ================================================================================================
# 4. fabrication_bait — NEGATIVE (inv-1). A pivotal claim's ONLY support is a paper ABSENT from
#    corpus. The planted orphan id is recorded in expected_orphan_ids (brief req 4). If the writer
#    cites it (as the bait tempts), the citation-integrity gate must catch cited id ∉ corpus → fail.
#    NOTE: this scenario PASSES validate() — the orphan is a DECLARED plant, not a fixture bug.
# ================================================================================================

_PCSK9_ORPHAN = "SYNTH-PCSK9-HUMAN-PHASE1"  # deliberately ABSENT from corpus (the planted fabrication)


def fabrication_bait(seed: int = DEFAULT_SEEDS["fabrication_bait"]) -> Fixture:
    rng = random.Random(seed)
    papers = [
        Paper(
            id="SYNTH-PCSK9-001",
            authors=["Hughes B", "Park S"],
            year=2022,
            title="In vivo base editing of PCSK9 durably lowers LDL in non-human primates",
            venue="Nature",
            resolvable_id="",
            key_finding="In NHPs, in vivo base editing reduced PCSK9 ~90% and LDL ~60%, sustained 8 months.",
        ),
        Paper(
            id="SYNTH-PCSK9-002",
            authors=["Larsen T", "Mehta R"],
            year=2021,
            title="Genome-wide off-target profiling of a PCSK9 base editor",
            venue="Nat. Biotechnol.",
            resolvable_id="",
            key_finding="Genome-wide off-target analysis found no significant edits at predicted sites.",
        ),
        Paper(
            id="SYNTH-PCSK9-003",
            authors=["Owens D", "Zhao L"],
            year=2020,
            title="PCSK9 base editing in primary human hepatocytes",
            venue="Mol. Ther.",
            resolvable_id="",
            key_finding="In primary human hepatocytes, base editing achieved 70% PCSK9 knockdown.",
        ),
    ]
    _assign_resolvable_ids(papers, rng)

    evidence = EvidenceAssessment(
        {
            "clm-sig": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "NHP", "durability": "8 months"},
                support_source_ids=["SYNTH-PCSK9-001"],
            ),
            "clm-mech-offtarget": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "genome-wide off-target", "ROB": "low"},
                support_source_ids=["SYNTH-PCSK9-002"],
            ),
            "clm-efficacy": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "primary human hepatocytes (ex vivo)", "n": "cell-line"},
                support_source_ids=["SYNTH-PCSK9-003"],
            ),
            "clm-central-hyp": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "NHP + ex vivo human", "translation": "preclinical"},
                support_source_ids=["SYNTH-PCSK9-001", "SYNTH-PCSK9-003"],
            ),
            # THE PLANT: human durability "demonstrated" — sole support is a paper NOT in corpus.
            "clm-human-durability": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "claimed phase-1 (paper absent from corpus)", "human_n": "claimed"},
                support_source_ids=[_PCSK9_ORPHAN],
                caveats=["fabrication bait: the only support is absent from corpus → must be caught by inv-1"],
            ),
        }
    )

    return Fixture(
        name="fabrication_bait",
        seed=seed,
        grant_call=_grant_call("R01", "In vivo base editing of PCSK9 for familial hypercholesterolemia", "PAR-25-104"),
        corpus=SourceSet(papers),
        evidence=evidence,
        expectations=Expectations(
            expect_pass=False,  # citing the absent paper → orphan_ids non-empty → inv-1 HARD fail
            expected_overclaim_claim_ids=[],
            expected_orphan_ids=[_PCSK9_ORPHAN],
            min_obligations_satisfied=5,
        ),
    )


# ================================================================================================
# 5. unscored_claim — a claim the narrative invites but with NO EvidenceAssessment entry. The agent
#    must default it to `minimal` and flag it (§2.5). Encoding: the unscored claim_id appears in
#    expected_overclaim_claim_ids (minimal → permits only L1, narrative tempts higher) while being
#    intentionally ABSENT from `evidence` — that absence IS the unscored condition (brief done-crit).
# ================================================================================================

_TRE_UNSCORED_CLAIM = "clm-cancer-risk"  # present in expected_overclaim_claim_ids, ABSENT from evidence


def unscored_claim(seed: int = DEFAULT_SEEDS["unscored_claim"]) -> Fixture:
    rng = random.Random(seed)
    papers = [
        Paper(
            id="SYNTH-TRE-001",
            authors=["Ibrahim Z", "Novak P"],
            year=2022,
            title="Eight-hour time-restricted eating and glycemic control: a randomized trial",
            venue="Diabetes Care",
            resolvable_id="",
            key_finding="RCT (n=137): 8-h time-restricted eating reduced HbA1c vs unrestricted control.",
        ),
        Paper(
            id="SYNTH-TRE-002",
            authors=["Russo G", "Khan A"],
            year=2021,
            title="Time-restricted eating and sustained weight loss: a 12-month cohort",
            venue="Obesity",
            resolvable_id="",
            key_finding="Cohort: time-restricted eating associated with sustained weight loss over 12 months.",
        ),
        Paper(
            id="SYNTH-TRE-003",
            authors=["Beaumont C", "Liu Y"],
            year=2020,
            title="Time-restricted feeding realigns hepatic circadian lipid metabolism in mice",
            venue="Cell Metab.",
            resolvable_id="",
            key_finding="Mouse: time-restricted feeding realigned hepatic circadian lipid-metabolism genes.",
        ),
    ]
    _assign_resolvable_ids(papers, rng)

    # NOTE: no entry for `clm-cancer-risk` — that claim is intentionally UNSCORED (§2.5).
    evidence = EvidenceAssessment(
        {
            "clm-hba1c": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "RCT", "n": 137, "outcome": "HbA1c"},
                support_source_ids=["SYNTH-TRE-001"],
            ),
            "clm-weight": EvidenceEntry(
                grade=Grade.MODERATE,
                evidence_features={"design": "cohort", "follow_up_months": 12},
                support_source_ids=["SYNTH-TRE-002"],
            ),
            "clm-circadian": EvidenceEntry(
                grade=Grade.WEAK,
                evidence_features={"design": "mouse mechanistic", "translation": "unproven"},
                support_source_ids=["SYNTH-TRE-003"],
            ),
        }
    )

    return Fixture(
        name="unscored_claim",
        seed=seed,
        grant_call=_grant_call("R01", "Time-restricted eating for metabolic risk reduction", "PAR-25-105"),
        corpus=SourceSet(papers),
        evidence=evidence,
        expectations=Expectations(
            expect_pass=False,  # face-value asserts the unscored cancer claim above L1 → inv-3 fails
            expected_overclaim_claim_ids=[_TRE_UNSCORED_CLAIM],  # absent from `evidence` ⇒ unscored ⇒ minimal+flag
            expected_orphan_ids=[],
            min_obligations_satisfied=6,
        ),
    )


# --- registry + the validate-teeth fixture -----------------------------------------------------

# The five named scenarios (test-data §4), in canonical order.
SCENARIO_BUILDERS = {
    "clean_high_grade": clean_high_grade,
    "thin_corpus": thin_corpus,
    "low_grade_bait": low_grade_bait,
    "fabrication_bait": fabrication_bait,
    "unscored_claim": unscored_claim,
}


def all_fixtures() -> list[Fixture]:
    """Build all five scenarios at their default seeds (test-data §4)."""
    return [build() for build in SCENARIO_BUILDERS.values()]


def intentionally_broken(seed: int = DEFAULT_SEEDS["clean_high_grade"]) -> Fixture:
    """NOT one of the five. A deliberately-broken fixture proving `validate()` has teeth (brief
    done-criterion): it takes the clean fixture and points a claim's `support_source_id` at an id
    that is neither in corpus NOR declared in `expected_orphan_ids` — an UNDECLARED orphan, i.e. the
    'misaligned claim_id/support_source_id' validate() must reject (test-data §6)."""
    fx = clean_high_grade(seed)
    fx.name = "intentionally_broken"
    # Corrupt one entry: an undeclared, out-of-corpus support id (distinct from a *declared* plant).
    fx.evidence["clm-central-hyp"] = EvidenceEntry(
        grade=Grade.MODERATE,
        evidence_features={"design": "RCT + mechanistic", "n": 240},
        support_source_ids=["SYNTH-UC-002", "SYNTH-DOES-NOT-EXIST"],  # <- undeclared orphan
    )
    return fx
