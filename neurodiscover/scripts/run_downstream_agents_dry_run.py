"""
Dry-run integration for downstream discovery agents.

Safe behavior:
- Does not write to Supabase
- Does not truncate tables
- Does not call cli.py build
- Only tests agent chaining with sample evidence rows
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT_DIR / "agents"

sys.path.insert(0, str(AGENTS_DIR))

from patient_subgroup_agent import PatientSubgroupAgent
from treatment_connection_agent import TreatmentConnectionAgent
from evidence_scoring_agent import EvidenceScoringAgent
from commercial_discovery_agent import CommercialDiscoveryAgent


def main():
    evidence_rows = [
        {
            "source_type": "literature",
            "title": "Metabolomic Changes in Idiopathic and GBA1 Parkinson's Disease",
            "subgroup": "GBA-mutation PD",
            "mechanism": "Metabolomic changes / lysosomal dysfunction",
            "treatment": "GCase activation",
            "key_result": "Significant metabolic differences observed in GBA1 Parkinson's disease.",
        },
        {
            "source_type": "clinical_trial",
            "title": "LRRK2 inhibitor study in Parkinson's disease",
            "subgroup": "LRRK2 PD",
            "mechanism": "LRRK2 kinase pathway",
            "treatment": "LRRK2 inhibition",
            "key_result": "Targeted inhibition may be relevant for genetically defined PD subgroup.",
        },
        {
            "source_type": "grant",
            "title": "Alpha-synuclein aggregation research program",
            "subgroup": "Alpha-synuclein-high PD",
            "mechanism": "Alpha-synuclein aggregation",
            "treatment": "Anti-alpha-synuclein therapy",
            "key_result": "Grant supports translational work in synuclein biology.",
        },
    ]

    subgroup_agent = PatientSubgroupAgent()
    treatment_agent = TreatmentConnectionAgent()
    scoring_agent = EvidenceScoringAgent()
    commercial_agent = CommercialDiscoveryAgent()

    subgroups = subgroup_agent.run(evidence_rows)
    print("\n=== Patient Subgroups ===")
    print(subgroups)

    treatment_connections = treatment_agent.run(subgroups, evidence_rows
)
    print("\n=== Treatment Connections ===")
    print(treatment_connections)

    scored_connections = scoring_agent.run(treatment_connections,evidence_rows)
    print("\n=== Evidence Scored Connections ===")
    print(scored_connections)

    commercial_outputs = commercial_agent.run(scored_connections)
    print("\n=== Commercial Discovery Outputs ===")
    print(commercial_outputs)


if __name__ == "__main__":
    main()
